"""M7 Pairwise Comparison: constants, metric mappings, model definitions."""

# FMP column name -> prompt label
FUNDAMENTAL_METRICS = {
    # From key_metrics
    "returnOnEquity": "ROE",
    "returnOnAssets": "ROA",
    "currentRatio": "Current Ratio",
    "incomeQuality": "Income Quality",
    "evToEBITDA": "EV/EBITDA",
    # From financial_ratios
    "priceToEarningsRatio": "P/E",
    "debtToEquityRatio": "D/E",
    "priceToBookRatio": "P/B",
    "grossProfitMargin": "Gross Margin",
    "netProfitMargin": "Net Margin",
    "freeCashFlowPerShare": "FCF/Share",
    "dividendYield": "Dividend Yield",
}

# Metrics shown to the LLM (includes derived metrics beyond fundamentals)
PROMPT_METRICS = [
    "Revenue Growth (YoY)",
    "Net Margin",
    "Gross Margin",
    "ROE",
    "ROA",
    "P/E",
    "P/B",
    "D/E",
    "Current Ratio",
    "EV/EBITDA",
    "FCF/Share",
    "Dividend Yield",
    "Piotroski F-Score",
    "Trailing 6mo Return",
    "Trailing Volatility",
]

# Experiment defaults
MARKET_CAP_MIN = 100_000_000  # $100M
FORWARD_MONTHS = 6
FORWARD_TRADING_DAYS = 126  # ~6 months of trading days
TRAILING_TRADING_DAYS = 126
PAIRS_PER_REBALANCE = 150
REBALANCE_FREQUENCY = "semi-annual"
START_YEAR = 2015
END_YEAR = 2025

# Difficulty tiers by absolute return spread
DIFFICULTY_TIERS = {
    "easy": {"min_spread": 0.15, "max_spread": float("inf")},   # >15% spread
    "medium": {"min_spread": 0.05, "max_spread": 0.15},          # 5-15% spread
    "hard": {"min_spread": 0.0, "max_spread": 0.05},             # <5% spread
}
DIFFICULTY_RATIOS = {"easy": 0.33, "medium": 0.34, "hard": 0.33}

# Model configurations
MODELS = {
    "claude-haiku": {
        "model_id": "claude-haiku-4-5-20251001",
        "input_cost_per_mtok": 0.80,
        "output_cost_per_mtok": 4.00,
    },
    "claude-sonnet": {
        "model_id": "claude-sonnet-4-6-20250514",
        "input_cost_per_mtok": 3.00,
        "output_cost_per_mtok": 15.00,
    },
    "claude-opus": {
        "model_id": "claude-opus-4-6-20250610",
        "input_cost_per_mtok": 15.00,
        "output_cost_per_mtok": 75.00,
    },
}

# Prompt variants
PROMPT_VARIANTS = ["v1_direct", "v2_cot", "v3_expert", "v4_structured"]

# Exchange presets (maps CLI names to API exchange codes)
EXCHANGE_PRESETS = {
    "us": ["NYSE", "NASDAQ", "AMEX"],
    "india": ["BSE", "NSE"],
    "hongkong": ["HKSE"],
    "australia": ["ASX"],
    "germany": ["XETRA"],
    "canada": ["TSX"],
}
