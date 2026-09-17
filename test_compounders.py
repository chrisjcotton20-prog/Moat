"""Verify the Overlooked Compounders lens. Run: python test_compounders.py"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from moat import compounders  # noqa: E402

FAILS = []
def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    if not cond: FAILS.append(name)

def row(t, sector, pe, growth, **kw):
    """A record shaped like metrics.compute output, quality-passing by default."""
    r = dict(t=t, name=t, sector=sector, price=100.0, eps=5.0,
             roe=0.20, opMargin=0.20, de=0.4, fcf=1e8, fScore=8,
             marketCap=5e9, plausible=True, pe=pe,
             revenueCagr=growth, earningsCagr=growth)
    r.update(kw); return r

def main():
    rows = [
        # Tech sector: 4 quality names to form a peer median; PEs 30/28/32 + a cheap 20
        row("HIGH1", "Tech", 30, 0.15),
        row("HIGH2", "Tech", 28, 0.15),
        row("HIGH3", "Tech", 32, 0.15),
        row("CHEAP", "Tech", 20, 0.15),   # cheap vs peers AND low PEG -> BUY
        row("ONEONLY", "Tech", 20, 0.08), # cheap vs peers but PEG high (20/8=2.5) -> WATCH
        # gate failures -> excluded entirely
        row("LOWROE", "Tech", 18, 0.15, roe=0.10),      # ROE < 15%
        row("NOGROW", "Tech", 15, 0.02),                # growth < 7%
        row("LEVERED", "Tech", 15, 0.15, de=1.4),       # debt/equity > 1.0
        row("SMALL", "Tech", 15, 0.15, marketCap=4e8),  # below size floor
    ]
    res = compounders.evaluate(rows)
    cands = {c["t"]: c for c in res["candidates"]}

    print("--- Gates ---")
    check("low-ROE name excluded", "LOWROE" not in cands)
    check("no-growth name excluded", "NOGROW" not in cands)
    check("over-levered name excluded", "LEVERED" not in cands)
    check("micro-cap excluded", "SMALL" not in cands)
    check("quality names retained", {"HIGH1","HIGH2","HIGH3","CHEAP","ONEONLY"} <= set(cands))

    print("\n--- Peer-relative valuation ---")
    med = cands["CHEAP"]["sectorMedianPE"]
    check("sector median P/E computed (~29)", 28 <= med <= 31, f"{med}")
    check("CHEAP shows a peer discount (~31%)", cands["CHEAP"]["peerDiscount"] > 0.25,
          f"{cands['CHEAP']['peerDiscount']:.2f}")
    check("expensive peer HIGH3 shows negative/near-zero discount",
          cands["HIGH3"]["peerDiscount"] <= 0.05)

    print("\n--- Signals (Buy = cheap on both, Watch = one, Fair = neither) ---")
    check("CHEAP -> BUY (discount + low PEG)", cands["CHEAP"]["cSignal"] == "BUY",
          f"peg={cands['CHEAP']['peg']:.2f}")
    check("ONEONLY -> WATCH (discount only, PEG too high)", cands["ONEONLY"]["cSignal"] == "WATCH",
          f"peg={cands['ONEONLY']['peg']:.2f}")
    check("HIGH3 -> FAIR (priced in line, no discount)", cands["HIGH3"]["cSignal"] == "FAIR")

    print("\n--- Ranking ---")
    check("ranked by peer discount (CHEAP first)", res["candidates"][0]["t"] == "CHEAP")

    print("\n--- Price-lag signal (when history present) ---")
    check("no history -> laggedPeers is None", cands["CHEAP"]["laggedPeers"] is None)
    check("no history -> counts flag false", res["counts"]["hasPriceHistory"] is False)
    returns = {"HIGH1": 0.40, "HIGH2": 0.35, "HIGH3": 0.42, "CHEAP": 0.05, "ONEONLY": 0.30}
    res2 = compounders.evaluate(rows, returns=returns)
    c2 = {c["t"]: c for c in res2["candidates"]}
    check("CHEAP flagged as having lagged peers", c2["CHEAP"]["laggedPeers"] is True,
          f"lag={c2['CHEAP']['priceLag']:.2f}")
    check("HIGH3 (led peers) not flagged as lagged", c2["HIGH3"]["laggedPeers"] is False)
    check("counts flag true with history", res2["counts"]["hasPriceHistory"] is True)

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILURE(S): {FAILS}"); sys.exit(1)
    print("All compounder checks passed.")

if __name__ == "__main__":
    main()
