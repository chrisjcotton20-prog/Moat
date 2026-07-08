"""
Moat engine configuration.

Everything here is a dial you own. The gate thresholds below are the same
opening defaults shown in the app preview. Loosen or tighten them and the
screen changes accordingly -- nothing else needs to move.
"""

# ---- The quality / strength gates -------------------------------------------
# A company must clear EVERY gate to appear on the shortlist.
GATES = {
    "roe_min": 0.12,          # return on equity >= 12%
    "op_margin_min": 0.08,    # operating margin > 8%
    "fscore_min": 5,          # Piotroski F-score >= 5 (of 9)
    "debt_to_equity_max": 1.5,
    "current_ratio_min": 1.0,
    "min_profitable_years": 8,  # want a long record of profits...
    "min_years_of_data": 5,     # ...but don't reject a name just for shallow EDGAR history
}

# ---- Valuation / signal bands -----------------------------------------------
GRAHAM_MULTIPLIER = 22.5      # Graham's 15 P/E * 1.5 P/B ceiling
BUY_MARGIN = 0.15            # >=15% below the Graham target -> BUY
WATCH_FLOOR = -0.10          # between -10% and +15% -> WATCH (fairly priced)
                             # below -10% (i.e. >10% above target) -> RICH

# ---- Sell / thesis bands (used when scoring a holdings list) -----------------
RICH_LINE = 1.5              # price above 1.5x target -> "Trim, richly valued"
ABOVE_FAIR_LINE = 1.2       # price above 1.2x target -> "Watch, above fair value"

# ---- SEC request etiquette ---------------------------------------------------
# SEC REQUIRES a descriptive User-Agent or it returns 403. Put your own contact.
DEFAULT_USER_AGENT = "Moat personal screener your-email@example.com"
SEC_REQUEST_DELAY = 0.12    # seconds between calls (~8/sec, under SEC's 10/sec)
SEC_MAX_RETRIES = 3

# ---- XBRL concept fallbacks --------------------------------------------------
# Companies tag the same idea with different us-gaap concepts. We try each in
# order and take the first that yields data. This is the messy heart of EDGAR.
CONCEPTS = {
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
    ],
    "gross_profit": ["GrossProfit"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "operating_income": ["OperatingIncomeLoss"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "assets": ["Assets"],
    "assets_current": ["AssetsCurrent"],
    "liabilities_current": ["LiabilitiesCurrent"],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "long_term_debt_current": ["LongTermDebtCurrent"],
    "short_term_debt": ["ShortTermBorrowings", "DebtCurrent"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment",
              "PaymentsToAcquireProductiveAssets"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "eps_basic": ["EarningsPerShareBasic"],
    "shares_outstanding_dei": ["EntityCommonStockSharesOutstanding"],  # dei namespace
    "shares_outstanding": ["CommonStockSharesOutstanding",
                           "WeightedAverageNumberOfDilutedSharesOutstanding"],
}

# Which concepts are point-in-time (instant) vs. period (duration)?
INSTANT_CONCEPTS = {
    "equity", "assets", "assets_current", "liabilities_current",
    "long_term_debt", "long_term_debt_current", "short_term_debt",
    "shares_outstanding", "shares_outstanding_dei",
}
