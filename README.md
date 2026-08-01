# HK / SGX Command Centre

A second, standalone dashboard alongside **Basket Command Centre 2**, built for
a watchlist of Hong Kong and Singapore-listed instruments. Same pipeline
pattern as the original: GitHub Actions → yfinance → `data.json` → static
`index.html`, refreshed via an external cron-job.org dispatcher.

## Genesis

This started as a request to build a dashboard for "HK stocks and SEA unit
trusts," modelled on Fundsupermart Singapore. That framing turned out to be
wrong in a way that changed the whole build, so it's worth recording here
rather than losing it in chat history:

1. **The unit trust half was never buildable as originally scoped.**
   Fundsupermart/FSM Global runs as a JS-rendered SPA with no static NAV
   table, and — as a MAS-regulated brokerage — scraping it sits in ToS grey
   territory that was never fully resolved. A public, scrapable alternative
   was found (Maybank Singapore's unit trust price list, ~35 fund houses,
   daily-updated static HTML), but it never got used because of point 3
   below.

2. **Insurer-run ILP fund centres are explicitly off the table.** Tokio
   Marine's public Fund Centre carries a written prohibition on
   redistributing or copying its Morningstar-sourced data in any form. That
   is a hard stop, not a risk to weigh — no scraper was built against it or
   any similarly licensed insurer fund centre (HSBC Life's fund prices page
   was also left unresolved: it sits inside their authenticated app portal
   and was never confirmed scrapable).

3. **The actual watchlist supplied turned out to contain zero unit trusts.**
   Every ticker submitted (`1211.HK`, `9618.HK`, `3067.HK`, and twenty
   `.SI` tickers) is an exchange-traded instrument — HK stocks, two HSTECH
   ETFs, and a set of SGX-listed REITs, Business Trusts, and one
   preference share. All of it prices continuously on the exchange and
   pulls directly from yfinance, identical in structure to the HK stock
   half. The unit-trust research above turned out to be unnecessary for
   this watchlist — kept here in case a genuine unit trust gets added
   later, since the groundwork (and the dead ends) won't need repeating.

4. **GEX was requested, tested, and confirmed not currently possible.**
   A live call to the FlashAlpha endpoint used in Basket Command Centre 2
   returned `no_cached_data` for every HK/SGX ticker tested, against a
   working response for a US ticker (AAPL) as baseline. Beyond that
   provider gap, most SGX REITs have no listed single-stock options market
   at all, so there may be no options chain to derive gamma exposure from
   regardless of provider. GEX is not in this dashboard. If it's wanted
   later, it needs its own research task to find and vet an HK-options
   data source — not a retrofit of this build.

5. **Benchmarks and scoring were built to replace, not imitate, what
   Basket Command Centre 2 does with SPY/QQQ/IWM.** The US dashboard's
   exact conviction/feasibility formula (built on GEX inputs) isn't
   available here, so this dashboard uses a documented, price-only
   substitute — see "Scoring methodology" below. It should be treated as a
   different tool with a similar shape, not a port of the original logic.

## What's in the dashboard

- **Benchmark strip** — `^STI` (SG Index), `^HSI` (HK Index), `3067.HK`
  (iShares HSTECH ETF, used as the Tech Index proxy — Yahoo has no working
  `^HSTECH` ticker). Direct index tickers were used over ETF proxies where
  possible to avoid NAV tracking error and dividend drag.
- **Sector rotation panel** — average 1D/1W/1M return per category, compared
  against each category's assigned benchmark (HK-listed names vs `^HSI`,
  SGX-listed names vs `^STI`).
- **Per-instrument table** — grouped by category, sorted by conviction
  score, with 1D/1W/1M change, relative strength vs benchmark, and both
  scores below.

## Scoring methodology

Both scores are price-only. Neither uses options data. Formulas live in
`fetch_data.py` and are repeated here so they don't require reading code to
audit:

**Conviction score (0–100)**
- Trend alignment (40%): what fraction of the 1D/1W/1M changes share the
  majority sign.
- Magnitude (30%): average absolute change across 1D/1W/1M, capped at a 10%
  average move.
- Relative strength (30%): the instrument's 1M change minus its
  benchmark's 1M change, mapped from a ±10% range onto 0–1.

**Feasibility score (0–100)**
- Position within the trailing 90-day price range. 100 = at the 90-day
  low (maximum room before hitting recent resistance). 0 = at the 90-day
  high (little room left, higher mean-reversion risk).
- This is a range-position proxy, not a target-price model. It is
  explicitly not the GEX-based feasibility score used in Basket Command
  Centre 2, and shouldn't be read as carrying the same weight.

Both are meant to be argued with, not trusted blindly — re-weight or
replace them in `fetch_data.py` as conviction (no pun intended) develops
about what's actually useful.

A collapsible guidance panel with this same explanation lives directly in
`index.html` now, so it doesn't require opening this file to understand
what the scores mean. Note: that panel's wording was written fresh for
this dashboard — it is not a copy of whatever guidance text exists in
Basket Command Centre 2, which wasn't visible to reference directly.

## Price targets and yfinance links

Each ticker links directly to its Yahoo Finance quote page for deeper
research. Analyst price targets (mean/high/low, analyst count, consensus
recommendation) are pulled from yfinance's own aggregation of sell-side
estimates — not computed by this dashboard. Coverage was checked before
building this: 21 of 25 instruments have target data, and the 4 without it
are structurally expected gaps, not errors — `3067.HK` and `HST.SI` are
ETFs, `C70.SI` is a preference share (none of these get analyst equity
targets by definition), and `SEB.SI` is a thinly-covered REIT with zero
analysts. Where coverage exists, analyst counts run as low as 3 — check the
count before weighting a target; a 3-analyst consensus swings hard on a
single revision.

There are still no unit trusts tracked (see Genesis, point 3), so no price
targets apply to that category — analyst price targets are a sell-side
equity coverage concept and don't exist for open-ended NAV-priced funds
even where unit trusts do get added later.

## Known gaps and quirks

- `MXNU.SI` (Elite UK REIT) prices in GBP and `CMOU.SI` (Keppel Pacific Oak
  US REIT) prices in USD — both sit in the same table as SGD-denominated
  instruments. Percentage changes are still valid per-instrument; absolute
  price comparisons across rows are not.
- No unit trusts are currently tracked. If any get added later, they will
  need a different fetch path — see "Genesis," point 3 — since yfinance
  does not reliably serve NAV-priced instruments (confirmed dead end: Yahoo
  shows quote pages for some Morningstar-sourced fund identifiers but the
  underlying data API returns empty history).
- No GEX. See "Genesis," point 4.

## Architecture

```
tickers.py              → watchlist + benchmark + category-benchmark config
fetch_data.py            → pulls yfinance data, computes changes/scores/rotation,
                            writes data.json (saves to /tmp first, then moves
                            into place — same race-condition guard as
                            Basket Command Centre 2)
data.json                 → output consumed by the dashboard
index.html               → static dashboard, fetches data.json client-side
.github/workflows/update.yml → runs fetch_data.py on repository_dispatch
                                 or manual workflow_dispatch
requirements.txt         → yfinance
```

## Setup

1. Create a new GitHub repo (e.g. `Basket-Command-Centre-HK-SGX`), public,
   with GitHub Pages enabled (Settings → Pages → deploy from `main`, root).
2. Push the contents of this folder as-is.
3. Create a fine-grained PAT scoped to this repo only, `actions: write`
   permission (Settings → Developer settings → Fine-grained tokens).
4. Set up a cron-job.org job (same external-dispatcher pattern used for
   Basket Command Centre 2, since native Actions scheduling has proven
   unreliable):
   - URL: `https://api.github.com/repos/YOUR_USERNAME/REPO_NAME/dispatches`
   - Method: `POST`
   - Headers: `Authorization: Bearer YOUR_PAT`,
     `Accept: application/vnd.github+json`
   - Body: `{"event_type": "update-data"}`
   - Schedule: after SGX/HKEX close (~5pm SGT) or first thing in the
     morning — there's no reason to run this on the US pre-market
     schedule used for Basket Command Centre 2.
