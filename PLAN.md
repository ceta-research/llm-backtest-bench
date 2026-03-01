# M7 Pairwise Comparison — Implementation Plan

## Context

We're building the first experiment for `llm-backtest-bench` — a new repo benchmarking LLM models on financial signal generation. M7 tests whether LLMs can pick the better-performing stock from anonymized pairs. This is the simplest, cheapest, and most cleanly evaluable methodology. No prior work has tested Claude models on this task, nor on non-US markets.

## Project Structure

```
llm-backtest-bench/
├── README.md
├── RESEARCH.md                  (existing)
├── METHODOLOGIES.md             (existing)
├── requirements.txt
├── .env.example
├── .gitignore
│
├── lib/                         # Copied from ts-backtests (verbatim)
│   ├── __init__.py
│   ├── ts_client.py
│   ├── data_utils.py
│   ├── metrics.py
│   ├── costs.py
│   └── cli_utils.py
│
├── m7/                          # M7 experiment
│   ├── __init__.py
│   ├── config.py                # Constants, metric mappings, model defs
│   ├── data.py                  # Fetch from API, cache to disk, load DuckDB
│   ├── pairs.py                 # Pair generation, seeding, stratification
│   ├── prompts.py               # 4 prompt variants + response parser
│   ├── llm.py                   # Anthropic SDK runner, logging, resume
│   ├── baselines.py             # 7 heuristic baselines
│   ├── evaluate.py              # Accuracy, calibration, long-short, stats
│   ├── run.py                   # CLI entry point
│   └── analyze.py               # Cross-run comparison, reports
│
├── data/                        # Cached parquet (gitignored)
│   └── {exchange}/
└── outputs/                     # Run results (gitignored)
    └── runs/{run_id}/
        ├── config.json
        ├── pairs.json
        ├── llm_calls.jsonl
        ├── results.json
        └── summary.json
```

## Implementation Steps (in order)

### Step 1: Scaffold & copy shared libs

- Create folder structure (`lib/`, `m7/`, `data/`, `outputs/`)
- Copy 5 files from `/Users/swas/Desktop/Swas/Kite/ATO_SUITE/ts-backtests/` into `lib/`: `ts_client.py`, `data_utils.py`, `metrics.py`, `costs.py`, `cli_utils.py`
- Create `requirements.txt`: `requests>=2.28.0`, `duckdb>=1.0.0`, `anthropic>=0.76.0`
- Create `.env.example` with `TS_API_KEY=` and `ANTHROPIC_API_KEY=`
- Create `.gitignore` (data/, outputs/, __pycache__, .env, *.pyc)

### Step 2: `m7/config.py` — constants

Define:
- `FUNDAMENTAL_METRICS` dict mapping FMP column names → prompt labels. Columns confirmed from schema: `returnOnEquity`, `returnOnAssets`, `currentRatio`, `incomeQuality`, `evToEBITDA` (from `key_metrics`); `priceToEarningsRatio`, `debtToEquityRatio`, `priceToBookRatio`, `grossProfitMargin`, `netProfitMargin`, `freeCashFlowPerShare`, `dividendYield` (from `financial_ratios`)
- `PROMPT_METRICS` list (the ~14 metrics shown to the LLM)
- Experiment defaults: `MARKET_CAP_MIN=100M`, `FORWARD_MONTHS=6`, `PAIRS_PER_REBALANCE=150`, `REBALANCE_FREQUENCY="semi-annual"`, year range 2015-2025
- Difficulty tiers: easy (>15% spread), medium (5-15%), hard (<5%), ratios 33/34/33
- Model configs with IDs and token costs
- Prompt variant keys

### Step 3: `m7/data.py` — data pipeline

**Pattern**: Follow `qarp/backtest.py:fetch_data_via_api()` (lines 58-167) but with disk caching and full price history.

Key function: `fetch_and_cache(exchange, start_year, end_year, api_key, cache_dir, verbose)`

SQL queries (using confirmed FMP column names + `dateEpoch as filing_epoch` pattern):
1. **Universe**: `SELECT DISTINCT symbol, exchange FROM profile WHERE exchange IN (...)`
2. **Key metrics**: `SELECT symbol, returnOnEquity, returnOnAssets, currentRatio, incomeQuality, evToEBITDA, marketCap, dateEpoch as filing_epoch, period FROM key_metrics WHERE period='FY' AND symbol IN (...)`
3. **Financial ratios**: `SELECT symbol, priceToEarningsRatio, debtToEquityRatio, priceToBookRatio, grossProfitMargin, netProfitMargin, freeCashFlowPerShare, dividendYield, dateEpoch as filing_epoch, period FROM financial_ratios WHERE period='FY' AND symbol IN (...)`
4. **Income statement** (for revenue growth YoY): `SELECT symbol, revenue, dateEpoch as filing_epoch, period FROM income_statement WHERE period='FY' AND symbol IN (...)`
5. **Scores** (Piotroski): `SELECT symbol, piotroskiScore FROM scores WHERE symbol IN (...)`
6. **Prices**: `SELECT symbol, date, dateEpoch as trade_epoch, adjClose FROM stock_eod WHERE symbol IN (...) AND date >= '{start}' AND date <= '{end}'` — full daily history needed for trailing return + volatility + forward return

Caching: save parquet bytes to `data/{exchange}/{table}.parquet`. On re-run, check if cache exists and is <24h old; if so, load from disk via DuckDB `read_parquet()`.

Derived features (computed in DuckDB after loading):
- `trailing_6mo_return`: price 126 trading days ago vs current, per symbol per date
- `trailing_volatility`: annualized stddev of daily returns over 126 days
- `revenue_growth_yoy`: from consecutive FY income statements (same CTE pattern as qarp/backtest.py lines 175-198)

Return: DuckDB connection with all tables loaded.

### Step 4: `m7/pairs.py` — pair generation

Key function: `generate_pairs(con, rebalance_date, exchange, n_pairs, seed)`

1. **Eligible universe**: Query DuckDB for stocks where:
   - `marketCap > 100M` (as of most recent FY filing before rebalance_date)
   - ALL prompt metrics non-null
   - Price exists at rebalance_date AND rebalance_date + 6 months
2. **Forward returns**: `(price_at_T+6mo - price_at_T) / price_at_T` for each eligible stock
3. **Sample pairs**: Seeded RNG (`hash(exchange + date + run_id)`), sample from eligible universe
4. **Stratify**: Compute `abs(return_x - return_y)`, bucket into easy/medium/hard, sample target ratios from each bucket
5. **Anonymize**: Randomly assign X/Y labels (seeded), strip symbol names from metrics dict

Output: list of pair dicts with `pair_id`, `stock_x.metrics`, `stock_y.metrics`, `forward_return_x`, `forward_return_y`, `winner`, `difficulty`

Save to `pairs.json`. Load via `load_pairs()` for resume/re-evaluation.

### Step 5: `m7/prompts.py` — prompt construction + response parsing

`build_prompt(stock_x_metrics, stock_y_metrics, variant)` → str

4 variants:
- **V1 Direct**: Data block + "Which stock? Answer: PICK/CONFIDENCE/REASONING"
- **V2 CoT**: "Think step by step: 1) valuation 2) profitability 3) health 4) momentum 5) decide"
- **V3 Expert**: System prompt "You are a senior quant analyst..." + data block
- **V4 Structured**: "Score each category 1-10 for both stocks, then decide"

`parse_response(text)` → `{"pick": "X"|"Y"|None, "confidence": float|None, "reasoning": str, "parse_error": str|None}`

Regex-based parser with fallbacks for common LLM output variations.

### Step 6: `m7/baselines.py` — heuristic evaluators

7 pure functions, each takes a pair dict, returns `{"pick": "X"|"Y", "rule": str}`:
- `baseline_lower_pe` — lower P/E wins
- `baseline_higher_roe` — higher ROE wins
- `baseline_higher_piotroski` — higher Piotroski wins
- `baseline_lower_pb` — lower P/B wins
- `baseline_momentum` — higher trailing 6mo return wins
- `baseline_composite` — normalized multi-factor sum (value + quality + momentum), pick higher
- `baseline_random` — seeded random pick

`evaluate_all_baselines(pairs)` runs all 7 on all pairs, returns dict of results.

### Step 7: `m7/llm.py` — LLM runner

`LLMRunner` class:
- Init: Anthropic client (`anthropic.Anthropic()`), load completed pair_ids from existing `llm_calls.jsonl` for resumability
- `run(pairs)`: iterate pairs, skip completed, call `build_prompt()` → `client.messages.create()` → `parse_response()` → append to JSONL
- Rate limiting: `time.sleep(0.5)` between calls, exponential backoff on 429
- Logging: every call → JSONL line with pair_id, model, tokens_in/out, latency_ms, cost_usd, pick, confidence, reasoning, errors

V3 Expert uses `system=` parameter in Anthropic SDK; others use user message only.

### Step 8: `m7/evaluate.py` — evaluation

`evaluate_run(pairs, llm_results, baseline_results)` → summary dict:
- **Accuracy**: mean correctness + Wilson 95% CI
- **Accuracy by difficulty**: easy/medium/hard breakdown
- **Calibration**: bucket by confidence (0.5-0.6, 0.6-0.7, ..., 0.9-1.0), compute actual accuracy per bucket, ECE
- **Long-short portfolio**: per rebalance date, avg return of LLM picks minus avg return of rejects → feed into `lib/metrics.compute_metrics()` for Sharpe, CAGR, etc.
- **Statistical tests**: McNemar's test (paired binary) for LLM vs each baseline, report p-values

### Step 9: `m7/run.py` — CLI orchestrator

```
python3 -m m7.run --exchange us --model claude-sonnet --prompt v1_direct [--pairs 150] [--start-year 2015] [--end-year 2025] [--verbose] [--pairs-only] [--resume PATH] [--evaluate PATH]
```

Flow: parse args → `data.fetch_and_cache()` → `pairs.generate_pairs()` per date → `llm.LLMRunner.run()` → `baselines.evaluate_all_baselines()` → `evaluate.evaluate_run()` → save summary.json → print results

### Step 10: `m7/analyze.py` — cross-run comparison

`compare_runs(run_dirs)` loads summary.json from each, prints comparison table. `generate_report(run_dir)` produces markdown report.

## Key Files Referenced

| Source File | Purpose |
|-------------|---------|
| `ts-backtests/ts_client.py` | Copy to lib/ — API client |
| `ts-backtests/data_utils.py` | Copy to lib/ — query_parquet, get_prices, rebalance dates |
| `ts-backtests/metrics.py` | Copy to lib/ — compute_metrics (17 metrics), format_metrics |
| `ts-backtests/costs.py` | Copy to lib/ — transaction cost models |
| `ts-backtests/cli_utils.py` | Copy to lib/ — exchange presets, risk-free rates |
| `ts-backtests/qarp/backtest.py` | Reference for SQL patterns, filing_epoch cutoff, Piotroski CTE |

## Data Availability (verified via API)

### Equities with Financial Data (key_metrics FY + prices)

| Exchange | Suffix | Financials | Prices | Date Range |
|----------|--------|-----------|--------|------------|
| US (NYSE/NASDAQ) | none | 9,302 | 43,701 | 1978-2026 |
| BSE (India) | .BO | 4,077 | 4,332 | 1994-2026 |
| NSE (India) | .NS | 2,458 | 2,795 | 1994-2026 |
| HKSE (Hong Kong) | .HK | 2,784 | 2,880 | 1985-2026 |
| ASX (Australia) | .AX | 2,443 | 2,498 | 1987-2026 |
| XETRA (Germany) | .DE | 1,029 | 2,594 | 1984-2026 |
| TSX (Canada) | .TO | 1,033 | 1,990 | 1985-2026 |
| KSC (Korea) | .KS | 1,022 | — | 1998-2026 |
| TW (Taiwan) | .TW | 1,048 | — | — |
| BK (Thailand) | .BK | 1,032 | — | — |
| ST (Stockholm) | .ST | 948 | — | — |
| JK (Jakarta) | .JK | 888 | — | — |

### Forex (daily data, 70+ pairs)

EURUSD (14,207 pts, 1971-2026), EURGBP (13,257 pts), USDCNY (11,486 pts), etc.

### Key Data Notes

- FMP column names confirmed: `returnOnEquity`, `returnOnAssets`, `currentRatio`, `incomeQuality`, `evToEBITDA`, `marketCap` (key_metrics); `priceToEarningsRatio`, `debtToEquityRatio`, `priceToBookRatio`, `grossProfitMargin`, `netProfitMargin`, `freeCashFlowPerShare`, `dividendYield` (financial_ratios)
- Filing dates use `dateEpoch as filing_epoch` pattern
- Prices use `dateEpoch as trade_epoch` + `adjClose`
- Exchange filtering by symbol suffix (e.g., `.BO` for BSE, `.NS` for NSE) or via `profile.exchange`
- LSE (.L) has 6,581 stocks with prices but only 1 with key_metrics → price-only experiments only
- The `scores` table has Piotroski F-Scores but may be current-only (not historical). Consider computing from raw statements as qarp/backtest.py does.

## LLM Integration Details

- **Anthropic SDK v0.76.0** installed at `/Users/swas/Desktop/Swas/Kite/ATO_SUITE/.venv`
- `client.messages.create(model="claude-opus-4-6", temperature=0.0, max_tokens=1024, messages=[...])`
- System prompt via `system=` parameter (for V3 Expert variant)
- Response: `message.content[0].text`, `message.usage.input_tokens`, `message.usage.output_tokens`
- Model IDs: `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`

## Verification Plan

1. **Data pipeline**: `python3 -m m7.run --exchange us --pairs-only --pairs 10 --start-year 2024 --end-year 2025 --verbose`
2. **LLM calls**: `python3 -m m7.run --exchange us --model claude-haiku --prompt v1_direct --pairs 5 --start-year 2024 --end-year 2025 --verbose` (5 pairs, ~$0.005)
3. **Resumability**: Kill mid-run, restart, verify skips completed pairs
4. **Full run**: `python3 -m m7.run --exchange us --model claude-sonnet --prompt v1_direct` (1,200 pairs, ~$3.60)
5. **Baselines**: Verify random baseline → ~50% accuracy over 1,000+ pairs
6. **Cross-exchange**: Run on `--exchange india`, verify BSE/NSE data loads

## Cost Estimates

| Model | Cost/pair | 1,200 pairs (1 exchange) | 4,800 pairs (4 exchanges) |
|-------|----------|-------------------------|--------------------------|
| Haiku | ~$0.001 | ~$1.20 | ~$4.80 |
| Sonnet | ~$0.003 | ~$3.60 | ~$14.40 |
| Opus | ~$0.015 | ~$18.00 | ~$72.00 |

Full sweep (4 exchanges × 3 models × 4 prompts) = 48 runs × 1,200 pairs = ~$300 total.
