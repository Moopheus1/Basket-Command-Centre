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
- **Per-instrument table** — grouped by category, alphabetical by ticker
  by default, with every column clickable to sort (click again to
  reverse). Sort state is independent per category table.
- **Light/dark theme toggle** — centered above the benchmark strip,
  preference persisted via `localStorage`.
- **Analyst price targets** — see "Price targets and yfinance links"
  below, including the `target_status` field that distinguishes genuine
  no-coverage instruments from transient fetch failures.

## Scoring methodology

Both scores are price-only. Neither uses options data. Formulas live in
`fetch_data.py` and are repeated here so they don't require reading code to
audit:

**Momentum score (0–100)**
- Trend alignment (40%): what fraction of the 1D/1W/1M changes share the
  majority sign.
- Magnitude (30%): average absolute change across 1D/1W/1M, capped at a 10%
  average move.
- Relative strength (30%): the instrument's 1M change minus its
  benchmark's 1M change, mapped from a ±10% range onto 0–1.

**Range score (0–100)**
- Position within the trailing 90-day price range. 100 = at the 90-day
  low (maximum room before hitting recent resistance). 0 = at the 90-day
  high (little room left, higher mean-reversion risk).
- This is a range-position proxy, not a target-price model. It is
  explicitly not the GEX-based feasibility score used in Basket Command
  Centre 2, and shouldn't be read as carrying the same weight.

Both are meant to be argued with, not trusted blindly — re-weight or
replace them in `fetch_data.py` as clarity about scoring develops
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

**Reliability note:** the yfinance `.info` call (which carries the target
data) was observed during this project's own testing to intermittently
fail with DNS resolution errors. A single-try fetch made those transient
failures indistinguishable from genuine "no analyst coverage." The fetch
script now retries a few times before giving up, and every instrument
carries a `target_status` field — `covered`, `no_coverage` (structural: 2
ETFs, 1 preference share, 1 thin-coverage REIT), or `fetch_failed`
(network issue on that run, not a real gap) — so the dashboard can show
the right message instead of a misleading blank.

## YTD column

Calendar-year-to-date change, anchored to 1 January of the current year.
Deliberately **not** fed into the momentum score, and not because it
wasn't considered — two concrete reasons:

1. YTD is a variable-length window (roughly 4 weeks in February, 11 months
   in December), which makes it incomparable across tickers and across
   the calendar year if baked into a fixed-weight formula.
2. Blending short-term (1D/1W/1M) and long-term (YTD) signals into one
   number obscures which horizon is actually driving the score. Keeping
   them as separate columns lets both be read together instead of
   collapsed into an ambiguous blend.

If a medium-term score input is wanted later, a rolling 3-month (63
trading day) window would be the better candidate than YTD specifically,
since it stays a constant length year-round.

Requires a full year of price history rather than the ~4 months needed
for the rest of the dashboard, so `fetch_data.py` pulls `period="1y"` from
yfinance for every ticker now.

## Column changes: trims and additions

The table was getting crowded, so three columns were cut to make room for
four higher-value ones:

**Removed:**
- **"As of"** — nearly identical across every row (last trading day),
  already stated once in the section header. Replaced with a small ⚠
  flag that only appears on a row if its date is stale relative to the
  rest of its category — so a genuinely broken fetch still gets caught
  without 25 rows of duplicate dates.
- **"Rel. Strength (1M)"** — already one of the three inputs baked into
  the momentum score (30% weight). Showing it again as its own column
  duplicated a signal already visible in Momentum.
- **"1W" change** — of the four %-change columns, the least distinct:
  too short to read as a trend, too long to read as "today." Trimmed
  down to 1D / 1M / YTD for short/medium/long horizons without the
  redundant middle step.

**Added** (sourced from yfinance, not computed here):
- **Yield** — trailing dividend/distribution yield. REITs are income
  vehicles; total return is price change plus distributions, and price-only
  momentum/range scores say nothing about the income component.
- **P/B** — price-to-book, the standard proxy for trading above or below
  NAV, which is how SGX REIT valuations are normally discussed.
- **Debt/Eq** — gearing proxy. SGX REITs carry a regulatory gearing cap;
  this flags balance-sheet and interest-rate sensitivity.
- **Next Earnings** — next scheduled results date where available.

`payout_ratio` is also pulled and present in `data.json` but was left off
the table itself to avoid re-crowding it — available if wanted later.

## Analyst target link

The analyst target price now links to Yahoo Finance's analyst breakdown
page (`/analysis`) — target range, recommendation trend, estimate history.
**This is not analyst thesis text.** Free data sources don't carry
brokerage report narratives, only the numeric consensus. If actual
research write-ups are wanted, that requires a different (likely paid)
source — not something this build currently has access to.

## Navigation and headers

- Every category section (HK Stock, HK/SGX ETF, SGX REIT, SGX Real Estate,
  SGX Pref Share) is now an anchor target. Clicking a category name in the
  Sector Rotation table jumps straight down to that category's table.
- A jump-button bar sits at the bottom of the page — one button per
  category (jumps back up to it) plus a "Top" button, so a page that's
  grown long with all these sections stays easy to navigate without
  scrolling back up manually.
- Section headers (category titles, Sector Rotation) are now bold and
  full-contrast text (white in dark mode, black in light mode) instead
  of the dim grey used before.

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
