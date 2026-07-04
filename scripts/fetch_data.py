"""Fetch EOD bars + fundamentals for all tickers in tickers.txt and write docs/data.json.

Runs in GitHub Actions (see .github/workflows/update-data.yml). Uses yfinance (Yahoo Finance).
"""
import json
import os
import time
from datetime import datetime, timezone

import yfinance as yf


def read_tickers(path="tickers.txt"):
    tickers = []
    with open(path) as f:
        for line in f:
            line = line.strip().upper()
            if line and not line.startswith("#") and line not in tickers:
                tickers.append(line)
    return tickers


def fetch_one(symbol):
    tk = yf.Ticker(symbol)
    hist = tk.history(period="430d", interval="1d", auto_adjust=False)
    if hist.empty:
        raise ValueError("no price data returned")
    bars = []
    for ts, row in hist.iterrows():
        try:
            bars.append([
                int(ts.timestamp()),
                round(float(row["Open"]), 4),
                round(float(row["High"]), 4),
                round(float(row["Low"]), 4),
                round(float(row["Close"]), 4),
                int(row["Volume"]) if row["Volume"] == row["Volume"] else 0,  # NaN check
            ])
        except (ValueError, TypeError):
            continue
    if len(bars) < 2:
        raise ValueError("not enough valid bars")
    info = {}
    try:
        info = tk.info or {}
    except Exception:
        pass  # fundamentals are best-effort; bars are the essential part
    return {
        "name": info.get("shortName") or info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "mcap": info.get("marketCap"),
        "beta": info.get("beta"),
        "bars": bars,
    }


def main():
    tickers = read_tickers()
    out = {
        "asof": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tickers": {},
    }
    failed = []
    for sym in tickers:
        try:
            out["tickers"][sym] = fetch_one(sym)
            print(f"OK   {sym}: {len(out['tickers'][sym]['bars'])} bars")
        except Exception as e:
            failed.append(sym)
            out["tickers"][sym] = {"error": str(e)[:120], "bars": []}
            print(f"FAIL {sym}: {e}")
        time.sleep(1)  # stay polite to Yahoo
    os.makedirs("docs", exist_ok=True)
    with open("docs/data.json", "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"Wrote docs/data.json — {len(tickers) - len(failed)}/{len(tickers)} tickers OK")
    if len(failed) == len(tickers):
        raise SystemExit("every ticker failed — aborting so the old data.json is kept")


if __name__ == "__main__":
    main()
