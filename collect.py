"""Daily stock screening. No broker execution or real-time quote feed."""
import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

OUT = Path('reports')
OUT.mkdir(exist_ok=True)
KST = ZoneInfo('Asia/Seoul')


def korean():
    """Cross-sectional KOSPI/KOSDAQ scan using daily KRX snapshots via pykrx."""
    from pykrx import stock

    today = datetime.now(KST).date()
    # A little extra calendar history for 21 completed trading sessions.
    dates = [today - timedelta(days=n) for n in range(0, 48)]
    sessions = []
    failures = []
    for d in dates:
        ds = d.strftime('%Y%m%d')
        try:
            frame = stock.get_market_ohlcv_by_ticker(ds, market='ALL')
            if frame is not None and not frame.empty and '거래량' in frame.columns and frame['거래량'].sum() > 0:
                frame.index = frame.index.astype(str).str.zfill(6)
                sessions.append((d, frame))
                print(f'SESSION {ds}: {len(frame)} tickers')
            else:
                print(f'NO_SESSION {ds}')
        except Exception as exc:
            failures.append((ds, str(exc)))
            print(f'FETCH_ERROR {ds}: {type(exc).__name__}: {exc}')
        if len(sessions) >= 21:
            break
        time.sleep(0.15)

    if len(sessions) < 21:
        raise RuntimeError(f'KR scan incomplete: {len(sessions)}/21 trading sessions, fetch_errors={len(failures)}')
    sessions.sort(key=lambda x: x[0])
    last_day, last = sessions[-1]
    if (today - last_day).days > 5:
        raise RuntimeError(f'KR data stale: latest session={last_day}, today={today}')
    allowed = set(stock.get_market_ticker_list(last_day.strftime('%Y%m%d'), market='KOSPI'))
    allowed |= set(stock.get_market_ticker_list(last_day.strftime('%Y%m%d'), market='KOSDAQ'))
    if len(allowed) < 1500:
        raise RuntimeError(f'KR universe suspiciously small: {len(allowed)} tickers')
    last = last.loc[last.index.intersection(allowed)].copy()
    if len(last) < 1500:
        raise RuntimeError(f'KR latest snapshot suspiciously small: {len(last)} tickers')

    historical_volumes = pd.concat(
        [f['거래량'].rename(d.isoformat()) for d, f in sessions[:-1]], axis=1
    )
    historical_closes = sessions[-2][1]['종가']
    avg20 = historical_volumes.mean(axis=1)
    count20 = historical_volumes.notna().sum(axis=1)
    prev_close = historical_closes.reindex(last.index)
    volume = last['거래량'].astype(float)
    close = last['종가'].astype(float)
    op = last['시가'].astype(float)
    high = last['고가'].astype(float)
    low = last['저가'].astype(float)
    turnover = last['거래대금'].astype(float) if '거래대금' in last else close * volume
    denom = (high - low).replace(0, float('nan'))
    df = pd.DataFrame({
        'ticker': last.index,
        'date': last_day.isoformat(),
        'open': op, 'high': high, 'low': low, 'close': close,
        'volume': volume.astype('int64'),
        'volume_multiple_20d': volume.div(avg20.reindex(last.index).replace(0, float('nan'))).round(2),
        'turnover_krw': turnover.round().astype('int64'),
        'change_pct': ((close / prev_close - 1) * 100).round(2),
        'close_location_pct': ((close - low) / denom * 100).round(1),
        'upper_wick_pct': ((high - pd.concat([op, close], axis=1).max(axis=1)) / denom * 100).round(1),
        'history_sessions': count20.reindex(last.index).fillna(0).astype(int),
    })
    df = df[(df['history_sessions'] == 20) & (df['volume'] > 0) & (df['close'] > 0)].copy()
    if len(df) < 1400:
        raise RuntimeError(f'KR valid rows too few: {len(df)}')
    df = df.reset_index(drop=True).sort_values('turnover_krw', ascending=False)
    day = last_day.strftime('%Y%m%d')
    df.to_csv(OUT / f'kr_all_{day}.csv', index=False, encoding='utf-8-sig')
    quiet = df[(df['volume_multiple_20d'] >= 3) & (df['turnover_krw'] >= 5_000_000_000)
               & (df['change_pct'].between(-3, 3))].copy()
    momentum = df[(df['turnover_krw'] >= 5_000_000_000) & (df['change_pct'] > 3)
                  & (df['close_location_pct'] >= 65)].copy()
    quiet.sort_values(['volume_multiple_20d','turnover_krw'], ascending=False).to_csv(
        OUT / f'kr_volume_candidates_{day}.csv', index=False, encoding='utf-8-sig')
    momentum.sort_values('turnover_krw', ascending=False).to_csv(
        OUT / f'kr_momentum_candidates_{day}.csv', index=False, encoding='utf-8-sig')
    print(f'SUCCESS KR: date={last_day}, universe={len(allowed)}, valid={len(df)}')

def american():
    # Preserved original US watchlist behavior (not an all-market scan).
    symbols = ['SPY','QQQ','DIA','SOXX','EW','XEL','LSCC','NVDA','AMD','USDKRW=X']
    rows = []
    for symbol in symbols:
        try:
            df = yf.Ticker(symbol).history(period='45d', interval='1d', auto_adjust=False)
            if len(df)<22:
                print(f'SKIP {symbol}: insufficient history')
                continue
            df=df.dropna(subset=['Close','Volume'])
            last,prev=df.iloc[-1],df.iloc[-2]
            avg=df['Volume'].iloc[-21:-1].mean()
            rows.append({'ticker':symbol,'date':str(df.index[-1].date()),
                'close':float(last['Close']),'volume':int(last['Volume']),
                'change_pct':round((float(last['Close'])/float(prev['Close'])-1)*100,2),
                'volume_multiple_20d':round(float(last['Volume'])/avg,2) if avg else None})
        except Exception as exc:
            print(f'ERROR {symbol}: {type(exc).__name__}: {exc}')
    if len(rows)<6:
        raise RuntimeError(f'US data validation failed: {len(rows)} tickers')
    df=pd.DataFrame(rows)
    df.to_csv(OUT/f'us_watch_{datetime.now(KST):%Y%m%d}.csv',index=False,encoding='utf-8-sig')
    print(df.to_string(index=False))
    print('SUCCESS: US WATCHLIST ONLY. NOT an all-market scan.')


