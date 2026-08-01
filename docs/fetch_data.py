#!/usr/bin/env python3
"""
Fetch daily prices for the HK/SGX watchlist plus SG/HK/Tech benchmarks,
compute 1D/1W/1M change, relative strength vs benchmark, sector rotation
aggregates, and a price-only conviction/feasibility score.

No options data is used anywhere in this script. FlashAlpha/QuantWheel/
MenthorQ do not cover HK/SGX names (confirmed: FlashAlpha returns
"no_cached_data" for HK/SGX tickers) and SGX REITs mostly have no listed
options market at all, so GEX is not computed here.

Conviction score (0-100), methodology -- documented so it can be audited
or replaced:
  - Trend alignment: how many of 1D/1W/1M changes share the majority sign.
  - Magnitude: average absolute change across 1D/1W/1M, scaled (10%+
    average move maxes this component out).
  - Relative strength: instrument's 1M change minus its benchmark's 1M
    change (outperformance vs its own market).
  These three components are weighted 40/30/30 and mapped to 0-100.
  This is a price-momentum score, not a fundamental or options-derived
  signal.

Feasibility score (0-100), methodology:
  - Position within the trailing 90-day range: 100 = at the 90d low
    (maximum room to run before hitting recent resistance), 0 = at the
    90d high (little room left, mean-reversion risk).
  This is a simple range-position proxy, not a target-price feasibility
  model like the GEX-based version in Basket Command Centre 2.

Writes data.json. Saves to /tmp first, then moves into place (race
condition guard, per the Basket Command Centre 2 pattern).
"""
import json
import os
import sys
import shutil
import tempfile
from datetime import datetime, timezone
from statistics import mean

import yfinance as yf
from tickers import TICKERS, BENCHMARKS, CATEGORY_BENCHMARK


def pct_change(series, periods_back):
    if len(series) <= periods_back:
        return None
    latest = series.iloc[-1]
    prior = series.iloc[-1 - periods_back]
    if prior == 0 or prior is None:
        return None
    return round((latest - prior) / prior * 100, 2)


def fetch_series(ticker):
    tk = yf.Ticker(ticker)
    hist = tk.history(period="4mo", interval="1d")
    if hist.empty:
        return None, None
    close = hist["Close"].dropna()
    name = ticker
    currency = ""
    try:
        name = tk.info.get("shortName") or ticker
        currency = tk.info.get("currency", "")
    except Exception:
        pass
    return close, {"name": name, "currency": currency}


def conviction_score(c1d, c1w, c1m, rel_strength_1m):
    vals = [v for v in (c1d, c1w, c1m) if v is not None]
    if not vals:
        return None
    signs = [1 if v > 0 else (-1 if v < 0 else 0) for v in vals]
    majority = 1 if sum(signs) >= 0 else -1
    agreement = sum(1 for s in signs if s == majority) / len(vals)  # 0-1

    magnitude = mean(abs(v) for v in vals)  # in %
    magnitude_score = min(magnitude / 10, 1.0)  # 10%+ avg move = maxed out

    rel_score = 0.5
    if rel_strength_1m is not None:
        rel_score = min(max((rel_strength_1m + 10) / 20, 0), 1)  # -10%..+10% -> 0..1

    composite = (agreement * 0.4) + (magnitude_score * 0.3) + (rel_score * 0.3)
    return round(composite * 100, 1)


def feasibility_score(close_series):
    if close_series is None or len(close_series) < 5:
        return None
    window = close_series.tail(90)
    hi, lo, last = window.max(), window.min(), window.iloc[-1]
    if hi == lo:
        return 50.0
    position = (last - lo) / (hi - lo)  # 0 = at low, 1 = at high
    return round((1 - position) * 100, 1)  # invert: 100 = most room to run


def main():
    # 1. Fetch benchmarks first
    benchmark_data = {}
    for b_ticker, meta in BENCHMARKS.items():
        close, info = fetch_series(b_ticker)
        if close is None:
            benchmark_data[b_ticker] = {"error": "no data", **meta}
            print(f"ERR benchmark {b_ticker}: no data", file=sys.stderr)
            continue
        benchmark_data[b_ticker] = {
            **meta,
            "name": info["name"],
            "currency": info["currency"],
            "last_price": round(float(close.iloc[-1]), 4),
            "last_date": close.index[-1].strftime("%Y-%m-%d"),
            "change_1d_pct": pct_change(close, 1),
            "change_1w_pct": pct_change(close, 5),
            "change_1m_pct": pct_change(close, 21),
        }
        print(f"OK  benchmark {b_ticker:10} {info['name']}")

    # 2. Fetch instruments
    results = []
    errors = []
    for ticker, category in TICKERS.items():
        try:
            close, info = fetch_series(ticker)
            if close is None:
                errors.append(ticker)
                results.append({"ticker": ticker, "category": category, "name": ticker, "error": "no data"})
                print(f"ERR {ticker:10} no data", file=sys.stderr)
                continue

            last_price = round(float(close.iloc[-1]), 4)
            last_date = close.index[-1].strftime("%Y-%m-%d")
            c1d = pct_change(close, 1)
            c1w = pct_change(close, 5)
            c1m = pct_change(close, 21)

            bench_ticker = CATEGORY_BENCHMARK.get(category)
            rel_strength_1m = None
            if bench_ticker and bench_ticker != ticker:
                bdata = benchmark_data.get(bench_ticker, {})
                b_c1m = bdata.get("change_1m_pct")
                if c1m is not None and b_c1m is not None:
                    rel_strength_1m = round(c1m - b_c1m, 2)

            history = [
                {"date": d.strftime("%Y-%m-%d"), "close": round(float(v), 4)}
                for d, v in close.tail(90).items()
            ]

            results.append({
                "ticker": ticker,
                "category": category,
                "name": info["name"],
                "currency": info["currency"],
                "last_price": last_price,
                "last_date": last_date,
                "change_1d_pct": c1d,
                "change_1w_pct": c1w,
                "change_1m_pct": c1m,
                "benchmark": bench_ticker,
                "rel_strength_1m_pct": rel_strength_1m,
                "conviction_score": conviction_score(c1d, c1w, c1m, rel_strength_1m),
                "feasibility_score": feasibility_score(close),
                "history": history,
            })
            print(f"OK  {ticker:10} {info['name']}")
        except Exception as e:
            errors.append(ticker)
            results.append({"ticker": ticker, "category": category, "name": ticker, "error": str(e)})
            print(f"ERR {ticker:10} {e}", file=sys.stderr)

    # 3. Sector rotation: average 1D/1W/1M change per category, vs each category's benchmark
    rotation = {}
    for row in results:
        if row.get("error"):
            continue
        cat = row["category"]
        rotation.setdefault(cat, {"c1d": [], "c1w": [], "c1m": []})
        if row["change_1d_pct"] is not None: rotation[cat]["c1d"].append(row["change_1d_pct"])
        if row["change_1w_pct"] is not None: rotation[cat]["c1w"].append(row["change_1w_pct"])
        if row["change_1m_pct"] is not None: rotation[cat]["c1m"].append(row["change_1m_pct"])

    sector_rotation = []
    for cat, vals in rotation.items():
        bench_ticker = CATEGORY_BENCHMARK.get(cat)
        bench_1m = benchmark_data.get(bench_ticker, {}).get("change_1m_pct") if bench_ticker else None
        avg_1m = round(mean(vals["c1m"]), 2) if vals["c1m"] else None
        sector_rotation.append({
            "category": cat,
            "count": len(vals["c1m"]),
            "avg_1d_pct": round(mean(vals["c1d"]), 2) if vals["c1d"] else None,
            "avg_1w_pct": round(mean(vals["c1w"]), 2) if vals["c1w"] else None,
            "avg_1m_pct": avg_1m,
            "benchmark": bench_ticker,
            "benchmark_1m_pct": bench_1m,
            "rel_to_benchmark_1m_pct": round(avg_1m - bench_1m, 2) if (avg_1m is not None and bench_1m is not None) else None,
        })
    sector_rotation.sort(key=lambda r: (r["avg_1m_pct"] is None, -(r["avg_1m_pct"] or 0)))

    payload = {
        "last_updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "instrument_count": len(results),
        "error_count": len(errors),
        "benchmarks": benchmark_data,
        "sector_rotation": sector_rotation,
        "instruments": results,
    }

    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, "data.json")
    with open(tmp_path, "w") as f:
        json.dump(payload, f, indent=2)

    final_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
    shutil.move(tmp_path, final_path)
    print(f"\nWrote {final_path}")
    print(f"{len(results) - len(errors)}/{len(results)} tickers OK")
    if errors:
        print(f"Failed tickers: {errors}", file=sys.stderr)


if __name__ == "__main__":
    main()
