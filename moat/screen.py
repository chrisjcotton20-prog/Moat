"""
Moat screening engine -- command line entry point.

Run against a list of tickers (default) using the SEC Company Facts API, or
point --facts-dir at a folder of pre-downloaded companyfacts JSON files (e.g.
extracted from SEC's nightly companyfacts.zip) for whole-market screening
without per-ticker calls.

Examples
--------
    # screen a watchlist, prices from Stooq
    python -m moat.screen --tickers watchlist.txt --stooq \
        --user-agent "Moat you@example.com" --out results.json

    # whole market from the bulk dump, prices from a local CSV
    python -m moat.screen --facts-dir ./companyfacts --prices prices.csv \
        --out results.json
"""
from __future__ import annotations
import argparse
import json
import os
import sys

from . import config, edgar, prices as price_mod, metrics


def _load_tickers(path: str) -> list[str]:
    with open(path) as f:
        return [ln.strip().upper() for ln in f if ln.strip() and not ln.startswith("#")]


def _facts_from_dir(facts_dir: str):
    """Yield (facts_dict) for every *.json in a bulk-extracted directory."""
    for name in os.listdir(facts_dir):
        if name.lower().endswith(".json"):
            with open(os.path.join(facts_dir, name)) as f:
                try:
                    yield json.load(f)
                except json.JSONDecodeError:
                    continue


def build_record(facts: dict, ticker: str, price, sector=None) -> dict:
    rec = edgar.extract_fundamentals(facts)
    if not rec.get("ok"):
        return {"t": ticker, "skipped": True, "reason": rec.get("reason", "no data")}
    rec["ticker"] = ticker
    if sector:
        rec["sector"] = sector
    return metrics.compute(rec, price)


def run(args) -> dict:
    price_map = {}
    if args.prices:
        price_map = price_mod.load_prices_csv(args.prices)

    rows = []
    skipped = []

    if args.facts_dir:
        # Whole-market path: iterate local bulk files. Need a CIK->ticker map;
        # prices keyed by ticker. We read the ticker from the facts if present.
        tmap = {}
        if args.ticker_map:
            with open(args.ticker_map) as f:
                tmap = {int(v): k for k, v in json.load(f).items()}
        for facts in _facts_from_dir(args.facts_dir):
            cik = facts.get("cik")
            ticker = tmap.get(cik) or (facts.get("entityName", "")[:6].upper())
            price = price_map.get(ticker)
            if args.stooq and price is None:
                price = price_mod.fetch_stooq_last(ticker)
            row = build_record(facts, ticker, price)
            (skipped if row.get("skipped") else rows).append(row)
    else:
        tickers = _load_tickers(args.tickers)
        print(f"Resolving {len(tickers)} tickers to CIKs...", file=sys.stderr)
        tmap = edgar.get_ticker_map(args.user_agent)
        for i, tk in enumerate(tickers, 1):
            cik = tmap.get(tk)
            if not cik:
                skipped.append({"t": tk, "skipped": True, "reason": "ticker not in SEC map"})
                continue
            try:
                facts = edgar.get_company_facts(cik, args.user_agent)
            except Exception as e:  # noqa: BLE001
                skipped.append({"t": tk, "skipped": True, "reason": f"fetch error: {e}"})
                continue
            sector = edgar.get_sic_description(cik, args.user_agent) if args.with_sector else None
            price = price_map.get(tk)
            if args.stooq and price is None:
                price = price_mod.fetch_stooq_last(tk)
            row = build_record(facts, tk, price, sector)
            (skipped if row.get("skipped") else rows).append(row)
            print(f"  [{i}/{len(tickers)}] {tk}: {row.get('signal','-')}", file=sys.stderr)

    graded = [r for r in rows if r.get("price") is not None and r.get("graham") is not None]
    # implausible targets (bad share-count / scaling) never reach the shortlist
    flagged = sorted((r for r in graded if r["passes"] and not r.get("plausible", True)),
                     key=lambda r: r["mos"], reverse=True)
    shortlist = sorted((r for r in graded if r["passes"] and r.get("plausible", True)),
                       key=lambda r: r["mos"], reverse=True)
    rejected = sorted((r for r in graded if not r["passes"]),
                      key=lambda r: (r["mos"] if r["mos"] is not None else 9))

    return {
        "generated": args.stamp,
        "thresholds": config.GATES,
        "counts": {"screened": len(rows), "graded": len(graded),
                   "shortlist": len(shortlist), "rejected": len(rejected),
                   "flagged": len(flagged), "skipped": len(skipped)},
        "shortlist": shortlist,
        "rejected": rejected,
        "flagged": flagged,
        "no_price": [r["t"] for r in rows if r.get("price") is None],
        "skipped": skipped,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Moat value screener")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--tickers", help="text file, one ticker per line")
    src.add_argument("--facts-dir", help="dir of companyfacts JSON (bulk mode)")
    ap.add_argument("--prices", help="CSV with ticker,close")
    ap.add_argument("--stooq", action="store_true", help="fetch last close from Stooq when missing")
    ap.add_argument("--ticker-map", help="JSON {TICKER: cik} for bulk mode")
    ap.add_argument("--with-sector", action="store_true", help="also fetch SIC sector (extra call/ticker)")
    ap.add_argument("--user-agent", default=config.DEFAULT_USER_AGENT,
                    help="SEC requires a descriptive UA with contact email")
    ap.add_argument("--out", default="results.json")
    ap.add_argument("--stamp", default="", help="timestamp label for the output")
    args = ap.parse_args(argv)

    result = run(args)
    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, default=lambda o: None)
    c = result["counts"]
    print(f"\nDone. {c['shortlist']} on the shortlist, {c['rejected']} rejected, "
          f"{c['skipped']} skipped. Wrote {args.out}", file=sys.stderr)
    return result


if __name__ == "__main__":
    main()
