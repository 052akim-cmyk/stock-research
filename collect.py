import argparse
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import FinanceDataReader as fdr
import yfinance as yf

OUT = Path('reports')
OUT.mkdir(exist_ok=True)
KST = ZoneInfo('Asia/Seoul')
KR_WATCH = {'005930':'삼성전자', '000660':'SK하이닉스', '003000':'부광약품', '006400':'삼성SDI', '373220':'LG에너지솔루션'}

def korean():
    start = (datetime.now(KST).date() - timedelta(days=75)).isoformat()
    rows = []
    for ticker, name in KR_WATCH.items():
        try:
            data = fdr.DataReader('NAVER:' + ticker, start)
            if data is None or len(data) < 22:
                print(f'SKIP {ticker}: insufficient data')
                continue
            data = data.sort_index().dropna(subset=['Open','High','Low','Close','Volume'])
            if len(data) < 22:
                continue
            last, prev = data.iloc[-1], data.iloc[-2]
            avg = data['Volume'].iloc[-21:-1].mean()
            high, low, op, close = [float(last[k]) for k in ['High','Low','Open','Close']]
            rng = high-low
            rows.append({'ticker':ticker,'name':name,'date':str(data.index[-1].date()),
                'open':op,'high':high,'low':low,'close':close,
                'volume':int(last['Volume']), 'volume_multiple_20d':round(float(last['Volume'])/avg,2) if avg else None,
                'turnover_est_krw':round(close*float(last['Volume'])),
                'change_pct':round((close/float(prev['Close'])-1)*100,2),
                'close_location_pct':round((close-low)/rng*100,1) if rng else None,
                'upper_wick_pct':round((high-max(op,close))/rng*100,1) if rng else None})
        except Exception as exc:
            print(f'ERROR {ticker}: {type(exc).__name__}: {exc}')
    if len(rows) < 3:
        raise RuntimeError(f'KR data validation failed: only {len(rows)} of {len(KR_WATCH)} tickers returned')
    df = pd.DataFrame(rows)
    path = OUT / f'kr_watch_{datetime.now(KST):%Y%m%d}.csv'
    df.to_csv(path,index=False,encoding='utf-8-sig')
    print(df.to_string(index=False))
    print('SUCCESS: KR WATCHLIST ONLY. NOT an all-market scan. Turnover is estimated close x volume.')

def american():
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

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('market',choices=['kr','us'])
    args=p.parse_args()
    (korean if args.market=='kr' else american)()
