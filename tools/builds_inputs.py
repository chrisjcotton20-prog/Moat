"""
Turn the daily all-US CSV (symbol,name,price,marketCap,volume,industry) into the
files the engine needs:
  * prices.csv          ticker,close            (throwaway, rebuilt each run)
  * meta.csv            ticker,sector,marketcap (throwaway, rebuilt each run)
  * price_history.csv   date,ticker,close       (COMMITTED, grows over time)

The history append is idempotent per date, so re-running on the same day won't
duplicate a snapshot. Robust CSV parsing (handles commas inside company names).

Usage: python tools/build_inputs.py [all.csv]
"""
import csv
import os
import sys
import datetime


def norm(sym: str) -> str:
    return sym.replace(".", "-").replace("/", "-").strip().upper()


def main(src="all.csv"):
    with open(src, newline="") as f:
        rows = list(csv.DictReader(f))

    with open("prices.csv", "w", newline="") as p, open("meta.csv", "w", newline="") as m:
        p.write("ticker,close\n")
        m.write("ticker,sector,marketcap\n")
        for r in rows:
            t = norm(r.get("symbol", ""))
            if not t:
                continue
            px = (r.get("price") or "").strip()
            mc = (r.get("marketCap") or "").strip()
            sector = (r.get("industry") or "").replace(",", " ").strip()
            try:
                if float(px) > 0:
                    p.write(f"{t},{px}\n")
            except ValueError:
                pass
            m.write(f"{t},{sector},{mc}\n")

    # append today's snapshot to the committed history, once per calendar day
    today = datetime.date.today().isoformat()
    hist = "price_history.csv"
    already = False
    if os.path.exists(hist):
        with open(hist) as f:
            last = None
            for line in f:
                if line.strip():
                    last = line
            if last and last.split(",", 1)[0] == today:
                already = True
    if not already:
        new = not os.path.exists(hist)
        with open(hist, "a", newline="") as h:
            if new:
                h.write("date,ticker,close\n")
            for r in rows:
                t = norm(r.get("symbol", ""))
                px = (r.get("price") or "").strip()
                if not t:
                    continue
                try:
                    if float(px) > 0:
                        h.write(f"{today},{t},{px}\n")
                except ValueError:
                    pass
        print(f"appended {today} snapshot to {hist}")
    else:
        print(f"{today} already in {hist}; skipped append")

    total = (sum(1 for _ in open(hist)) - 1) if os.path.exists(hist) else 0
    print(f"prices + meta written; price history rows: {total}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all.csv")
