# We Ran 13,200 LLM Calls to Test If Claude Can Pick Stocks. Here's What Happened.

Can a large language model pick stocks from financial data alone? We tested this by feeding Claude anonymized fundamental metrics for 3,300 stock pairs and asking it to predict which one would outperform over six months. We ran four models, compared against 14 heuristic baselines, and covered 10 years of US equities.

The short answer: barely better than a weighted formula you could write in a spreadsheet.

## The Setup

We built a pairwise comparison benchmark called M7. The idea is simple. Take two stocks, strip the names, show the model 15 financial metrics (P/E, ROE, revenue growth, trailing return, etc.), and ask: "Which one will deliver higher total return over the next 6 months?"

The dataset covers US equities (NYSE, NASDAQ, AMEX) from January 2015 to July 2025. We used 38 million price rows and 265,000 metric rows from FMP via the TradingStudio API. Stocks had to have market cap above $100M and non-null metrics to be eligible. Each rebalance date had 3,400 to 5,900 eligible stocks.

We generated 3,300 pairs across 22 semi-annual rebalance dates (150 pairs per date). Pairs were stratified by difficulty:

- **Easy** (33%): forward return spread >15% between the two stocks
- **Medium** (34%): spread between 5% and 15%
- **Hard** (33%): spread under 5%

The LLM never sees company names, sector labels, or any context beyond 15 numbers. It just gets "Stock X" and "Stock Y" with their metrics.

## What We Tested

Four Claude models, all using the same direct prompt ("Which stock will deliver higher total return?"):

- **Haiku** (smallest, cheapest)
- **Sonnet** (mid-tier)
- **Sonnet with extended thinking** (10,000 token thinking budget)
- **Opus with effort=high** (largest, most expensive)

Plus 14 heuristic baselines ranging from single-factor rules (pick lower P/E, pick higher ROE) to multi-factor weighted models using all 15 metrics.

All LLM calls were made via Claude CLI (`claude --print`), so the entire experiment ran at zero marginal cost on a Claude subscription. Total runtime was about 14 hours.

## Results

| Model | Accuracy | Easy Pairs | Medium | Hard |
|---|---|---|---|---|
| Haiku | 52.5% | 56.8% | 50.7% | 50.1% |
| Sonnet | 52.6% | 58.3% | 51.6% | 47.9% |
| Sonnet+think | 52.7% | 58.2% | 51.9% | 47.8% |
| Opus (high effort) | 52.7% | 57.5% | 51.5% | 49.1% |

All four models cluster in a 0.2 percentage point band. The cheapest model (Haiku) matches the most expensive (Opus). Extended thinking changes nothing.

For comparison, here are the baselines:

| Method | Accuracy | Description |
|---|---|---|
| kitchen_sink | 52.0% | All 15 factors, literature-based weights |
| quality | 52.0% | ROE + margins + Piotroski + low leverage |
| low_vol | 51.9% | Pick less volatile stock |
| random | 50.3% | Seeded coin flip |
| momentum | 49.8% | Pick higher trailing return |

The best heuristic (a simple weighted formula across all 15 metrics) hits 52.0%. The best LLM hits 52.7%. That's a 0.7 percentage point gap on 3,300 pairs.

## Five Things That Surprised Us

### 1. Model scale doesn't matter

Going from Haiku to Opus changed accuracy by 0.2 points. That's noise. The task isn't bottlenecked by reasoning capability. It's bottlenecked by signal.

### 2. Extended thinking is useless here

Sonnet and Sonnet+think agreed on 97.6% of pairs. On the 79 disagreements, thinking got 40 right, no-thinking got 39. A literal coin flip. Chain-of-thought doesn't help when the underlying signal is too weak.

### 3. Confidence scores are meaningless

When the models say they're 90% confident, they're right about 57% of the time. Expected Calibration Error ranges from 0.14 to 0.20. The models can't tell easy picks from hard ones, even though they claim to.

| Confidence Bucket | Actual Accuracy |
|---|---|
| 0.50 - 0.60 | 50-52% |
| 0.60 - 0.70 | 51-52% |
| 0.70 - 0.80 | 53-55% |
| 0.80 - 0.90 | 52-59% |
| 0.90 - 1.00 | 56-59% |

### 4. Simple prompts beat complex ones

We tested four prompt strategies on a 63-pair sample:

| Prompt Style | Accuracy |
|---|---|
| Direct ("which stock?") | 61.9% |
| Chain-of-thought (step by step) | 57.1% |
| Structured scoring (1-10 per category) | 57.1% |
| Expert persona ("senior quant analyst") | 55.6% |

More prompting complexity made things worse. The direct prompt won by 5+ points over the expert persona.

### 5. COVID broke everything

All models dropped to 44-46% accuracy in 2020. That's worse than random. Fundamental metrics can't predict macro shocks, and the models had no way to know a pandemic was about to reshape price action.

## The Kitchen Sink Problem

The most interesting finding was about the `kitchen_sink` baseline. This is just a weighted sum of all 15 metrics using textbook factor weights (value 25%, quality 30%, momentum 15%, growth 15%, safety 15%). No machine learning, no optimization. Just multiply each metric by a weight, sum, and pick the higher score.

This simple formula beat every LLM on medium-difficulty pairs (54.5% vs 51.9% for the best LLM) and matched them on hard pairs (51.1% vs 50.1%). The LLMs only pulled ahead on easy pairs where the return spread was large enough that the answer was obvious.

In other words: the LLM's "intelligence" on this task amounts to roughly the same thing as applying textbook factor weights. It doesn't extract some hidden pattern from the data that a formula can't.

## What This Means

This experiment tested a specific, narrow question: can an LLM predict relative stock returns from anonymized fundamentals alone? The answer is "barely, and not better than a spreadsheet."

This doesn't mean LLMs are useless for financial work. It means that on a stripped-down task with only 15 numbers and no context, the forward return signal is too weak for any method to exploit. The ceiling on this task appears to be around 53%.

What would probably help: sector context, macro indicators, earnings surprises, management quality signals, news sentiment. Everything we deliberately excluded. LLMs are good at synthesizing diverse, unstructured information. Reducing the input to 15 numbers removes their advantage.

## Methodology Details

- **Universe**: US equities (NYSE, NASDAQ, AMEX), market cap >$100M
- **Period**: January 2015 to July 2025 (22 semi-annual rebalance dates)
- **Pairs**: 3,300 total (150 per date), stratified by difficulty
- **Forward return**: 6-month total return from rebalance date
- **LLM invocation**: Claude CLI (`claude --print`), JSON output, no tools
- **Statistical tests**: McNemar's test for LLM vs each baseline (paired binary outcomes)
- **Confidence intervals**: Wilson score 95% CIs

## Code

The full benchmark code is open. Pipeline, pair generation, prompt construction, baselines, evaluation, and analysis tools.

*Data: FMP warehouse via TradingStudio API, 38M price rows, 265K metric rows*
