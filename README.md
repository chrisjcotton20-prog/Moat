# Moat — screening engine

The engine behind the Moat screener. It reads company fundamentals from
**SEC EDGAR** and prices from **Stooq**, computes the quality/strength gates,
the Graham buy target, the Piotroski F-score, and a buy/sell signal for every
company, and writes a `results.json` that the Moat app reads directly.

No third-party packages — pure Python 3.9+ standard library.

## Why you run it, not me
The build sandbox can't reach `sec.gov` or `stooq.com`. So the logic was
verified here against synthetic SEC-shaped data (`python test_engine.py`), and
you run it against the live sites from your own machine or a GitHub Action.

## Two ways to run

### 1. Watchlist mode (start here)
Screens a list of tickers via SEC's per-company API. Best for a first real run.

```bash
# watchlist.txt = one ticker per line
python -m moat.screen \
  --tickers watchlist.txt \
  --stooq \
  --user-agent "Moat personal screener you@example.com" \
  --out results.json
```

**The `--user-agent` is not optional.** SEC returns HTTP 403 without a
descriptive User-Agent that includes a contact email. Put your own in.

Add `--with-sector` to also fetch each company's SIC sector (one extra call per
ticker). Add `--prices prices.csv` (columns `ticker,close`) to supply your own
prices instead of Stooq.

### 2. Bulk / whole-market mode
For the full market without per-ticker rate limits, download SEC's nightly
`companyfacts.zip`, unzip it, and point the engine at the folder:

```bash
# one-time-ish: grab and unzip the bulk dump (~1GB unzipped)
curl -A "Moat you@example.com" \
  https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip -o cf.zip
unzip -q cf.zip -d companyfacts

python -m moat.screen \
  --facts-dir companyfacts \
  --prices prices.csv \
  --ticker-map ticker_map.json \
  --out results.json
```

`ticker_map.json` is `{ "AAPL": 320193, ... }` — build it once from
`https://www.sec.gov/files/company_tickers.json`. For prices at this scale,
Stooq's bulk per-exchange CSV downloads are far kinder than per-symbol calls.

## Output
`results.json` contains `shortlist` (passed every gate, ranked by margin of
safety), `rejected` (graded but failed a gate, with which gates failed),
`no_price`, `skipped`, and the `thresholds` used. Each row carries the same
fields the app renders: `graham`, `mos`, `roe`, `roic`, `de`, `fScore`,
`gates`, `signal`, and so on.

## Tuning the screen
Every dial lives in `moat/config.py` — the gate thresholds (ROE floor,
debt/equity ceiling, F-score minimum, years profitable), the Graham multiplier,
and the buy/watch/rich and sell/trim bands. Change a number, re-run, done.

## Honest limitations
- **XBRL is messy.** Companies tag concepts differently; the engine tries
  fallback tags but some filers will still come back incomplete and get
  skipped. `dataComplete` flags shallow records.
- **Debt is approximated** as long-term + current portion + short-term
  borrowings; unusual capital structures may need a tweak.
- **The Graham Number is conservative** and rejects most capital-light growth
  compounders. That's by design for classic value; loosen it in config if you
  want to catch more Munger-style names.
- Fundamentals lag by a quarter (they're from the last 10-K); prices are
  end-of-day. This is a long-hold screen, not a live quote board.

## Test
```bash
python test_engine.py
```
Regenerates the synthetic companies and checks extraction, Graham math, gates,
F-score, and signals against hand-computed values.

---

## The dashboard (index.html)

`index.html` is the Moat UI — a single self-contained file, no build step. It
reads `public/results.json` and renders the shortlist, per-stock detail, and a
Holdings tab (saved in your browser). Before the first screen runs it shows
built-in sample data with a banner.

### Deploy it (browser only)
1. Put `index.html` at the repo root (it's already here).
2. **GitHub Pages:** repo Settings > Pages > Deploy from a branch > `main` / root.
   Open the URL it gives you. (Pages needs a public repo on the free plan.)
3. **Vercel (alternative):** import the repo, framework preset "Other", no build
   command. Works with private repos too.

## Choosing what to screen
The nightly workflow has a `universe` dropdown (Actions > Run workflow):
- **sp500** — the S&P 500 (~503 names), fetched fresh each run. Start here.
- **all** — every SEC filer (~13k). Works, but per-symbol prices make it slow;
  best on a public repo. The proper full-market fix is bulk Stooq prices.
- **watchlist** — your own `watchlist.txt`.

## Note on the workflow
The ticker list is written to `screen_list.txt` (git-ignored) so `watchlist.txt`
is never modified and the working tree stays clean. The commit step uses
`git pull --rebase --autostash` so a browser commit made mid-run can't cause a
push rejection.
