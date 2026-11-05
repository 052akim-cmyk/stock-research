import argparse
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import yfinance as yf
from pykrx import stock

OUT=Path("reports")
OUT.mkdir(exist_ok=True)

def kr_report():
    today=datetime.now(ZoneInfo("Asia/Seoul")).date()
    # Try recent sessions, because exchange publication may lag.
    last_error=None
    for delta in range(0, 8):
        day=(today-timedelta(days=delta)).strftime("%Y%m%d")
        try:
            frames=[]
            for market in ("KOSPI","KOSDAQ"):
                df=stock.get_market_ohlcv_by_ticker(day, market=market)
                if not df.empty:
                    df=df.copy()
                    df["시장"]=market
                    df["종목코드"]=df.index
                    frames.append(df)
            if frames:
                all_df=pd.concat(frames,ignore_index=True)
                if len(all_df)<1000:
                    raise ValueError(f"Unexpectedly few rows: {len(all_df)}")
                all_df.to_csv(OUT/f"kr_{day}.csv",index=False,encoding="utf-8-sig")
                print(f"KR snapshot {day}: {len(all_df)} tickers saved")
                print("CAUTION: Verify exchange close and data freshness before trading.")
                return
        except Exception as e:
            last_error=e
    raise RuntimeError(f"No valid KR snapshot obtained: {last_error}")

def us_report():
    # Market overview, not a complete US market scanner.
    symbols=["SPY","QQQ","DIA","SOXX","^VIX","USDKRW=X","AAPL","MSFT","NVDA","AMD"]
    rows=[]
    for symbol in symbols:
        try:
            df=yf.Ticker(symbol).history(period="35d",interval="1d",auto_adjust=False)
            if len(df)<2:
                continue
            latest, prev=df.iloc[-1],df.iloc[-2]
            rows.append({"ticker":symbol,"session_date":str(df.index[-1].date()),
                         "close":float(latest["Close"]),
                         "change_pct":round((float(latest["Close"])/float(prev["Close"])-1)*100,2),
                         "volume":int(latest["Volume"])})
        except Exception as e:
            print(f"WARN {symbol}: {e}")
    if len(rows)<6:
        raise RuntimeError("Insufficient US data; report NOT validated")
    df=pd.DataFrame(rows)
    df.to_csv(OUT/f"us_{datetime.now(ZoneInfo('Asia/Seoul')):%Y%m%d}.csv",
              index=False,encoding="utf-8-sig")
    print(df.to_string(index=False))
    print("US report is a watchlist snapshot, NOT an all-stock scan.")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("market",choices=["kr","us"])
    args=parser.parse_args()
    (kr_report if args.market=="kr" else us_report)()
