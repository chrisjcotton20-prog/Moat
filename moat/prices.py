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
