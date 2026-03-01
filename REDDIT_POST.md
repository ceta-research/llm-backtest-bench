# Reddit Post Draft

**Target subreddits:** r/quant, r/algotrading, r/MachineLearning

---

## Title Options

1. "I ran 13,200 LLM calls to test if Claude can pick stocks from fundamentals. It can't."
2. "Benchmarking Claude (Haiku/Sonnet/Opus) on pairwise stock selection: 3,300 pairs, 10 years, 14 baselines"
3. "LLMs vs a spreadsheet formula for stock picking: results from 13,200 API calls"

---

## Post Body (r/quant / r/algotrading version)

**Title: I ran 13,200 LLM calls to test if Claude can pick stocks from fundamentals. It can't.**

I built a benchmark to test whether LLMs can pick stocks from anonymized fundamental data. 3,300 stock pairs, 10 years of US equities, four Claude models, 14 heuristic baselines. Sharing the results because I found them surprising.

**Setup**

Each pair has two anonymized stocks (X and Y) with 15 metrics: P/E, P/B, EV/EBITDA, ROE, ROA, margins, D/E, Piotroski, trailing return, volatility, etc. The model has to predict which one delivers higher 6-month forward return. No company names, no sector, no macro context.

3,300 pairs across 22 semi-annual dates from 2015-2025. Stratified by difficulty (return spread: >15%, 5-15%, <5%).

**Results**

| Model | Accuracy |
|---|---|
| Haiku (cheapest) | 52.5% |
| Sonnet | 52.6% |
| Sonnet + extended thinking | 52.7% |
| Opus (most expensive, effort=high) | 52.7% |
| kitchen_sink baseline (weighted formula) | 52.0% |
| random | 50.3% |

All four models land in a 0.2pp band. The cheapest model matches the most expensive. Extended thinking changes literally nothing (97.6% agreement with non-thinking, 40-39 coin flip on disagreements).

A weighted formula using all 15 metrics with textbook factor weights gets 52.0%. The best LLM gets 52.7%. On medium-difficulty pairs, the formula actually beats every LLM (54.5% vs 51.9%).

**Other findings**

- Confidence scores are useless. When the model says 90% confident, it's right 57% of the time. ECE = 0.14-0.20.
- Simple "which stock?" prompt beats chain-of-thought, expert persona, and structured scoring prompts.
- COVID 2020: all models drop to 44-46% (below random). Fundamentals can't predict macro shocks.
- Momentum baseline (pick higher trailing return) is below random at 49.8%.

**My takeaway**

The task is signal-starved. 15 fundamental metrics and a 6-month horizon don't contain enough predictive information for any method to exploit. The ceiling is around 53%. LLMs aren't doing anything special here. Their "reasoning" amounts to roughly the same factor weighting you could write in a spreadsheet.

This doesn't mean LLMs are useless for finance. It means removing context (company identity, sector, macro, news) removes their advantage. They're good at synthesizing messy, diverse information. Give them only 15 numbers and they have nothing to synthesize.

Full methodology: 38M price rows, 265K metric rows, US equities (NYSE/NASDAQ/AMEX), market cap >$100M, Wilson 95% CIs, McNemar's test for paired comparisons.

Happy to answer questions or share the code.

---

## Shorter Version (r/MachineLearning)

**Title: Benchmarking Claude on pairwise stock selection: 13,200 calls, 4 models, all cluster at 52.5-52.7%**

Ran a controlled experiment: give Claude (Haiku through Opus) two anonymized stocks with 15 fundamental metrics, ask which has higher 6-month forward return. 3,300 pairs, 10 years of US equities.

Results: All 4 models cluster at 52.5-52.7%. A weighted formula using the same 15 metrics gets 52.0%. Extended thinking (10k budget) changes nothing. Model scale (Haiku vs Opus) changes nothing. Confidence calibration is terrible (90% confidence = 57% accuracy).

The interesting bit: on medium-difficulty pairs (5-15% return spread), a kitchen_sink heuristic (all 15 factors, textbook weights) beats every LLM. The models only pull ahead on easy pairs where the answer is obvious.

Takeaway: on a signal-starved task (just numbers, no context), LLMs don't outperform simple factor models. Their advantage likely requires richer, unstructured inputs.

Details: McNemar's test, Wilson CIs, 14 baselines, 4 prompt variants tested. Code available.
