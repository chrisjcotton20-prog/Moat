"""
Verify the engine end-to-end against SEC-shaped synthetic data.
Run: python test_engine.py
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from moat import edgar, metrics                       # noqa: E402
from moat.sample_data import make_sample              # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILS.append(name)


def approx(a, b, tol=0.01):
    return a is not None and abs(a - b) <= tol * max(1.0, abs(b))


def load(cik):
    path = os.path.join(os.path.dirname(__file__), "moat", "sample_data",
                        "facts", f"CIK{cik:010d}.json")
    with open(path) as f:
        return json.load(f)


def main():
    make_sample.write()
    prices = make_sample.PRICES

    print("\n--- Extraction ---")
    crns = edgar.extract_fundamentals(load(1001))
    check("extracts entity name", crns["entity"] == "Cornerstone Foods Inc")
    check("latest fiscal year is 2024", crns["fiscal_year"] == 2024, str(crns["fiscal_year"]))
    check("net income current = 1.08e9", approx(crns["net_income"], 1.08e9))
    check("shares via dei = 2.0e8", approx(crns["shares"], 2.0e8))
    check("bvps = equity/shares = 28.5", approx(crns["bvps"], 28.5))
    check("prior-year NI populated for F-score", approx(crns["prior"]["net_income"], 0.95e9))
    check("6 years of NI history", len(crns["ni_by_year"]) == 6, str(len(crns["ni_by_year"])))

    aztc = edgar.extract_fundamentals(load(1002))
    check("shares via us-gaap fallback = 5.0e8", approx(aztc["shares"], 5.0e8))

    gldn = edgar.extract_fundamentals(load(1003))
    check("gross profit via rev-COGS fallback = 1.05e9", approx(gldn["gross_profit"], 1.05e9),
          f"{gldn['gross_profit']}")

    print("\n--- Metrics: Cornerstone (expect BUY) ---")
    crns["ticker"] = "CRNS"
    r = metrics.compute(crns, prices["CRNS"])
    expect_graham = math.sqrt(22.5 * 5.40 * 28.5)
    check("graham number ~= 58.85", approx(r["graham"], expect_graham), f"{r['graham']:.2f}")
    check("margin of safety ~= 0.285", approx(r["mos"], (expect_graham - 42.10) / expect_graham))
    check("ROE ~= 18.9%", approx(r["roe"], 1.08e9 / 5.7e9))
    check("debt/equity ~= 0.333", approx(r["de"], 1.9e9 / 5.7e9))
    check("current ratio = 2.0", approx(r["currentRatio"], 2.0))
    check("FCF > 0", r["fcf"] > 0, f"{r['fcf']:.2e}")
    check("F-score >= 5", r["fScore"] >= 5, f"{r['fScore']}/{r['fScoreMax']}")
    check("all gates pass", r["passes"], str(r["gates"]))
    check("signal is BUY", r["signal"] == "BUY", r["signal"])

    print("\n--- Metrics: Aztec (expect RICH) ---")
    aztc["ticker"] = "AZTC"
    ra = metrics.compute(aztc, prices["AZTC"])
    check("passes quality gates", ra["passes"], str(ra["gates"]))
    check("price far above target -> RICH", ra["signal"] == "RICH",
          f"{ra['signal']} (mos={ra['mos']:.2f})")

    print("\n--- Metrics: Golden Mile (expect REJECTED) ---")
    gldn["ticker"] = "GLDN"
    rg = metrics.compute(gldn, prices["GLDN"])
    check("cheap: margin of safety positive", rg["mos"] > 0.3, f"{rg['mos']:.2f}")
    check("but debt gate fails", rg["gates"]["debt"] is False)
    check("and FCF gate fails", rg["gates"]["fcf"] is False)
    check("does NOT pass", rg["passes"] is False)
    check("signal is REJECTED", rg["signal"] == "REJECTED", rg["signal"])

    print("\n--- Sell / thesis signal ---")
    hold = metrics.sell_signal(r)          # BUY name held -> should be Hold
    trim = metrics.sell_signal(ra)         # RICH name -> should be Trim
    check("healthy holding -> Hold", hold["level"] == "hold", hold["label"])
    check("richly valued holding -> Trim", trim["level"] == "trim", trim["label"])

    print("\n--- Missing price handling ---")
    rnp = metrics.compute(crns, None)
    check("no price -> graham still computed, mos None", rnp["graham"] is not None and rnp["mos"] is None)

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILURE(S): {FAILS}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
