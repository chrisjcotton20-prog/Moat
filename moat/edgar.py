"""
SEC EDGAR access + the extraction layer that turns raw XBRL facts into a
tidy per-company record. The fetch functions hit the network; the extraction
functions are pure and are what the test suite exercises against sample JSON
shaped exactly like the real API output.
"""
from __future__ import annotations
import json
import time
import urllib.request
from datetime import date
from typing import Optional

from . import config

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"


# --------------------------------------------------------------------------- #
# Network (not exercised in the sandbox; run these on your own machine)        #
# --------------------------------------------------------------------------- #
def _get_json(url: str, user_agent: str) -> dict:
    last_err = None
    for attempt in range(config.SEC_MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": user_agent,
                                                       "Accept-Encoding": "gzip, deflate"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    raw = gzip.decompress(raw)
                return json.loads(raw)
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def get_ticker_map(user_agent: str) -> dict[str, int]:
    """Return {TICKER: cik_int} for every filer SEC knows about."""
    data = _get_json(TICKER_MAP_URL, user_agent)
    out = {}
    for row in data.values():
        out[row["ticker"].upper()] = int(row["cik_str"])
    return out


def get_company_facts(cik: int, user_agent: str) -> dict:
    time.sleep(config.SEC_REQUEST_DELAY)
    return _get_json(FACTS_URL.format(cik=cik), user_agent)


def get_sic_description(cik: int, user_agent: str) -> Optional[str]:
    time.sleep(config.SEC_REQUEST_DELAY)
    try:
        return _get_json(SUBMISSIONS_URL.format(cik=cik), user_agent).get("sicDescription")
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# Extraction (pure functions -- the tested core)                              #
# --------------------------------------------------------------------------- #
def _days(a: str, b: str) -> int:
    ya, ma, da = map(int, a.split("-"))
    yb, mb, db = map(int, b.split("-"))
    return (date(yb, mb, db) - date(ya, ma, da)).days


def _annual_series(units: list[dict], instant: bool) -> dict[int, float]:
    """
    Collapse a concept's unit points into {fiscal_year: value}, using only
    annual 10-K figures and preferring the most recently *filed* value for each
    year so that restatements win. Duration concepts (income, cash flow) are
    filtered to ~full-year periods so quarterly points don't leak in.
    """
    best: dict[int, tuple[str, float]] = {}  # fy -> (filed, val)
    for u in units:
        if u.get("form") not in ("10-K", "10-K/A"):
            continue
        fy = u.get("fy")
        val = u.get("val")
        if fy is None or val is None:
            continue
        if not instant:
            s, e = u.get("start"), u.get("end")
            if not s or not e or _days(s, e) < 300:
                continue
        else:
            if not u.get("end"):
                continue
        filed = u.get("filed", "")
        if fy not in best or filed > best[fy][0]:
            best[fy] = (filed, float(val))
    return {fy: v[1] for fy, v in best.items()}


def _find_concept(facts: dict, keys: list[str], instant: bool,
                  namespace: str = "us-gaap") -> dict[int, float]:
    """Try each fallback tag; return the annual series of the first that hits."""
    block = facts.get("facts", {}).get(namespace, {})
    for key in keys:
        node = block.get(key)
        if not node:
            continue
        units = node.get("units", {})
        # pick the right unit (USD, USD/shares, or shares)
        for unit_key in ("USD", "USD/shares", "shares"):
            if unit_key in units:
                series = _annual_series(units[unit_key], instant)
                if series:
                    return series
    return {}


def _latest_point(facts: dict, keys: list[str], namespace: str = "us-gaap") -> Optional[float]:
    """Most recent value of a concept across ALL forms (for shares outstanding)."""
    block = facts.get("facts", {}).get(namespace, {})
    for key in keys:
        node = block.get(key)
        if not node:
            continue
        for unit_key, points in node.get("units", {}).items():
            dated = [(p.get("end", ""), p.get("val")) for p in points if p.get("val") is not None]
            if dated:
                dated.sort()
                return float(dated[-1][1])
    return None


def _series(facts, name):
    return _find_concept(facts, config.CONCEPTS[name], name in config.INSTANT_CONCEPTS)


def extract_fundamentals(facts: dict) -> dict:
    """
    Turn a full companyfacts payload into a flat record with current-year and
    prior-year figures. Missing fields come back as None; the caller decides
    how to treat incompleteness.
    """
    ni = _series(facts, "net_income")
    rev = _series(facts, "revenue")
    gp = _series(facts, "gross_profit")
    cor = _series(facts, "cost_of_revenue")
    oi = _series(facts, "operating_income")
    eq = _series(facts, "equity")
    ast = _series(facts, "assets")
    ca = _series(facts, "assets_current")
    cl = _series(facts, "liabilities_current")
    ltd = _series(facts, "long_term_debt")
    ltdc = _series(facts, "long_term_debt_current")
    std = _series(facts, "short_term_debt")
    cfo = _series(facts, "cfo")
    capex = _series(facts, "capex")
    eps_d = _series(facts, "eps_diluted")
    eps_b = _series(facts, "eps_basic")

    years = sorted(set(ni) | set(eq) | set(rev), reverse=True)
    if not years:
        return {"ok": False, "reason": "no annual fundamentals found"}
    cy = years[0]
    py = years[1] if len(years) > 1 else None

    def g(series, yr):
        return series.get(yr) if yr is not None else None

    def gross(yr):
        if g(gp, yr) is not None:
            return g(gp, yr)
        if g(rev, yr) is not None and g(cor, yr) is not None:
            return g(rev, yr) - g(cor, yr)
        return None

    def total_debt(yr):
        parts = [g(ltd, yr), g(ltdc, yr), g(std, yr)]
        present = [p for p in parts if p is not None]
        return sum(present) if present else None

    shares = _latest_point(facts, config.CONCEPTS["shares_outstanding_dei"], namespace="dei") \
        or _latest_point(facts, config.CONCEPTS["shares_outstanding"])

    eps = g(eps_d, cy)
    if eps is None:
        eps = g(eps_b, cy)
    if eps is None and g(ni, cy) is not None and shares:
        eps = g(ni, cy) / shares

    equity = g(eq, cy)
    bvps = (equity / shares) if (equity is not None and shares) else None

    rec = {
        "ok": True,
        "entity": facts.get("entityName"),
        "cik": facts.get("cik"),
        "fiscal_year": cy,
        "shares": shares,
        "eps": eps,
        "bvps": bvps,
        "net_income": g(ni, cy),
        "revenue": g(rev, cy),
        "gross_profit": gross(cy),
        "operating_income": g(oi, cy),
        "equity": equity,
        "assets": g(ast, cy),
        "current_assets": g(ca, cy),
        "current_liabilities": g(cl, cy),
        "total_debt": total_debt(cy),
        "cfo": g(cfo, cy),
        "capex": g(capex, cy),
        # prior-year slice for Piotroski
        "prior": {
            "net_income": g(ni, py),
            "revenue": g(rev, py),
            "gross_profit": gross(py),
            "assets": g(ast, py),
            "current_assets": g(ca, py),
            "current_liabilities": g(cl, py),
            "long_term_debt": g(ltd, py),
            "cfo": g(cfo, py),
            "shares_series": shares,  # placeholder; share issuance handled below
        },
        # multi-year net income for the "years profitable" gate
        "ni_by_year": ni,
        "eps_by_year": {**eps_b, **eps_d},
        "prior_year": py,
    }
    return rec
