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

    print("\n--- Dual-class share-count bug (the MBUU case) ---")
    # Reported cover-page shares are wrong-by-1000x (a tiny share class);
    # income statement implies 20M shares. Without the fix, BVPS explodes.
    _prior = {"net_income": 45e6, "assets": 1.0e9, "cfo": 65e6, "long_term_debt": 100e6,
              "current_assets": 290e6, "current_liabilities": 150e6,
              "revenue": 760e6, "gross_profit": 285e6}
    dual = {"ticker": "DUAL", "entity": "Dual Class Co", "eps": 2.50,
            "net_income": 50e6, "equity": 500e6, "total_debt": 100e6, "assets": 1.05e9,
            "revenue": 800e6, "operating_income": 120e6, "gross_profit": 300e6,
            "current_assets": 300e6, "current_liabilities": 150e6,
            "cfo": 70e6, "capex": 20e6, "shares": 20000,  # <-- bad: should be ~20M
            "fiscal_year": 2024, "ni_by_year": {2024: 50e6}, "prior": _prior}
    rd = metrics.compute(dual, 25.00)
    check("share count corrected to ~20M via net income / EPS", approx(rd["shares"], 20e6, 0.05),
          f"{rd['shares']:.0f}")
    check("BVPS sane (~$25, not $25,000)", approx(rd["bvps"], 25.0, 0.05), f"{rd['bvps']:.2f}")
    check("Graham target sane (~$37-38, not five figures)", 30 < rd["graham"] < 45, f"{rd['graham']:.2f}")
    check("shareWarning flag raised", rd["shareWarning"] is True)
    check("still plausible after correction", rd["plausible"] is True)

    print("\n--- Plausibility backstop (bad data derivation can't fix) ---")
    bad = dict(dual); bad["equity"] = 50e12  # absurd equity scaling
    rb = metrics.compute(bad, 25.00)
    check("implausible target flagged", rb["plausible"] is False, f"graham={rb['graham']:.0f}")

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILURE(S): {FAILS}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
