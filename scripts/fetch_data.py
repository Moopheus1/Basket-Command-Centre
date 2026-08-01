#!/usr/bin/env python3
"""
Fetch daily prices for the HK/SGX watchlist plus SG/HK/Tech benchmarks,
compute 1D/1W/1M change, relative strength vs benchmark, sector rotation
aggregates, a price-only momentum/range score pair, and analyst price
targets where covered.

No options data is used anywhere in this script. FlashAlpha/QuantWheel/
MenthorQ do not cover HK/SGX names (confirmed: FlashAlpha returns
"no_cached_data" for HK/SGX tickers) and SGX REITs mostly have no listed
options market at all, so GEX is not computed here.

Momentum score (0-100) -- formerly "conviction"; renamed because
"conviction" implied more than a pure price-momentum read delivers.
Methodology, documented so it can be audited or replaced:
  - Trend alignment: how many of 1D/1W/1M changes share the majority sign.
  - Magnitude: average absolute change across 1D/1W/1M, scaled (10%+
    average move maxes this component out).
  - Relative strength: instrument's 1M change minus its benchmark's 1M
    change (outperformance vs its own market).
  These three components are weighted 40/30/30 and mapped to 0-100.

Range score (0-100) -- formerly "feasibility"; renamed because
"feasibility" implied a target-reachability model this dashboard doesn't
have. Methodology:
  - Position within the trailing 90-day range: 100 = at the 90d low
    (maximum room to run before hitting recent resistance), 0 = at the
    90d high (little room left, mean-reversion risk).
  This is a simple range-position proxy, not a target-price feasibility
  model like the GEX-based version in Basket Command Centre 2.

Price targets: pulled from yfinance's `.info` (targetMeanPrice /
targetHighPrice / targetLowPrice / numberOfAnalystOpinions /
recommendationKey), with retry logic -- this call has been observed to
intermittently fail with DNS resolution errors in this project's own
testing, and a single-try fallback made transient failures indistinguishable
from genuine "no analyst coverage." Each instrument now carries a
target_status field: "covered", "no_coverage" (structurally expected for
ETFs/preference shares, or genuinely thin-coverage names), or
"fetch_failed" (network issue -- distinct from a real gap).

Writes data.json. Saves to /tmp first, then moves into place (race
condition guard, per the Basket Command Centre 2 pattern).
"""
import json
import os
import sys
import shutil
import tempfile
import time
from datetime import datetime, timezone
from statistics import mean

import yfinance as yf
from tickers import TICKERS, BENCHMARKS, CATEGORY_BENCHMARK

YAHOO_QUOTE_URL = "https://finance.yahoo.com/quote/{ticker}"


def pct_change(series, periods_back):
    if len(series) <= periods_back:
        return None
    latest = series.iloc[-1]
    prior = series.iloc[-1 - periods_back]
    if prior == 0 or prior is None:
        return None
    return round((latest - prior) / prior * 100, 2)


def fetch_info_with_retry(tk, ticker, retries=3, delay=2.0):
    """
    yfinance's .info call has been observed (in this project's own testing)
    to intermittently fail with DNS resolution errors. A silent single-try
    fallback makes a transient network blip indistinguishable from a
    genuine "no analyst coverage" gap. Retry a few times before giving up,
    and report the failure explicitly rather than masking it as "no data".
    """
    last_err = None
    for attempt in range(retries):
        try:
            raw = tk.info
            if raw and (raw.get("shortName") or raw.get("regularMarketPrice") is not None):
                return raw, "ok"
            last_err = "empty response"
        except Exception as e:
            last_err = str(e)
        if attempt < retries - 1:
            time.sleep(delay)
    print(f"WARN {ticker}: .info fetch failed after {retries} attempts ({last_err})", file=sys.stderr)
    return {}, "fetch_failed"


def fetch_series_and_info(ticker):
    tk = yf.Ticker(ticker)
    hist = tk.history(period="1y", interval="1d")
    if hist.empty:
        return None, None, None
    close = hist["Close"].dropna()

    raw, info_status = fetch_info_with_retry(tk, ticker)
    info = {
        "name": raw.get("shortName") or ticker,
        "currency": raw.get("currency", ""),
        "target_mean": raw.get("targetMeanPrice"),
        "target_high": raw.get("targetHighPrice"),
        "target_low": raw.get("targetLowPrice"),
        "num_analysts": raw.get("numberOfAnalystOpinions"),
        "recommendation": raw.get("recommendationKey"),
    }

    if info_status == "fetch_failed":
        target_status = "fetch_failed"
    elif info["target_mean"] is not None:
        target_status = "covered"
    else:
        target_status = "no_coverage"

    return close, info, target_status


def ytd_change(close_series):
    """
    Calendar-year-to-date change, anchored to Jan 1 of the current year.
    Deliberately NOT fed into momentum_score -- YTD is a variable-length
    window (4 weeks in February, 11 months in December), which makes it
    incomparable across tickers and across time if blended into a fixed
    scoring formula. Display-only.
    """
    if close_series is None or len(close_series) == 0:
        return None
    current_year = close_series.index[-1].year
    ytd_slice = close_series[close_series.index.year == current_year]
    if len(ytd_slice) < 2:
        return None
    first, last = ytd_slice.iloc[0], ytd_slice.iloc[-1]
    if first == 0:
        return None
    return round((last - first) / first * 100, 2)


def momentum_score(c1d, c1w, c1m, rel_strength_1m):
    """Renamed from 'conviction' -- the name implied more than a pure
    price-momentum read actually delivers. See docstring above."""
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


def range_score(close_series):
    """Renamed from 'feasibility' -- the name implied a target-reachability
    model this dashboard doesn't have. This is purely 90-day range
    position. See docstring above."""
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
        close, info, _status = fetch_series_and_info(b_ticker)
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
            "change_ytd_pct": ytd_change(close),
        }
        print(f"OK  benchmark {b_ticker:10} {info['name']}")

    # 2. Fetch instruments
    results = []
    errors = []
    for ticker, category in TICKERS.items():
        try:
            close, info, target_status = fetch_series_and_info(ticker)
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

            target_mean = info.get("target_mean")
            upside_pct = None
            if target_mean is not None and last_price:
                upside_pct = round((target_mean - last_price) / last_price * 100, 2)

            results.append({
                "ticker": ticker,
                "category": category,
                "name": info["name"],
                "currency": info["currency"],
                "yfinance_url": YAHOO_QUOTE_URL.format(ticker=ticker),
                "last_price": last_price,
                "last_date": last_date,
                "change_1d_pct": c1d,
                "change_1w_pct": c1w,
                "change_1m_pct": c1m,
                "change_ytd_pct": ytd_change(close),
                "benchmark": bench_ticker,
                "rel_strength_1m_pct": rel_strength_1m,
                "momentum_score": momentum_score(c1d, c1w, c1m, rel_strength_1m),
                "range_score": range_score(close),
                "target_mean": target_mean,
                "target_high": info.get("target_high"),
                "target_low": info.get("target_low"),
                "num_analysts": info.get("num_analysts"),
                "recommendation": info.get("recommendation"),
                "upside_to_target_pct": upside_pct,
                "target_status": target_status,
                "history": history,
            })
            print(f"OK  {ticker:10} {info['name']} (target: {target_status})")
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
