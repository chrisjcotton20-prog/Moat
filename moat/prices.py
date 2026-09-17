"""
Prices are the one thing EDGAR doesn't give us. Two sources:

  * a local CSV (ticker,close) -- used by the tests and handy if you already
    have a price file, and
  * Stooq's free per-symbol history endpoint, taking the last close.

Stooq also publishes whole-exchange bulk downloads; for a first screen the
per-symbol pull is simplest and is what --stooq uses.
"""
from __future__ import annotations
import csv
import io
import urllib.request
from typing import Optional

STOOQ_DAILY = "https://stooq.com/q/d/l/?s={sym}.us&i=d"


def load_prices_csv(path: str) -> dict[str, float]:
    out = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            tk = (row.get("ticker") or row.get("Ticker") or "").strip().upper()
            val = row.get("close") or row.get("Close")
            if tk and val:
                try:
                    out[tk] = float(val)
                except ValueError:
                    pass
    return out


def fetch_stooq_last(ticker: str) -> Optional[float]:
    """Last available daily close from Stooq. Returns None on any failure."""
    try:
        url = STOOQ_DAILY.format(sym=ticker.lower())
        with urllib.request.urlopen(url, timeout=20) as resp:
            text = resp.read().decode("utf-8", "replace")
        rows = list(csv.DictReader(io.StringIO(text)))
        for row in reversed(rows):
            if row.get("Close") not in (None, "", "N/D"):
                return float(row["Close"])
    except Exception:  # noqa: BLE001
        return None
    return None


def load_meta(path):
    """Load {ticker: {"sector": str, "market_cap": float}} from a meta CSV
    (columns: ticker,sector,marketcap). Used for peer grouping and the size gate."""
    out = {}
    try:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                tk = (row.get("ticker") or "").strip().upper()
                if not tk:
                    continue
                mc = row.get("marketcap") or row.get("market_cap") or ""
                try:
                    mc = float(mc)
                except (TypeError, ValueError):
                    mc = None
                out[tk] = {"sector": (row.get("sector") or "").strip() or None,
                           "market_cap": mc}
    except FileNotFoundError:
        pass
    return out


def load_returns(history_path, lookback_days=250, tolerance_days=60):
    """
    From a long-format price history (columns: date,ticker,close), compute each
    ticker's trailing return over ~lookback_days trading days (~365 calendar).
    Returns {ticker: return_fraction}. Tickers without enough history are omitted,
    so the price-lag signal simply switches on as history accumulates.
    """
    from datetime import date as _date
    series = {}
    try:
        with open(history_path, newline="") as f:
            for row in csv.DictReader(f):
                tk = (row.get("ticker") or "").strip().upper()
                d = (row.get("date") or "").strip()
                c = row.get("close")
                if not tk or not d or c in (None, ""):
                    continue
                try:
                    y, m, dd = map(int, d.split("-"))
                    series.setdefault(tk, []).append((_date(y, m, dd), float(c)))
                except ValueError:
                    continue
    except FileNotFoundError:
        return {}

    out = {}
    target_cal = int(lookback_days * 365 / 252)  # trading days -> calendar days
    for tk, pts in series.items():
        pts.sort()
        latest_d, latest_c = pts[-1]
        target = latest_d.toordinal() - target_cal
        # nearest point to the target date, within tolerance
        best = None
        for d, c in pts:
            gap = abs(d.toordinal() - target)
            if gap <= tolerance_days and (best is None or gap < best[0]) and c > 0:
                best = (gap, c)
        if best:
            out[tk] = latest_c / best[1] - 1.0
    return out
