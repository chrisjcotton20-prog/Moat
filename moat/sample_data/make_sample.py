"""
Generate SEC-shaped companyfacts JSON + a prices CSV for testing, WITHOUT any
network. The JSON structure mirrors data.sec.gov/api/xbrl/companyfacts exactly
so the same extraction code runs here and on the real thing.
"""
import json
import os

HERE = os.path.dirname(__file__)


def dur(val, fy, filed):
    return {"start": f"{fy}-01-01", "end": f"{fy}-12-31", "val": val,
            "fy": fy, "fp": "FY", "form": "10-K", "filed": filed}


def inst(val, fy, filed):
    return {"end": f"{fy}-12-31", "val": val, "fy": fy, "fp": "FY",
            "form": "10-K", "filed": filed}


def usgaap(tag, points, unit="USD"):
    return {tag: {"label": tag, "units": {unit: points}}}


def build(cik, name, cur, prior, ni_history, shares, eps, *, shares_via_dei=True,
          gross_via_components=False):
    f, p = "2025-02-15", "2024-02-15"
    g = {}
    # net income: full history (duration)
    ni_pts = [dur(v, y, f"{y+1}-02-15") for y, v in sorted(ni_history.items())]
    g.update(usgaap("NetIncomeLoss", ni_pts))
    # two-year duration concepts
    g.update(usgaap("Revenues", [dur(prior["rev"], 2023, p), dur(cur["rev"], 2024, f)]))
    g.update(usgaap("OperatingIncomeLoss", [dur(prior["oi"], 2023, p), dur(cur["oi"], 2024, f)]))
    g.update(usgaap("NetCashProvidedByUsedInOperatingActivities",
                    [dur(prior["cfo"], 2023, p), dur(cur["cfo"], 2024, f)]))
    g.update(usgaap("PaymentsToAcquirePropertyPlantAndEquipment",
                    [dur(prior["capex"], 2023, p), dur(cur["capex"], 2024, f)]))
    g.update(usgaap("EarningsPerShareDiluted",
                    [dur(prior["eps"], 2023, p), dur(eps, 2024, f)], unit="USD/shares"))
    if gross_via_components:  # exercise the "gross profit from rev - COGS" fallback
        g.update(usgaap("CostOfRevenue",
                        [dur(prior["rev"] - prior["gp"], 2023, p),
                         dur(cur["rev"] - cur["gp"], 2024, f)]))
    else:
        g.update(usgaap("GrossProfit", [dur(prior["gp"], 2023, p), dur(cur["gp"], 2024, f)]))
    # two-year instant concepts
    g.update(usgaap("StockholdersEquity", [inst(prior["eq"], 2023, p), inst(cur["eq"], 2024, f)]))
    g.update(usgaap("Assets", [inst(prior["assets"], 2023, p), inst(cur["assets"], 2024, f)]))
    g.update(usgaap("AssetsCurrent", [inst(prior["ca"], 2023, p), inst(cur["ca"], 2024, f)]))
    g.update(usgaap("LiabilitiesCurrent", [inst(prior["cl"], 2023, p), inst(cur["cl"], 2024, f)]))
    g.update(usgaap("LongTermDebtNoncurrent", [inst(prior["ltd"], 2023, p), inst(cur["ltd"], 2024, f)]))

    facts = {"us-gaap": g}
    share_pts = [inst(shares, 2024, f)]
    if shares_via_dei:
        facts["dei"] = {"EntityCommonStockSharesOutstanding":
                        {"label": "shares", "units": {"shares": share_pts}}}
    else:
        g.update(usgaap("CommonStockSharesOutstanding", share_pts, unit="shares"))
    return {"cik": cik, "entityName": name, "facts": facts}


COMPANIES = [
    # BUY: quality, cheap. gross profit reported directly; shares via dei.
    build(1001, "Cornerstone Foods Inc",
          cur=dict(rev=5.5e9, gp=2.3e9, oi=1.1e9, eq=5.7e9, assets=9.0e9, ca=3.0e9,
                   cl=1.5e9, ltd=1.9e9, cfo=1.4e9, capex=0.3e9),
          prior=dict(rev=5.1e9, gp=2.05e9, oi=0.95e9, eq=5.2e9, assets=8.7e9, ca=2.8e9,
                     cl=1.55e9, ltd=2.0e9, cfo=1.2e9, capex=0.3e9, eps=4.75),
          ni_history={2019: 0.6e9, 2020: 0.7e9, 2021: 0.8e9, 2022: 0.9e9,
                      2023: 0.95e9, 2024: 1.08e9},
          shares=2.0e8, eps=5.40),
    # RICH: quality, expensive. shares via us-gaap tag instead of dei.
    build(1002, "Aztec Software Corp",
          cur=dict(rev=9.0e9, gp=7.1e9, oi=3.06e9, eq=1.18e10, assets=1.4e10, ca=6.0e9,
                   cl=1.7e9, ltd=0.8e9, cfo=3.6e9, capex=0.4e9),
          prior=dict(rev=7.8e9, gp=6.0e9, oi=2.5e9, eq=1.0e10, assets=1.25e10, ca=5.2e9,
                     cl=1.7e9, ltd=0.9e9, cfo=3.0e9, capex=0.4e9, eps=5.10),
          ni_history={2019: 1.5e9, 2020: 1.9e9, 2021: 2.3e9, 2022: 2.7e9,
                      2023: 2.55e9, 2024: 3.05e9},
          shares=5.0e8, eps=6.10, shares_via_dei=False),
    # REJECTED: cheap but junk. gross profit only via components; many gates fail.
    build(1003, "Golden Mile Mining Co",
          cur=dict(rev=5.0e9, gp=1.05e9, oi=0.30e9, eq=3.8e9, assets=10.5e9, ca=2.0e9,
                   cl=2.5e9, ltd=6.1e9, cfo=0.40e9, capex=0.54e9),
          prior=dict(rev=4.7e9, gp=1.0e9, oi=0.28e9, eq=3.9e9, assets=10.2e9, ca=1.9e9,
                     cl=2.3e9, ltd=5.9e9, cfo=0.45e9, capex=0.50e9, eps=1.05),
          ni_history={2019: -0.2e9, 2020: 0.1e9, 2021: 0.15e9, 2022: 0.18e9,
                      2023: 0.16e9, 2024: 0.165e9},
          shares=1.5e8, eps=1.10, gross_via_components=True),
]

PRICES = {"CRNS": 42.10, "AZTC": 210.40, "GLDN": 8.40}
CIK_TO_TICKER = {1001: "CRNS", 1002: "AZTC", 1003: "GLDN"}


def write():
    facts_dir = os.path.join(HERE, "facts")
    os.makedirs(facts_dir, exist_ok=True)
    for c in COMPANIES:
        with open(os.path.join(facts_dir, f"CIK{c['cik']:010d}.json"), "w") as fh:
            json.dump(c, fh)
    with open(os.path.join(HERE, "prices.csv"), "w") as fh:
        fh.write("ticker,close\n")
        for tk, px in PRICES.items():
            fh.write(f"{tk},{px}\n")
    with open(os.path.join(HERE, "ticker_map.json"), "w") as fh:
        json.dump({v: k for k, v in CIK_TO_TICKER.items()}, fh)
    print(f"Wrote {len(COMPANIES)} facts files + prices.csv to {HERE}")


if __name__ == "__main__":
    write()
