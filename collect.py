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
