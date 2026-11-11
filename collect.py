"""Daily stock screening. No broker execution or real-time quote feed."""
import argparse
import sys
import time
import io
import urllib.request
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

OUT = Path('reports')
OUT.mkdir(exist_ok=True)
KST = ZoneInfo('Asia/Seoul')


def korean():
    """KRX listed stocks via FinanceDataReader listing and Yahoo daily OHLCV batches.

    Free third-party feeds may be incomplete or unavailable. Fail closed on poor coverage.
    """
    import FinanceDataReader as fdr

    listing = fdr.StockListing('KRX')
    if listing is None or listing.empty:
        raise RuntimeError('KRX listing unavailable')
    code_col = next((c for c in ('Code', 'Symbol') if c in listing.columns), None)
    market_col = next((c for c in ('Market', 'MarketName') if c in listing.columns), None)
    if not code_col or not market_col:
        raise RuntimeError(f'Unexpected listing columns: {list(listing.columns)}')
    listing = listing[listing[market_col].astype(str).str.upper().isin(['KOSPI', 'KOSDAQ'])].copy()
    listing['ticker'] = listing[code_col].astype(str).str.zfill(6)
    listing = listing[listing['ticker'].str.fullmatch(r'\d{6}')].drop_duplicates('ticker')
    if len(listing) < 1500:
        raise RuntimeError(f'KRX listing suspiciously small: {len(listing)}')
    market_map = {'KOSPI': 'KS', 'KOSDAQ': 'KQ'}
    listing['yf_symbol'] = listing['ticker'] + '.' + listing[market_col].str.upper().map(market_map)
    symbol_to_ticker = dict(zip(listing['yf_symbol'], listing['ticker']))
    market_by_ticker = dict(zip(listing['ticker'], listing[market_col]))
    name_by_ticker = dict(zip(listing['ticker'], listing['Name'])) if 'Name' in listing.columns else {}
    symbols = list(symbol_to_ticker)
    print(f'KRX_UNIVERSE {len(symbols)}', flush=True)

    today = datetime.now(KST).date()
    start = (today - timedelta(days=55)).isoformat()
    end = (today + timedelta(days=1)).isoformat()
    rows = []
    failed_batches = 0
    # Batches reduce requests; multi-symbol Yahoo data may still be rate limited.
    for offset in range(0, len(symbols), 50):
        batch = symbols[offset:offset + 50]
        try:
            data = yf.download(batch, start=start, end=end, interval='1d',
                               auto_adjust=False, group_by='ticker', threads=False,
                               progress=False, timeout=25)
            if data is None or data.empty:
                raise ValueError('empty batch')
            for symbol in batch:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        frame = data[symbol].copy() if symbol in data.columns.get_level_values(0) else pd.DataFrame()
                    else:
                        frame = data.copy() if len(batch) == 1 else pd.DataFrame()
                    if frame.empty or not {'Open', 'High', 'Low', 'Close', 'Volume'}.issubset(frame.columns):
                        continue
                    frame = frame.dropna(subset=['Open', 'High', 'Low', 'Close', 'Volume'])
                    frame = frame[frame['Volume'] > 0].sort_index()
                    if len(frame) < 21:
                        continue
                    last = frame.iloc[-1]
                    prev = frame.iloc[-2]
                    history = frame['Volume'].iloc[-21:-1]
                    if len(history) != 20 or history.mean() <= 0 or prev['Close'] <= 0:
                        continue
                    last_date = pd.Timestamp(frame.index[-1]).date()
                    high, low, op, close = (float(last[k]) for k in ('High', 'Low', 'Open', 'Close'))
                    volume = int(last['Volume'])
                    span = high - low
                    ticker = symbol_to_ticker[symbol]
                    # Approximate turnover: closing price x volume; NOT official KRX traded value.
                    rows.append({'ticker': ticker, 'name': name_by_ticker.get(ticker, ''),
                                 'market': market_by_ticker[ticker], 'date': last_date.isoformat(),
                                 'open': op, 'high': high, 'low': low, 'close': close,
                                 'volume': volume,
                                 'volume_multiple_20d': round(volume / float(history.mean()), 2),
                                 'turnover_krw': round(close * volume),
                                 'turnover_source': 'estimated_close_times_volume',
                                 'change_pct': round((close / float(prev['Close']) - 1) * 100, 2),
                                 'close_location_pct': round((close - low) / span * 100, 1) if span > 0 else None,
                                 'upper_wick_pct': round((high - max(op, close)) / span * 100, 1) if span > 0 else None,
                                 'history_sessions': 20})
                except Exception as exc:
                    print(f'SYMBOL_ERROR {symbol}: {exc}', flush=True)
        except Exception as exc:
            failed_batches += 1
            print(f'BATCH_ERROR {offset // 50 + 1}: {type(exc).__name__}: {exc}', flush=True)
        print(f'PROGRESS {min(offset + 50, len(symbols))}/{len(symbols)}, valid={len(rows)}', flush=True)

    save_results(rows, 'kr', len(symbols), failed_batches)


            if not yf_sym.replace('-', '').isalnum():
                continue
            symbols[yf_sym] = sym
    print(f'US_LISTING_PARSED symbols={len(symbols)}', flush=True)
    if len(symbols) < 2000:
        raise RuntimeError(f'US listing suspiciously small: {len(symbols)}')
    return symbols


def american():
    symbol_map = us_universe()
    symbols = list(symbol_map)
    print(f'US_UNIVERSE {len(symbols)}', flush=True)
    today = datetime.now(KST).date()
    start = (today - timedelta(days=55)).isoformat()
    end = (today + timedelta(days=1)).isoformat()
    rows = []
    failed_batches = 0
    for offset in range(0, len(symbols), 50):
        batch = symbols[offset:offset + 50]
        try:
            data = yf.download(batch, start=start, end=end, interval='1d',
                               auto_adjust=False, group_by='ticker', threads=False,
                               progress=False, timeout=25)
            if data is None or data.empty:
                raise ValueError('empty batch')
            for symbol in batch:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        frame = data[symbol].copy() if symbol in data.columns.get_level_values(0) else pd.DataFrame()
                    else:
                        frame = data.copy() if len(batch) == 1 else pd.DataFrame()
                    if frame.empty or not {'Open', 'High', 'Low', 'Close', 'Volume'}.issubset(frame.columns):
                        continue
                    frame = frame.dropna(subset=['Open', 'High', 'Low', 'Close', 'Volume'])
                    frame = frame[frame['Volume'] > 0].sort_index()
                    if len(frame) < 21:
                        continue
                    last, prev = frame.iloc[-1], frame.iloc[-2]
                    history = frame['Volume'].iloc[-21:-1]
                    if len(history) != 20 or history.mean() <= 0 or prev['Close'] <= 0:
                        continue
                    last_date = pd.Timestamp(frame.index[-1]).date()
                    high, low, op, close = (float(last[k]) for k in ('High', 'Low', 'Open', 'Close'))
                    volume = int(last['Volume'])
                    span = high - low
                    rows.append({'ticker': symbol_map[symbol], 'name': '', 'market': 'US',
                                 'date': last_date.isoformat(), 'open': op, 'high': high,
                                 'low': low, 'close': close, 'volume': volume,
                                 'volume_multiple_20d': round(volume / float(history.mean()), 2),
                                 'turnover_usd': round(close * volume),
                                 'turnover_source': 'estimated_close_times_volume',
                                 'change_pct': round((close / float(prev['Close']) - 1) * 100, 2),
                                 'close_location_pct': round((close - low) / span * 100, 1) if span > 0 else None,
                                 'upper_wick_pct': round((high - max(op, close)) / span * 100, 1) if span > 0 else None,
                                 'history_sessions': 20})
                except Exception as exc:
                    print(f'SYMBOL_ERROR {symbol}: {exc}', flush=True)
        except Exception as exc:
            failed_batches += 1
            print(f'BATCH_ERROR {offset // 50 + 1}: {type(exc).__name__}: {exc}', flush=True)
        print(f'PROGRESS US {min(offset + 50, len(symbols))}/{len(symbols)}, valid={len(rows)}', flush=True)
    save_results(rows, 'us', len(symbols), failed_batches)


def save_results(rows, market, universe_count, failed_batches):
    if not rows:
        raise RuntimeError(f'{market.upper()}: no valid records')
    df = pd.DataFrame(rows)
    coverage = len(df) / universe_count
    print(f'COVERAGE {market.upper()} {len(df)}/{universe_count} ({coverage:.1%}), failed_batches={failed_batches}', flush=True)
    if coverage < 0.65:
        raise RuntimeError(f'{market.upper()}: insufficient coverage {coverage:.1%}; failed_batches={failed_batches}; no report published')
    df = df.sort_values('date', ascending=False)
    latest = df['date'].iloc[0]
    df = df[df['date'] == latest].copy()
    if len(df) / universe_count < 0.60:
        raise RuntimeError(f'{market.upper()}: latest-date coverage too low: {len(df)}/{universe_count}')
    today_kst = datetime.now(KST).date()
    latest_day = datetime.strptime(latest, '%Y-%m-%d').date()
    if (today_kst - latest_day).days > 5:
        raise RuntimeError(f'{market.upper()}: stale data: latest={latest}, today_KST={today_kst}')
    turnover_col = 'turnover_krw' if market == 'kr' else 'turnover_usd'
    stamp = latest.replace('-', '')
    df.sort_values(turnover_col, ascending=False).to_csv(OUT / f'{market}_all_{stamp}.csv', index=False, encoding='utf-8-sig')
    quiet = df[(df.volume_multiple_20d >= 3) & df.change_pct.between(-3, 3) &
               (df[turnover_col] >= (5_000_000_000 if market == 'kr' else 5_000_000))]
    momentum = df[(df.change_pct > 3) & (df.close_location_pct >= 65)]
    quiet.sort_values('volume_multiple_20d', ascending=False).to_csv(OUT / f'{market}_volume_candidates_{stamp}.csv', index=False, encoding='utf-8-sig')
    momentum.sort_values(turnover_col, ascending=False).to_csv(OUT / f'{market}_momentum_candidates_{stamp}.csv', index=False, encoding='utf-8-sig')
    print(f'SUCCESS {market.upper()}: {len(df)} tickers, date={latest}, quiet={len(quiet)}, momentum={len(momentum)}, coverage={len(df)/universe_count:.1%}, failed_batches={failed_batches}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('market', choices=['kr', 'us'])
    args = parser.parse_args()
    print(f'START market={args.market} KST={datetime.now(KST).isoformat()}', flush=True)
    if args.market == 'kr':
        korean()
    else:
        try:
            american()
        except BaseException as exc:
            print(f'US_FATAL_ERROR type={type(exc).__name__} message={exc!r}', file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
    turnover_col = 'turnover_krw' if market == 'kr' else 'turnover_usd'
    stamp = latest.replace('-', '')
    df.sort_values(turnover_col, ascending=False).to_csv(OUT / f'{market}_all_{stamp}.csv', index=False, encoding='utf-8-sig')
    quiet = df[(df.volume_multiple_20d >= 3) & df.change_pct.between(-3, 3) &
               (df[turnover_col] >= (5_000_000_000 if market == 'kr' else 5_000_000))]
    momentum = df[(df.change_pct > 3) & (df.close_location_pct >= 65)]
    quiet.sort_values('volume_multiple_20d', ascending=False).to_csv(OUT / f'{market}_volume_candidates_{stamp}.csv', index=False, encoding='utf-8-sig')
    momentum.sort_values(turnover_col, ascending=False).to_csv(OUT / f'{market}_momentum_candidates_{stamp}.csv', index=False, encoding='utf-8-sig')
    print(f'SUCCESS {market.upper()}: {len(df)} tickers, date={latest}, quiet={len(quiet)}, momentum={len(momentum)}, coverage={len(df)/universe_count:.1%}, failed_batches={failed_batches}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('market', choices=['kr', 'us'])
    args = parser.parse_args()
    print(f'START market={args.market} KST={datetime.now(KST).isoformat()}', flush=True)
    if args.market == 'kr':
        korean()
    else:
        try:
            american()
        except BaseException as exc:
            print(f'US_FATAL_ERROR type={type(exc).__name__} message={exc!r}', file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
            raise
