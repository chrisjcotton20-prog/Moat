"""
The "Overlooked Compounders" lens.

A RELATIVE screen (unlike Graham's absolute one): it hunts for strong, growing,
financially-sound businesses that trade cheap *versus comparable-quality peers*
and cheap *relative to their own growth* -- laggards due for a catch-up.

Inputs are the per-stock records produced by metrics.compute (which already
carry roe, opMargin, de, fScore, fcf, pe, marketCap, and now growth rates).
Peer comparisons are cross-sectional, so this operates on the whole set at once.
"""
from __future__ import annotations
from statistics import median
from typing import Optional

from . import config


def _growth(r) -> Optional[float]:
    vals = [x for x in (r.get("revenueCagr"), r.get("earningsCagr")) if x is not None]
    return max(vals) if vals else None


def gate_check(r, t=None):
    """Return (checks dict, passes bool, growth). Strong-footing + actually-compounding."""
    g = t or config.COMPOUNDERS
    growth = _growth(r)
    checks = {
        "profitable": (r.get("eps") or 0) > 0,
        "roe": (r.get("roe") is not None and r["roe"] >= g["roe_min"]),
        "opMargin": (r.get("opMargin") is not None and r["opMargin"] > g["op_margin_min"]),
        "debt": (r.get("de") is not None and r["de"] < g["debt_to_equity_max"]),
        "fcf": (r.get("fcf") is not None and r["fcf"] > 0),
        "fScore": (r.get("fScore") or 0) >= g["fscore_min"],
        "growth": (growth is not None and growth >= g["growth_min"]),
        "size": (r.get("marketCap") is not None and r["marketCap"] >= g["market_cap_min"]),
        "plausible": r.get("plausible", True),
    }
    return checks, all(checks.values()), growth


def evaluate(rows, returns: dict = None, thresholds=None) -> dict:
    """
    rows      : list of per-stock records from metrics.compute
    returns   : optional {ticker: trailing_return_fraction} for the price-lag signal
    Produces a ranked list of overlooked compounders with Buy/Watch/Fair signals.
    """
    t = thresholds or config.COMPOUNDERS
    returns = returns or {}

    # 1) keep only strong, growing, sound businesses with a usable P/E
    cands = []
    for r in rows:
        checks, ok, growth = gate_check(r, t)
        if ok and r.get("pe") and r["pe"] > 0:
            cands.append((r, growth))

    # 2) sector peer medians (P/E) among the quality candidates themselves
    by_sector: dict[str, list] = {}
    for r, _ in cands:
        by_sector.setdefault(r.get("sector") or "—", []).append(r["pe"])
    overall_pe = [r["pe"] for r, _ in cands]
    overall_med = median(overall_pe) if overall_pe else None

    # 3) sector median trailing return (for the price-lag comparison)
    ret_by_sector: dict[str, list] = {}
    for r, _ in cands:
        if r["t"] in returns:
            ret_by_sector.setdefault(r.get("sector") or "—", []).append(returns[r["t"]])

    scored = []
    for r, growth in cands:
        sec = r.get("sector") or "—"
        peers = by_sector.get(sec, [])
        if len(peers) >= t["min_peers"]:
            med_pe, basis = median(peers), "sector"
        else:
            med_pe, basis = overall_med, "overall"

        peer_discount = ((med_pe - r["pe"]) / med_pe) if med_pe else None
        peg = (r["pe"] / (growth * 100)) if (growth and growth > 0) else None

        # price-lag: did its price trail the sector while fundamentals held up?
        price_lag = None
        lagged = None
        if r["t"] in returns:
            sec_rets = ret_by_sector.get(sec, [])
            if len(sec_rets) >= t["min_peers"]:
                price_lag = median(sec_rets) - returns[r["t"]]  # >0 = lagged peers
                lagged = price_lag > 0

        cheap_peers = peer_discount is not None and peer_discount >= t["peer_discount_min"]
        cheap_peg = peg is not None and peg < t["peg_buy_max"]

        if cheap_peers and cheap_peg:
            signal = "BUY"
        elif cheap_peers or cheap_peg:
            signal = "WATCH"
        else:
            signal = "FAIR"

        scored.append({
            **r,
            "growth": growth,
            "sectorMedianPE": med_pe,
            "peerBasis": basis,
            "peerDiscount": peer_discount,
            "peg": peg,
            "trailingReturn": returns.get(r["t"]),
            "priceLag": price_lag,
            "laggedPeers": lagged,          # None when history not yet available
            "cSignal": signal,
        })

    scored.sort(key=lambda x: (x["peerDiscount"] if x["peerDiscount"] is not None else -9), reverse=True)
    counts = {s: sum(1 for x in scored if x["cSignal"] == s) for s in ("BUY", "WATCH", "FAIR")}
    counts["candidates"] = len(scored)
    counts["hasPriceHistory"] = any(x["laggedPeers"] is not None for x in scored)
    return {"counts": counts, "candidates": scored}
