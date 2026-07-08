"""
Pure metric math. Given the flat record from edgar.extract_fundamentals plus a
current price, produce every ratio, the Graham target, the F-score, the gate
results, and the buy signal -- matching the field names the app expects.
"""
from __future__ import annotations
import math
from typing import Optional

from . import config


def _safe_div(a, b):
    if a is None or b in (None, 0):
        return None
    return a / b


def graham_number(eps: Optional[float], bvps: Optional[float]) -> Optional[float]:
    if eps is None or bvps is None or eps <= 0 or bvps <= 0:
        return None
    return math.sqrt(config.GRAHAM_MULTIPLIER * eps * bvps)


def piotroski_fscore(rec: dict) -> tuple[int, int]:
    """
    Return (score, max_possible). Each of the 9 tests is scored only when the
    data it needs is present; max_possible drops when history is missing, so a
    shallow filer isn't silently penalised.
    """
    p = rec["prior"]
    score = 0
    possible = 0

    def test(condition_inputs, passed):
        nonlocal score, possible
        if all(x is not None for x in condition_inputs):
            possible += 1
            if passed():
                score += 1

    ni, assets, cfo = rec["net_income"], rec["assets"], rec["cfo"]
    p_ni, p_assets, p_cfo = p["net_income"], p["assets"], p["cfo"]
    roa = _safe_div(ni, assets)
    p_roa = _safe_div(p_ni, p_assets)

    # Profitability
    test([ni], lambda: ni > 0)
    test([cfo], lambda: cfo > 0)
    test([roa, p_roa], lambda: roa > p_roa)
    test([cfo, ni], lambda: cfo > ni)  # accruals: cash beats reported earnings

    # Leverage, liquidity, dilution
    ltd_ratio = _safe_div(rec["total_debt"], assets)
    p_ltd_ratio = _safe_div(p["long_term_debt"], p_assets)
    test([ltd_ratio, p_ltd_ratio], lambda: ltd_ratio <= p_ltd_ratio)

    cr = _safe_div(rec["current_assets"], rec["current_liabilities"])
    p_cr = _safe_div(p["current_assets"], p["current_liabilities"])
    test([cr, p_cr], lambda: cr > p_cr)

    # (Share issuance test omitted unless a prior share count is available;
    #  most single-snapshot pulls can't see it, so we don't fabricate it.)

    # Efficiency
    gm = _safe_div(rec["gross_profit"], rec["revenue"])
    p_gm = _safe_div(p["gross_profit"], p["revenue"])
    test([gm, p_gm], lambda: gm > p_gm)

    turn = _safe_div(rec["revenue"], assets)
    p_turn = _safe_div(p["revenue"], p_assets)
    test([turn, p_turn], lambda: turn > p_turn)

    return score, possible


def profitable_years(rec: dict) -> tuple[int, int]:
    """Count of positive-net-income years available, and total years available."""
    ni = rec.get("ni_by_year", {})
    if not ni:
        return 0, 0
    return sum(1 for v in ni.values() if v and v > 0), len(ni)


def compute(rec: dict, price: Optional[float], thresholds: dict = None) -> dict:
    t = thresholds or config.GATES
    eps, bvps = rec.get("eps"), rec.get("bvps")
    equity, debt = rec.get("equity"), rec.get("total_debt")
    ni = rec.get("net_income")

    roe = _safe_div(ni, equity)
    roic = _safe_div(ni, (equity + debt)) if (equity is not None and debt is not None) else _safe_div(ni, equity)
    op_margin = _safe_div(rec.get("operating_income"), rec.get("revenue"))
    gross_margin = _safe_div(rec.get("gross_profit"), rec.get("revenue"))
    de = _safe_div(debt, equity)
    current_ratio = _safe_div(rec.get("current_assets"), rec.get("current_liabilities"))
    fcf = None
    if rec.get("cfo") is not None and rec.get("capex") is not None:
        fcf = rec["cfo"] - rec["capex"]

    graham = graham_number(eps, bvps)
    mcap = (price * rec["shares"]) if (price is not None and rec.get("shares")) else None
    fcf_yield = _safe_div(fcf, mcap)
    pe = _safe_div(price, eps)
    pb = _safe_div(price, bvps)
    mos = _safe_div((graham - price), graham) if (graham is not None and price is not None) else None

    fscore, fscore_max = piotroski_fscore(rec)
    pos_years, years_avail = profitable_years(rec)

    gates = {
        "profitable": (eps is not None and eps > 0),
        "roe": (roe is not None and roe >= t["roe_min"]),
        "fcf": (fcf is not None and fcf > 0),
        "opMargin": (op_margin is not None and op_margin > t["op_margin_min"]),
        "fScore": (fscore >= t["fscore_min"]),
        "debt": (de is not None and de < t["debt_to_equity_max"]),
        "liquidity": (current_ratio is not None and current_ratio > t["current_ratio_min"]),
        "consistent": (years_avail >= t["min_years_of_data"]
                       and pos_years >= min(t["min_profitable_years"], years_avail)),
    }
    passes = all(gates.values())

    if not passes or mos is None:
        signal = "REJECTED" if not passes else "WATCH"
    elif mos >= config.BUY_MARGIN:
        signal = "BUY"
    elif mos >= config.WATCH_FLOOR:
        signal = "WATCH"
    else:
        signal = "RICH"

    return {
        "t": rec.get("ticker"),
        "name": rec.get("entity"),
        "sector": rec.get("sector", "—"),
        "price": price,
        "eps": eps,
        "bvps": bvps,
        "graham": graham,
        "mos": mos,
        "pe": pe,
        "pb": pb,
        "roe": roe,
        "roic": roic,
        "de": de,
        "fcfYield": fcf_yield,
        "grossMargin": gross_margin,
        "opMargin": op_margin,
        "fScore": fscore,
        "fScoreMax": fscore_max,
        "currentRatio": current_ratio,
        "yearsPos": pos_years,
        "yearsData": years_avail,
        "marketCap": mcap,
        "fcf": fcf,
        "fiscalYear": rec.get("fiscal_year"),
        "gates": gates,
        "passes": passes,
        "signal": signal,
        "dataComplete": (fscore_max >= 6 and years_avail >= 5),
    }


def sell_signal(row: dict) -> dict:
    """Thesis check for a holding already computed by `compute`."""
    price, graham = row.get("price"), row.get("graham")
    if not row["passes"]:
        return {"label": "Review — thesis weakening", "level": "sell",
                "why": "A quality or strength gate that held at purchase no longer passes."}
    if graham and price and price > graham * config.RICH_LINE:
        return {"label": "Trim — richly valued", "level": "trim",
                "why": f"Price is above the richly-valued line (${graham * config.RICH_LINE:,.2f})."}
    if graham and price and price > graham * config.ABOVE_FAIR_LINE:
        return {"label": "Watch — above fair value", "level": "watch",
                "why": "Trading over fair value but not extended. No action needed."}
    return {"label": "Hold", "level": "hold",
            "why": "Business still compounding and price is reasonable."}
