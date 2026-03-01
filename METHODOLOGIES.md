# Experiment Methodologies

## Data Availability Summary

Before listing methodologies, here's what we actually have.

### Equities with Full Financial Data (key_metrics + ratios + statements + prices)

| Exchange | Suffix | Financials | Prices | Date Range |
|----------|--------|-----------|--------|------------|
| **US** (NYSE/NASDAQ/AMEX) | none | 9,302 | 43,701 | 1978-2026 |
| **BSE** (India) | .BO | 4,077 | 4,332 | 1994-2026 |
| **NSE** (India) | .NS | 2,458 | 2,795 | 1994-2026 |
| **HKSE** (Hong Kong) | .HK | 2,784 | 2,880 | 1985-2026 |
| **SHZ** (Shenzhen) | .SZ | 2,469 | — | 1989-2026 |
| **SHH** (Shanghai) | .SS | 2,032 | — | 1990-2026 |
| **ASX** (Australia) | .AX | 2,443 | 2,498 | 1987-2026 |
| **XETRA** (Germany) | .DE | 1,029 | 2,594 | 1984-2026 |
| **TSX** (Canada) | .TO | 1,033 | 1,990 | 1985-2026 |
| **KSC** (Korea) | .KS | 1,022 | — | 1998-2026 |
| **SAO** (Brazil) | .SA | 487 | — | 1994-2026 |
| **TW** (Taiwan) | .TW | 1,048 | — | — |
| **BK** (Thailand) | .BK | 1,032 | — | — |
| **ST** (Stockholm) | .ST | 948 | — | — |
| **JK** (Jakarta) | .JK | 888 | — | — |

### Equities with Prices Only (no/limited financial data)

| Exchange | Suffix | Prices | Date Range |
|----------|--------|--------|------------|
| **LSE** (London) | .L | 6,581 | 1970-2026 |
| **JPX** (Tokyo) | .T | 4,017 | 1980-2026 |
| **PAR** (Paris) | .PA | 1,217 | 1983-2026 |

### Forex (45+ years of daily data)

| Pair | Data Points | Date Range |
|------|------------|------------|
| EURUSD | 14,207 | 1971-2026 |
| EURGBP | 13,257 | 1975-2026 |
| USDGBP | 11,947 | 1979-2026 |
| USDCNY | 11,486 | 1981-2026 |
| USDMXN | 9,486 | 1989-2026 |
| ... | 70+ pairs | — |

### Macro Data
- **FRED**: Fed funds rate, CPI, unemployment, yield curve, etc.
- **Eurostat**: EU economic indicators
- **World Bank**: GDP, trade, development
- **FMP**: Treasury rates, market risk premium, sector/industry PE

---

## Experimental Framework

### Universal Design Principles

Every experiment follows these rules:

1. **Anonymization**: Strip all identifying information. Stocks labeled A, B, C... or random IDs. No sector names, no company names, no geographic hints. Dates presented as T, T-1, T-2... (relative) not calendar dates.

2. **Anti-look-ahead bias**: Only data available as-of the decision date. Financial statements use `filingDate` (not `date`). No future prices, no future news.

3. **Determinism**: temperature=0, fixed seeds where supported, pin exact model versions (e.g., `claude-opus-4-6`).

4. **Multiple trials**: Minimum 5 runs per configuration. Report mean, std, and 95% CI.

5. **Statistical testing**: Paired t-test or bootstrap for significance (p < 0.05). Report effect size (Cohen's d).

6. **Baselines**: Every experiment has at least one naive baseline (random, buy-and-hold, equal-weight) AND one traditional quantitative baseline.

7. **Cost tracking**: Log tokens in/out, latency, and dollar cost per signal for every model call.

8. **Reproducibility**: All prompts, responses, and configurations logged. Data fetchable via CR API by anyone.

---

## The 10 Methodologies

### M1: Earnings Direction Prediction (Binary Classification)

**Question**: Can LLMs predict whether a company's earnings will increase or decrease next fiscal year, given only anonymized financial statements?

**Why it matters**: This is the purest test of financial reasoning. Kim et al. (2024) showed GPT-4 achieves 60.35% on US data with anonymized Compustat statements. Nobody has tested this on non-US markets or compared across Claude/GPT/Gemini/open-source.

**Input to LLM**:
```
Company: Stock_A
Currency: [hidden]

Income Statement (3 years):
         T-2          T-1          T
Revenue: 45,231,000   52,108,000   48,672,000
COGS:    28,144,000   31,265,000   30,418,000
Gross:   17,087,000   20,843,000   18,254,000
OpEx:     8,432,000    9,105,000    9,311,000
NetInc:   6,201,000    8,490,000    5,982,000

Balance Sheet (2 years):
              T-1          T
TotalAssets:  91,405,000   88,231,000
TotalLiab:   42,318,000   45,102,000
Equity:      49,087,000   43,129,000
...

Question: Will net income increase or decrease in year T+1?
Answer with: INCREASE or DECREASE, then explain your reasoning.
```

**Ground truth**: Actual next-year net income from filing.

**Evaluation**: Accuracy, F1, AUC-ROC. Compare against:
- Random (50%)
- Naive persistence (same direction as last year)
- Logistic regression on same features
- Kim et al. (2024) GPT-4 result (60.35%) as reference point

**Data requirements**: `income_statement`, `balance_sheet`, `cash_flow_statement` (FY, 3+ years). Need `filingDate` for anti-look-ahead.

**Viable exchanges**: US (9,302), BSE (4,077), HKSE (2,784), NSE (2,458), ASX (2,443), SHZ (2,469), SHH (2,032), XETRA (1,029), TSX (1,033), KSC (1,022)

---

### M2: Stock Ranking from Fundamentals (Ordinal Ranking)

**Question**: Given a pool of anonymized stocks with key financial ratios, can LLMs rank them by future return?

**Why it matters**: Stock selection is the core value proposition of quantitative investing. Traditional factor models (Fama-French, quality, value) do this with fixed rules. Can LLMs do better with the same data? No existing benchmark tests this with structured numerical data across non-US markets.

**Input to LLM**:
```
Rank these 20 stocks by expected return over the next 6 months.
Use only the data provided. Return a ranked list from best (1) to worst (20).

Stock | P/E   | P/B  | ROE   | ROA   | D/E  | CR   | EV/EBITDA | FCF Yield | Revenue Growth | Piotroski
A     | 12.3  | 1.8  | 18.2% | 9.1%  | 0.42 | 1.8  | 8.5       | 6.2%      | 8.5%           | 7
B     |  8.7  | 0.9  | 24.1% | 12.0% | 0.15 | 2.1  | 5.2       | 9.1%      | -3.2%          | 8
C     | 35.2  | 5.4  | 32.0% | 15.3% | 0.88 | 1.2  | 22.1      | 2.1%      | 25.3%          | 6
...
```

**Ground truth**: Actual forward 6-month return (from `stock_eod`).

**Evaluation**:
- Spearman rank correlation (LLM ranking vs actual return ranking)
- Top-5 vs bottom-5 return spread
- Information coefficient (IC)
- Compare against: random ranking, single-factor sorts (P/E, ROE, Piotroski), multi-factor composite

**Data requirements**: `key_metrics` (FY) + `financial_ratios` (FY) + `stock_eod` + `scores` (Piotroski)

**Viable exchanges**: US, BSE, NSE, HKSE, ASX, XETRA, TSX, KSC (all with 1,000+ stocks with financial data)

---

### M3: Buy/Hold/Sell from Price Patterns (Technical Classification)

**Question**: Given an anonymized price series (OHLCV), can LLMs predict short-term direction?

**Why it matters**: Tests pattern recognition ability with zero fundamental context. Price data is available for ALL exchanges including LSE and JPX (which lack financial data). Also testable on forex. This is the methodology most people intuitively think of, and the most directly comparable to traditional technical analysis.

**Input to LLM**:
```
Here are the last 60 trading days of OHLCV data for an anonymized asset.

Day | Open    | High    | Low     | Close   | Volume
T-59| 142.30  | 145.10  | 141.80  | 144.50  | 2,341,000
T-58| 144.80  | 146.20  | 143.90  | 143.10  | 1,892,000
...
T-0 | 158.20  | 159.80  | 156.40  | 157.30  | 2,105,000

What will the closing price direction be over the next 5 trading days?
Answer: UP (>+2%), DOWN (<-2%), or FLAT (within +/-2%).
Also provide a confidence score from 0.0 to 1.0.
```

**Ground truth**: Actual 5-day forward return from `stock_eod` or `forex_prices_daily`.

**Evaluation**: Accuracy, calibration (confidence vs actual accuracy), profit if traded on signal.

**Baselines**:
- Random (33% each)
- Momentum (last 5 days direction continues)
- Mean reversion (opposite of last 5 days)
- SMA crossover (10/20 day)
- RSI overbought/oversold

**Data requirements**: `stock_eod` or `forex_prices_daily` (60+ days history)

**Viable exchanges**: ALL exchanges + forex. This is the methodology with widest applicability:
- US (43,701 symbols), LSE (6,581), BSE (4,332), JPX (4,017), HKSE (2,880), NSE (2,795), XETRA (2,594), ASX (2,498), TSX (1,990), PAR (1,217)
- Forex: 70+ pairs, 45+ years

---

### M4: Portfolio Allocation (Weight Optimization)

**Question**: Given N anonymized assets with characteristics, can LLMs allocate portfolio weights that produce better risk-adjusted returns?

**Why it matters**: Every existing benchmark (FINSABER, StockBench, AI-Trader) uses single-stock buy/sell/hold. Nobody tests portfolio-level allocation, which is how real investing works. This tests if LLMs can reason about diversification, correlation, and risk.

**Input to LLM**:
```
Allocate a portfolio across these 15 stocks. Weights must sum to 100%.
Minimum weight: 0%. Maximum weight: 20%. Objective: maximize risk-adjusted return over the next quarter.

Stock | Trailing 6mo Return | Volatility | P/E  | ROE  | Sector Group
A     | +12.3%              | 22.1%      | 15.2 | 18%  | 1
B     | -5.1%               | 35.4%      | 8.3  | 24%  | 2
C     | +3.8%               | 15.2%      | 22.1 | 12%  | 1
...

Correlation matrix (trailing 1yr):
    A     B     C     ...
A  1.00  0.35  0.72  ...
B  0.35  1.00  0.18  ...
C  0.72  0.18  1.00  ...

Return your allocation as: Stock, Weight%
```

**Ground truth**: Forward quarter return of the LLM's weighted portfolio.

**Evaluation**: Sharpe ratio, Sortino ratio, max drawdown, CAGR. Compare against:
- Equal weight (1/N)
- Inverse volatility
- Minimum variance (analytical, using correlation matrix)
- Max Sharpe (mean-variance optimization)
- Risk parity

**Data requirements**: `stock_eod` (1yr history + forward quarter), `key_metrics` or `financial_ratios` for characteristics, correlation computation from returns

**Viable exchanges**: Any exchange with 50+ liquid stocks with price history. US, BSE, NSE, HKSE, ASX, XETRA, TSX

---

### M5: Regime Classification (Market State Identification)

**Question**: Given anonymized market-level statistics, can LLMs classify the current market regime?

**Why it matters**: Market regime drives strategy selection. If LLMs can correctly identify bull/bear/sideways/crisis regimes, it would inform when to be aggressive vs defensive. This is a macro-level task that doesn't require individual stock data. Tests LLM reasoning about aggregate patterns.

**Input to LLM**:
```
Here are 120 days of market-level statistics for an anonymized equity index.

Day | Index Return | Breadth (% up) | Avg Vol (20d) | Dispersion | VIX-like
T-119| +0.8%       | 62%            | 1.02x         | 12.3%      | 14.2
T-118| +0.3%       | 58%            | 0.98x         | 11.8%      | 13.9
...
T-0  | -2.1%       | 31%            | 1.85x         | 28.4%      | 32.1

Classify the current market regime as one of:
A) BULL (sustained uptrend, low volatility)
B) BEAR (sustained downtrend, high volatility)
C) SIDEWAYS (range-bound, moderate volatility)
D) CRISIS (sharp drawdown, extreme volatility, correlation spike)

Also predict the regime for the next 20 trading days.
```

**Ground truth**: Regime labels assigned by rule-based classifier (validated):
- BULL: 60-day return > +10%, VIX-like < 20
- BEAR: 60-day return < -10%, VIX-like > 25
- CRISIS: 20-day return < -15%, VIX-like > 35
- SIDEWAYS: everything else

**Evaluation**: Classification accuracy, confusion matrix. Backtested value: does regime-conditional strategy (aggressive in bull, defensive in bear) outperform static strategy?

**Data requirements**: `index_prices_daily` or `stock_eod` (to construct index-level stats). `sector_performance` for breadth. `treasury_rates` for macro context.

**Viable exchanges**: Any market with broad index data. Can construct synthetic indices from our stock universe for each exchange.

---

### M6: Anomaly Detection (Pre-Move Signal)

**Question**: Given anonymized price + volume data, can LLMs identify stocks exhibiting unusual patterns that precede significant moves?

**Why it matters**: Anomaly detection is a bread-and-butter quant task. Tests whether LLMs can spot volume spikes, breakout patterns, or consolidation before moves, without being told what to look for. Unlike M3 (which predicts direction), this asks "is something unusual happening?"

**Input to LLM**:
```
Below are 30 days of price and volume data for 10 anonymized stocks.

Stock A:
Day | Open   | High   | Low    | Close  | Volume
T-29| 45.20  | 45.80  | 44.90  | 45.50  | 1,200,000
...
T-0 | 46.10  | 46.30  | 45.80  | 46.00  | 4,800,000  ← volume 4x average

[Similar for stocks B through J]

Which stocks (if any) show anomalous patterns that suggest an upcoming significant price move (>5% within 10 days)?
For each flagged stock, explain the anomaly.
```

**Ground truth**: Did the stock move >5% (absolute) in the next 10 days?

**Evaluation**:
- Precision/recall for anomaly flags
- Precision@K (top-K flagged stocks)
- False positive rate
- Compare against: Z-score volume filter, Bollinger band squeeze, ATR breakout, random selection

**Data requirements**: `stock_eod` (30+ days + 10 forward)

**Viable exchanges**: All with price data. Best tested on liquid exchanges (US, BSE, NSE, HKSE, LSE)

---

### M7: Pairwise Comparison (Relative Value)

**Question**: Given two anonymized stocks with financial data, which will outperform over the next period?

**Why it matters**: Pairwise comparison is simpler than ranking (M2) and avoids the difficulty of absolute return prediction. It maps to the core quant concept of "long-short" (buy the winner, short the loser). Pairwise accuracy compounds: 60% pairwise accuracy translates to meaningful portfolio alpha when applied systematically. Also, pairwise is the easiest format for LLMs -- binary choice with structured context.

**Input to LLM**:
```
Which stock will deliver higher total return over the next 6 months?

Stock X:
  Revenue Growth (YoY): +8.5%
  Net Margin: 12.3%
  ROE: 18.2%
  P/E: 15.4
  P/B: 2.1
  D/E: 0.42
  Current Ratio: 1.8
  FCF Yield: 6.2%
  Piotroski F-Score: 7
  Trailing 6mo Return: +14.2%
  Trailing Volatility: 22.1%

Stock Y:
  Revenue Growth (YoY): -3.2%
  Net Margin: 18.7%
  ROE: 24.1%
  P/E: 8.7
  P/B: 0.9
  D/E: 0.15
  Current Ratio: 2.1
  FCF Yield: 9.1%
  Piotroski F-Score: 8
  Trailing 6mo Return: -5.1%
  Trailing Volatility: 28.4%

Answer: X or Y
Confidence: 0.0 to 1.0
Brief reasoning (2-3 sentences)
```

**Ground truth**: Actual 6-month forward return comparison.

**Evaluation**:
- Pairwise accuracy (should exceed 50% random baseline)
- Accuracy stratified by return spread (easy pairs with >20% spread vs hard pairs with <5% spread)
- Calibration (does confidence predict accuracy?)
- Long-short portfolio return (buy LLM's pick, hypothetically short the other)
- Compare against: single-factor rules (lower P/E wins, higher ROE wins, higher Piotroski wins)

**Data requirements**: `key_metrics` + `financial_ratios` + `scores` + `stock_eod`

**Viable exchanges**: All with financial data (same as M2)

---

### M8: Valuation Assessment (Over/Under/Fair)

**Question**: Given anonymized financial statements and peer statistics, can LLMs assess whether a stock is overvalued, fairly valued, or undervalued?

**Why it matters**: Valuation is where LLMs should theoretically excel -- it requires synthesizing multiple data points, comparing to peers, and making a judgment. This tests deeper reasoning than binary classification (M1) or ranking (M2). Tests whether the LLM "understands" financial valuation concepts.

**Input to LLM**:
```
Assess the valuation of Stock_A relative to its peers.

Stock_A Financials:
  Revenue: 12.4B (growing 8.5% YoY)
  Net Income: 1.53B (margin 12.3%)
  FCF: 1.82B (yield 5.1%)
  Total Debt: 4.2B, Cash: 2.1B
  Market Cap: 35.7B
  P/E: 23.3, P/B: 3.8, EV/EBITDA: 14.2

Peer Group Median (same industry, similar size):
  P/E: 18.5, P/B: 2.4, EV/EBITDA: 11.8
  Revenue Growth: 5.2%, Net Margin: 10.1%
  FCF Yield: 4.2%, ROE: 14.5%

Assessment options:
  SIGNIFICANTLY OVERVALUED (>30% above fair value)
  MODERATELY OVERVALUED (10-30% above)
  FAIRLY VALUED (within +/-10%)
  MODERATELY UNDERVALUED (10-30% below)
  SIGNIFICANTLY UNDERVALUED (>30% below)

Provide your assessment and explain your reasoning.
Estimate the implied fair value range for the P/E ratio.
```

**Ground truth**: Forward 12-month return. Overvalued stocks should underperform, undervalued should outperform. Quintile analysis: do LLM valuations predict return quintiles?

**Evaluation**:
- Correlation between valuation score and forward return
- Long-short return: long "significantly undervalued" vs short "significantly overvalued"
- Compare against: simple mean-reversion (P/E vs sector median), Graham's formula, PEG ratio

**Data requirements**: `key_metrics` + `financial_ratios` + `income_statement` + `balance_sheet` + `stock_eod` + peer group statistics (computed from sector/size cohorts)

**Viable exchanges**: US, BSE, NSE, HKSE, ASX, XETRA, TSX (need enough peers per sector)

---

### M9: Multi-Step Analysis (Scan + Signal + Size)

**Question**: Can LLMs execute a complete investment workflow when given structured data at each step?

**Why it matters**: This mirrors the ATO_Simulator 4-step methodology and tests the LLM on a realistic workflow rather than an isolated task. It's the most complex experiment and the most representative of real-world use. Tests whether LLMs can maintain consistency across linked decisions.

**Step 1 - Scan**: Given 100 anonymized stocks with basic metrics, filter to a shortlist of 20.
```
Shortlist 20 stocks from these 100 based on quality and value criteria.
[Table: 100 stocks with P/E, ROE, D/E, market cap proxy, revenue growth]
```

**Step 2 - Signal**: For each shortlisted stock, generate entry signal.
```
For each of these 20 stocks, should we: BUY, WATCH, or SKIP?
[Table: 20 stocks with 60-day price series + fundamentals]
```

**Step 3 - Size**: For stocks with BUY signal, allocate portfolio weights.
```
Allocate across these BUY-signal stocks. Total budget: $100,000.
[Table: N stocks with volatility, correlation hints, conviction scores from Step 2]
```

**Ground truth**: Forward return of the final portfolio.

**Evaluation**: Full portfolio metrics (CAGR, Sharpe, max drawdown) over rolling quarterly windows across multiple years. Compare against:
- Random scan + random signal + equal weight
- Traditional screen (Piotroski >= 7) + momentum entry + equal weight
- QARP strategy (existing benchmark)

**Data requirements**: Everything from M2 + M3 + M4 combined.

**Viable exchanges**: US, BSE, NSE (where we have deepest data)

---

### M10: Forex Direction Prediction (Cross-Asset Transfer)

**Question**: Can LLMs predict forex pair direction from price data and macro context?

**Why it matters**: Forex is fundamentally different from equities -- no company fundamentals, driven by macro factors, 24/5 market, mean-reverting at some horizons. Tests whether LLM financial reasoning transfers across asset classes. Also: forex has zero company identity leakage (no anonymization needed). 45+ years of daily data for major pairs. Nobody in the literature has tested LLMs on forex signal generation.

**Input to LLM**:
```
Here are 90 days of daily data for an anonymized currency pair.

Day | Open    | High    | Low     | Close   | Volume
T-89| 1.08234 | 1.08521 | 1.07890 | 1.08110 | 182,000
...
T-0 | 1.09455 | 1.09812 | 1.09201 | 1.09640 | 215,000

Additional context:
- Country A interest rate: 4.50% (unchanged 3 months)
- Country B interest rate: 3.25% (raised 25bp last month)
- Country A CPI (YoY): 2.8% (declining trend)
- Country B CPI (YoY): 3.4% (stable)
- 30-day realized volatility: 8.2% annualized

Predict the direction over the next 20 trading days:
STRENGTHEN (pair rises >1%), WEAKEN (pair falls >1%), FLAT (within +/-1%)
Confidence: 0.0 to 1.0
```

**Ground truth**: Actual 20-day forward return.

**Evaluation**: Accuracy, calibration, simulated PnL with position sizing by confidence.

**Baselines**:
- Random (33%)
- Carry trade (buy high-yield currency)
- Momentum (20-day trend continuation)
- Mean reversion (opposite of 20-day trend)

**Data requirements**: `forex_prices_daily` + `treasury_rates` (for interest rates) + FRED data (for CPI, GDP)

**Viable pairs**: All 70+ pairs with 10+ years of data. Focus on majors: EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD, NZDUSD

---

## Datasets, Variants, and Hyperparameters

### Dataset Tiers

**Tier 1 (Primary — run every experiment)**:
- US (NYSE+NASDAQ): Deepest data, largest universe, direct comparison to all prior work
- BSE/NSE (India): Second-deepest financial data (4,077 + 2,458), never tested in literature
- HKSE (Hong Kong): Bridge between developed and emerging, strong data

**Tier 2 (Secondary — run if Tier 1 produces clear signal)**:
- ASX (Australia): Good data coverage, English-speaking market
- XETRA (Germany): European representation
- TSX (Canada): North American non-US

**Tier 3 (Exploratory — run for select experiments only)**:
- KSC (Korea), SHZ/SHH (China), SAO (Brazil)
- LSE, JPX (price-only experiments: M3, M6)
- Forex (M10 only)

### Model Variants

**Primary models (test all experiments)**:
| Model | Method | Cost Tier |
|-------|--------|-----------|
| Claude Opus 4.6 | claude CLI (`claude -p`) | High (free for us) |
| Claude Sonnet 4.6 | claude CLI (`claude -p --model sonnet`) | Medium (free for us) |
| Claude Haiku 4.5 | claude CLI (`claude -p --model haiku`) | Low (free for us) |

**Secondary models (test M1, M3, M7 — the simplest experiments)**:
| Model | Method | Est. Cost |
|-------|--------|-----------|
| GPT-4o | OpenAI API | ~$5/1000 calls |
| GPT-4o-mini | OpenAI API | ~$0.60/1000 calls |
| Gemini 2.5 Flash | Google API | ~$0.30/1000 calls |
| DeepSeek-R1 | Ollama (local) | $0 (compute) |

**Cost note**: Claude models via CLI have no API cost to us. This is our primary advantage. We can run extensive experiments on Claude variants at zero marginal cost, then selectively compare against paid APIs.

### Prompt Variants (applied to each experiment)

| Variant | Description |
|---------|-------------|
| **V1: Direct** | Minimal instruction, just data + question |
| **V2: Chain-of-Thought** | "Think step by step. First analyze X, then Y, then decide." |
| **V3: Expert Persona** | "You are a senior quantitative analyst at a hedge fund with 20 years of experience." |
| **V4: Structured Analysis** | "Score each factor 1-10, compute a weighted composite, then decide." |

### Hyperparameters

| Parameter | Values | Rationale |
|-----------|--------|-----------|
| **Temperature** | 0 (primary), 0.3, 0.7 | 0 for reproducibility; 0.3/0.7 for variance analysis |
| **History window** | 30, 60, 120 days (price); 2, 3, 5 years (fundamentals) | Tests sensitivity to context length |
| **Forward horizon** | 5 days, 20 days, 60 days, 6 months | Short vs medium vs long-term prediction |
| **Pool size** | 10, 20, 50 stocks per prompt (M2, M4) | Tests scalability of reasoning |
| **Rebalance frequency** | Monthly, quarterly, semi-annual (for backtested experiments) | Standard quant frequencies |

### Data Presentation Variants

| Variant | Format | Rationale |
|---------|--------|-----------|
| **D1: Raw numbers** | Plain numeric table | Baseline |
| **D2: Normalized** | Z-scores relative to cohort | Removes scale effects |
| **D3: Percentile ranks** | "P/E is at 23rd percentile of its cohort" | More interpretable |
| **D4: Change-only** | Only deltas from prior period | Tests trend reasoning |

---

## Execution Priority

| Priority | Experiment | Why First |
|----------|-----------|-----------|
| 1 | **M7: Pairwise Comparison** | Simplest to implement, cheapest per signal, clearest evaluation, binary output |
| 2 | **M1: Earnings Direction** | Direct comparison to Kim et al., well-defined ground truth, tests fundamental reasoning |
| 3 | **M3: Price Direction** | Widest exchange coverage (all markets + forex), tests technical reasoning |
| 4 | **M2: Stock Ranking** | Natural extension of M7 (pairwise → ranking), tests scaling |
| 5 | **M10: Forex Direction** | Novel asset class, no anonymization needed, abundant data |
| 6 | **M4: Portfolio Allocation** | Most practically useful, tests multi-asset reasoning |
| 7 | **M6: Anomaly Detection** | Interesting but harder to evaluate objectively |
| 8 | **M8: Valuation Assessment** | Rich reasoning task, but subjective ground truth |
| 9 | **M5: Regime Classification** | Useful but requires constructing index-level data first |
| 10 | **M9: Multi-Step Analysis** | Most complex, builds on M2+M3+M4, run last |

---

## Statistical Rigor Checklist

For journal-quality results, every experiment must include:

- [ ] Sample size calculation (power analysis) before running
- [ ] Multiple testing correction (Bonferroni or FDR) when comparing >2 models
- [ ] Bootstrap confidence intervals (10,000 resamples) for all key metrics
- [ ] Effect size reporting (Cohen's d for accuracy, annualized alpha for returns)
- [ ] Out-of-sample validation (train/val/test split or rolling walk-forward)
- [ ] Sensitivity analysis across hyperparameters
- [ ] Transaction cost sensitivity (0 bp, 10 bp, 50 bp)
- [ ] Survivorship bias check (include delisted stocks where available)
- [ ] Data snooping check (pre-register hypotheses before seeing results)
- [ ] Model version pinning and logging

---

## What Makes This Novel

1. **First multi-market LLM financial benchmark**: US + India + Hong Kong + Australia + Germany + Canada + Forex
2. **First Claude model family comparison for financial signals**: Opus vs Sonnet vs Haiku on identical tasks
3. **Structured numerical data only**: Avoids the anonymization signal-loss problem documented by Wu et al. (2025)
4. **Portfolio-level evaluation (M4, M9)**: Every prior benchmark tests single-stock only
5. **Cross-asset testing (M10)**: First LLM forex signal generation benchmark
6. **Full reproducibility via CR API**: Anyone can fetch the same data and run the same experiments
7. **Cost-performance Pareto**: First systematic comparison of signal quality per dollar across model families
