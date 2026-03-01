# M7 Design Notes (Detailed Implementation Reference)

These are the detailed design notes for implementing PLAN.md. Read PLAN.md first for the overview.

---

## Module Details

### m7/config.py

```python
# Metric definitions mapping FMP columns to prompt labels
FUNDAMENTAL_METRICS = {
    # From key_metrics (FY)
    "returnOnEquity": {"label": "ROE", "source": "key_metrics", "format": ".1%"},
    "returnOnAssets": {"label": "ROA", "source": "key_metrics", "format": ".1%"},
    "currentRatio": {"label": "Current Ratio", "source": "key_metrics", "format": ".2f"},
    "incomeQuality": {"label": "Income Quality", "source": "key_metrics", "format": ".2f"},
    "evToEBITDA": {"label": "EV/EBITDA", "source": "key_metrics", "format": ".1f"},
    "marketCap": {"label": "Market Cap", "source": "key_metrics", "format": "hidden"},
    # From financial_ratios (FY)
    "priceToEarningsRatio": {"label": "P/E", "source": "financial_ratios", "format": ".1f"},
    "debtToEquityRatio": {"label": "D/E", "source": "financial_ratios", "format": ".2f"},
    "priceToBookRatio": {"label": "P/B", "source": "financial_ratios", "format": ".2f"},
    "grossProfitMargin": {"label": "Gross Margin", "source": "financial_ratios", "format": ".1%"},
    "netProfitMargin": {"label": "Net Margin", "source": "financial_ratios", "format": ".1%"},
    "freeCashFlowPerShare": {"label": "FCF/Share", "source": "financial_ratios", "format": ".2f"},
    "dividendYield": {"label": "Dividend Yield", "source": "financial_ratios", "format": ".2%"},
}

# Metrics shown in LLM prompt (ordered by category)
PROMPT_METRICS = [
    "priceToEarningsRatio", "priceToBookRatio", "evToEBITDA",        # Valuation
    "returnOnEquity", "returnOnAssets", "netProfitMargin", "grossProfitMargin",  # Profitability
    "debtToEquityRatio", "currentRatio",                              # Leverage/Liquidity
    # + computed: revenue_growth_yoy, fcf_yield, piotroski_score, trailing_6mo_return, trailing_volatility
]

MODELS = {
    "claude-opus": {"provider": "anthropic", "model_id": "claude-opus-4-6",
                    "cost_per_1m_input": 15.0, "cost_per_1m_output": 75.0},
    "claude-sonnet": {"provider": "anthropic", "model_id": "claude-sonnet-4-6",
                      "cost_per_1m_input": 3.0, "cost_per_1m_output": 15.0},
    "claude-haiku": {"provider": "anthropic", "model_id": "claude-haiku-4-5-20251001",
                     "cost_per_1m_input": 0.80, "cost_per_1m_output": 4.0},
}

MARKET_CAP_MIN = 100_000_000
FORWARD_MONTHS = 6
PAIRS_PER_REBALANCE = 150
REBALANCE_FREQUENCY = "semi-annual"
START_YEAR = 2015
END_YEAR = 2025

DIFFICULTY_TIERS = {"easy": 0.15, "medium": 0.05, "hard": 0.00}
DIFFICULTY_RATIOS = {"easy": 0.33, "medium": 0.34, "hard": 0.33}

PROMPT_VARIANTS = ["v1_direct", "v2_cot", "v3_expert", "v4_structured"]
```

### m7/data.py — SQL Patterns

Exchange filtering uses symbol suffix (confirmed from data audit):
```python
EXCHANGE_SUFFIXES = {
    "us": None,  # US symbols have no suffix
    "bse": ".BO", "nse": ".NS",
    "hkse": ".HK", "asz": ".AX",
    "xetra": ".DE", "tsx": ".TO",
    "ksc": ".KS", "shz": ".SZ", "shh": ".SS",
    "sao": ".SA",
}

def _build_symbol_filter(exchange):
    """Build SQL WHERE clause for exchange filtering."""
    suffix = EXCHANGE_SUFFIXES.get(exchange.lower())
    if suffix is None:
        return "symbol NOT LIKE '%.%'"  # US: no dot in symbol
    return f"symbol LIKE '%{suffix}'"
```

Fetching key_metrics:
```sql
SELECT symbol, returnOnEquity, returnOnAssets, currentRatio, incomeQuality,
       evToEBITDA, marketCap, dateEpoch as filing_epoch, period
FROM key_metrics
WHERE period = 'FY' AND returnOnEquity IS NOT NULL AND {sym_filter}
```

Fetching financial_ratios:
```sql
SELECT symbol, priceToEarningsRatio, debtToEquityRatio, priceToBookRatio,
       grossProfitMargin, netProfitMargin, freeCashFlowPerShare, dividendYield,
       dateEpoch as filing_epoch, period
FROM financial_ratios
WHERE period = 'FY' AND priceToEarningsRatio IS NOT NULL AND {sym_filter}
```

Prices (full daily history, not just rebalance dates):
```sql
SELECT symbol, date, dateEpoch as trade_epoch, adjClose
FROM stock_eod
WHERE {sym_filter} AND date >= '{start}' AND date <= '{end}'
```

Revenue for growth YoY:
```sql
SELECT symbol, revenue, dateEpoch as filing_epoch, period
FROM income_statement
WHERE period = 'FY' AND {sym_filter}
```

### Derived Features — DuckDB SQL

**Trailing 6-month return** (at a specific rebalance date):
```sql
WITH price_now AS (
    SELECT symbol, adjClose as price_now, trade_epoch
    FROM prices_cache
    WHERE trade_epoch >= {rebalance_epoch}
    QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_epoch ASC) = 1
),
price_6mo_ago AS (
    SELECT symbol, adjClose as price_6mo, trade_epoch
    FROM prices_cache
    WHERE trade_epoch <= {rebalance_epoch - 126_trading_days}
    QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_epoch DESC) = 1
)
SELECT pn.symbol,
       (pn.price_now - p6.price_6mo) / p6.price_6mo AS trailing_6mo_return
FROM price_now pn
JOIN price_6mo_ago p6 ON pn.symbol = p6.symbol
```

**Trailing volatility** (annualized):
```sql
WITH daily_ret AS (
    SELECT symbol, trade_epoch,
           (adjClose - LAG(adjClose) OVER (PARTITION BY symbol ORDER BY trade_epoch))
           / LAG(adjClose) OVER (PARTITION BY symbol ORDER BY trade_epoch) AS ret
    FROM prices_cache
    WHERE trade_epoch BETWEEN {epoch_6mo_ago} AND {rebalance_epoch}
)
SELECT symbol, STDDEV(ret) * SQRT(252) AS trailing_volatility
FROM daily_ret WHERE ret IS NOT NULL
GROUP BY symbol HAVING COUNT(*) >= 60
```

**Revenue growth YoY** (from consecutive filings):
```sql
WITH curr AS (
    SELECT symbol, revenue, filing_epoch,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY filing_epoch DESC) AS rn
    FROM income_cache WHERE filing_epoch <= {cutoff_epoch} AND period = 'FY'
),
prev AS (
    SELECT symbol, revenue, filing_epoch,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY filing_epoch DESC) AS rn
    FROM income_cache WHERE filing_epoch <= {cutoff_epoch_minus_1yr} AND period = 'FY'
)
SELECT c.symbol,
       CASE WHEN p.revenue > 0 THEN (c.revenue - p.revenue) / p.revenue ELSE NULL END
       AS revenue_growth_yoy
FROM curr c JOIN prev p ON c.symbol = p.symbol AND p.rn = 1
WHERE c.rn = 1
```

### m7/pairs.py — Pair Generation Details

**Eligible universe query** (at a rebalance date):
```python
cutoff_epoch = int(datetime.combine(rebalance_date - timedelta(days=45), datetime.min.time()).timestamp())

eligible = con.execute("""
    WITH latest_km AS (
        SELECT symbol, returnOnEquity, returnOnAssets, currentRatio, incomeQuality,
               evToEBITDA, marketCap, filing_epoch,
               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY filing_epoch DESC) AS rn
        FROM metrics_cache WHERE filing_epoch <= ?
    ),
    latest_fr AS (
        SELECT symbol, priceToEarningsRatio, debtToEquityRatio, priceToBookRatio,
               grossProfitMargin, netProfitMargin, freeCashFlowPerShare, dividendYield,
               filing_epoch,
               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY filing_epoch DESC) AS rn
        FROM ratios_cache WHERE filing_epoch <= ?
    )
    SELECT km.symbol, km.returnOnEquity, km.returnOnAssets, km.currentRatio,
           km.incomeQuality, km.evToEBITDA, km.marketCap,
           fr.priceToEarningsRatio, fr.debtToEquityRatio, fr.priceToBookRatio,
           fr.grossProfitMargin, fr.netProfitMargin, fr.freeCashFlowPerShare,
           fr.dividendYield
    FROM latest_km km
    JOIN latest_fr fr ON km.symbol = fr.symbol AND fr.rn = 1
    WHERE km.rn = 1
      AND km.marketCap > 100000000
      AND km.returnOnEquity IS NOT NULL
      AND fr.priceToEarningsRatio IS NOT NULL
      -- ensure all metrics non-null
      AND km.returnOnAssets IS NOT NULL
      AND km.currentRatio IS NOT NULL
      AND fr.debtToEquityRatio IS NOT NULL
      AND fr.grossProfitMargin IS NOT NULL
      AND fr.netProfitMargin IS NOT NULL
""", [cutoff_epoch, cutoff_epoch]).fetchall()
```

**Pair dict structure**:
```python
{
    "pair_id": "US_2020-01-01_042",
    "rebalance_date": "2020-01-01",
    "exchange": "US",
    "stock_x": {
        "symbol": "AAPL",  # stored for ground truth, NOT shown to LLM
        "metrics": {
            "P/E": 15.4, "P/B": 2.1, "EV/EBITDA": 10.3,
            "ROE": 0.182, "ROA": 0.091, "Net Margin": 0.123,
            "Gross Margin": 0.425, "D/E": 0.42, "Current Ratio": 1.8,
            "Revenue Growth (YoY)": 0.085, "FCF Yield": 0.062,
            "Piotroski F-Score": 7,
            "Trailing 6-Month Return": 0.142, "Trailing Volatility": 0.221
        }
    },
    "stock_y": { ... },
    "forward_return_x": 0.123,
    "forward_return_y": 0.045,
    "return_spread": 0.078,
    "difficulty": "medium",
    "winner": "X"
}
```

### m7/prompts.py — Prompt Formats

**V1 Direct**:
```
Which stock will deliver higher total return over the next 6 months?

Stock X:
  P/E: 15.4
  P/B: 2.1
  EV/EBITDA: 10.3
  ROE: 18.2%
  ROA: 9.1%
  Net Margin: 12.3%
  Gross Margin: 42.5%
  D/E: 0.42
  Current Ratio: 1.8
  Revenue Growth (YoY): +8.5%
  FCF Yield: 6.2%
  Piotroski F-Score: 7
  Trailing 6-Month Return: +14.2%
  Trailing Volatility (ann.): 22.1%

Stock Y:
  [same metrics]

Answer with EXACTLY this format:
PICK: X or Y
CONFIDENCE: [0.0 to 1.0]
REASONING: [2-3 sentences]
```

**V2 CoT**: Same data, prepend "Think step by step: 1) Compare valuation 2) Compare profitability 3) Compare health 4) Compare momentum 5) Synthesize"

**V3 Expert**: System prompt = "You are a senior quantitative analyst..." + user message with data block

**V4 Structured**: "Score each category 1-10 for both stocks, compute totals, then decide"

### m7/llm.py — Anthropic SDK Call Pattern

```python
import anthropic
import time
import json

class LLMRunner:
    def __init__(self, model, run_dir, prompt_variant, temperature=0.0):
        self.model_config = MODELS[model]
        self.client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY env var
        self.run_dir = run_dir
        self.prompt_variant = prompt_variant
        self.temperature = temperature
        self.completed = self._load_completed()

    def _call_llm(self, prompt, pair_id, system_prompt=None):
        kwargs = {
            "model": self.model_config["model_id"],
            "max_tokens": 1024,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        t0 = time.monotonic()
        message = self.client.messages.create(**kwargs)
        latency_ms = int((time.monotonic() - t0) * 1000)

        return {
            "pair_id": pair_id,
            "model": self.model_config["model_id"],
            "response": message.content[0].text,
            "tokens_in": message.usage.input_tokens,
            "tokens_out": message.usage.output_tokens,
            "latency_ms": latency_ms,
            "cost_usd": (message.usage.input_tokens * self.model_config["cost_per_1m_input"]
                        + message.usage.output_tokens * self.model_config["cost_per_1m_output"]) / 1_000_000,
        }

    def _load_completed(self):
        """Load pair_ids from existing JSONL for resumability."""
        completed = set()
        path = os.path.join(self.run_dir, "llm_calls.jsonl")
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    try:
                        r = json.loads(line.strip())
                        if r.get("error") is None:
                            completed.add(r["pair_id"])
                    except (json.JSONDecodeError, KeyError):
                        pass
        return completed

    def _log(self, result):
        """Append to JSONL."""
        path = os.path.join(self.run_dir, "llm_calls.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps(result) + "\n")
```

### m7/evaluate.py — Key Formulas

**Wilson confidence interval** (for binary proportion):
```python
import math

def wilson_ci(successes, total, z=1.96):
    """Wilson score interval for 95% CI on a proportion."""
    if total == 0:
        return 0.0, 0.0, 0.0
    p = successes / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denom
    return p, max(0, center - spread), min(1, center + spread)
```

**Expected Calibration Error**:
```python
def compute_ece(results, n_buckets=5):
    """Expected Calibration Error."""
    buckets = [[] for _ in range(n_buckets)]
    for r in results:
        if r["confidence"] is None:
            continue
        idx = min(int(r["confidence"] * n_buckets), n_buckets - 1)
        buckets[idx].append(1 if r["correct"] else 0)

    ece = 0.0
    total = sum(len(b) for b in buckets)
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        avg_conf = (i + 0.5) / n_buckets
        avg_acc = sum(bucket) / len(bucket)
        ece += len(bucket) / total * abs(avg_acc - avg_conf)
    return ece
```

**McNemar's test** (paired binary outcomes):
```python
def mcnemar_test(llm_correct, baseline_correct):
    """McNemar's test for comparing two classifiers on same test set."""
    # b = LLM right, baseline wrong; c = LLM wrong, baseline right
    b = sum(1 for l, bl in zip(llm_correct, baseline_correct) if l and not bl)
    c = sum(1 for l, bl in zip(llm_correct, baseline_correct) if not l and bl)
    if b + c == 0:
        return 1.0  # No disagreement
    # With continuity correction
    chi2 = (abs(b - c) - 1)**2 / (b + c)
    # Approximate p-value from chi2 with 1 df
    from math import erfc, sqrt
    p_value = erfc(sqrt(chi2 / 2))
    return p_value
```

**Long-short portfolio** construction:
```python
def compute_long_short(pairs, results):
    """Compute period returns for long-short portfolio."""
    from collections import defaultdict
    by_date = defaultdict(list)
    for pair, result in zip(pairs, results):
        if result["pick"] is None:
            continue
        by_date[pair["rebalance_date"]].append((pair, result))

    period_returns = []
    for rd in sorted(by_date.keys()):
        long_rets, short_rets = [], []
        for pair, result in by_date[rd]:
            picked = pair[f"forward_return_{'x' if result['pick'] == 'X' else 'y'}"]
            rejected = pair[f"forward_return_{'y' if result['pick'] == 'X' else 'x'}"]
            long_rets.append(picked)
            short_rets.append(rejected)
        if long_rets and short_rets:
            period_returns.append(
                sum(long_rets)/len(long_rets) - sum(short_rets)/len(short_rets)
            )
    return period_returns  # Feed into lib/metrics.compute_metrics()
```

## ts_client.py Usage Reference

```python
from lib.ts_client import TradingStudio

ts = TradingStudio()  # uses TS_API_KEY env var

# JSON query (returns list[dict])
rows = ts.query("SELECT symbol, returnOnEquity FROM key_metrics WHERE period='FY' LIMIT 5")

# Parquet query (returns bytes, for DuckDB loading)
parquet_bytes = ts.query(sql, format="parquet", limit=1000000, timeout=600,
                          memory_mb=16384, threads=6)

# Save parquet to disk
with open("data/US/metrics.parquet", "wb") as f:
    f.write(parquet_bytes)

# Load into DuckDB from file
con = duckdb.connect(":memory:")
con.execute("CREATE TABLE metrics AS SELECT * FROM read_parquet('data/US/metrics.parquet')")
```

## data_utils.py Usage Reference

```python
from lib.data_utils import query_parquet, get_prices, generate_rebalance_dates

# Load via API directly into DuckDB
count = query_parquet(ts, sql, con, "table_name", memory_mb=16384, threads=6, timeout=600)

# Get prices at a date (searches forward window_days=10)
prices = get_prices(con, ["AAPL", "MSFT"], date(2024, 1, 1))
# Returns: {"AAPL": 185.5, "MSFT": 374.2}

# Generate rebalance dates
dates = generate_rebalance_dates(2015, 2025, "semi-annual")
# Returns: [date(2015,1,1), date(2015,7,1), date(2016,1,1), ...]
```

## Key Anti-Look-Ahead Rules

1. Financial data cutoff: `filing_epoch <= cutoff_epoch` where `cutoff_epoch = rebalance_date - 45 days`
2. Trailing returns: only use price data BEFORE rebalance_date
3. Forward returns: used ONLY for ground truth evaluation, NEVER shown in prompt
4. Revenue growth: compare current FY filing vs previous FY filing (both before cutoff)
5. Piotroski: compute from raw statements at cutoff, not from `scores` table (which may be current)
