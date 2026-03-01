# M7 Pairwise Comparison: Results

Can LLMs pick stocks from anonymized fundamentals? We tested four Claude models on 3,300 stock pairs and compared them against 14 heuristic baselines. The answer: barely.

## Experiment Design

**Task.** Given two anonymized stocks (labeled X and Y) with 15 financial metrics each, predict which will have higher 6-month forward return.

**Universe.** US equities (NYSE, NASDAQ, AMEX), market cap >$100M, non-null core metrics, price data at both entry and exit. Eligible stocks per rebalance date ranged from 3,400 to 5,900.

**Pairs.** 3,300 total. 22 semi-annual rebalance dates from 2015-01 to 2025-07, 150 pairs each. Difficulty was stratified into three buckets:

| Difficulty | Return Spread | Share |
|---|---|---|
| Easy | >15% | 33% |
| Medium | 5-15% | 34% |
| Hard | <5% | 33% |

**Anonymization.** Ticker symbols stripped. Stocks labeled X and Y. The LLM sees only the 15 metrics below, nothing else.

**Data source.** TradingStudio API (FMP warehouse). 38M price rows, 265K metric rows.

### Metrics Shown to LLM

| Category | Metrics |
|---|---|
| Growth | Revenue Growth (YoY) |
| Profitability | Net Margin, Gross Margin, ROE, ROA |
| Valuation | P/E, P/B, EV/EBITDA |
| Financial Health | D/E, Current Ratio, Piotroski F-Score |
| Cash & Income | FCF/Share, Dividend Yield |
| Technical | Trailing 6mo Return, Trailing Volatility |

### LLM Invocation

All models were called via Claude CLI (`claude --print`) with a dedicated CLAUDE.md context instructing the model to act as a quantitative analyst. Prompt variant: `v1_direct` (data block followed by "Which stock? PICK/CONFIDENCE/REASONING"). Total runtime across all four models was approximately 14 hours (13,200 calls). Zero marginal cost since CLI is included with a Claude subscription.

---

## LLM Results

All four models were evaluated on the same 3,300 pairs.

| Model | Overall | Easy | Medium | Hard | Avg Confidence | Avg Latency | Errors |
|---|---|---|---|---|---|---|---|
| Haiku | 52.5% (1733/3299) | 56.8% | 50.7% | 50.1% | 0.691 | 14.3s | 1 |
| Sonnet | 52.6% (1737/3300) | 58.3% | 51.6% | 47.9% | 0.667 | 5.5s | 0 |
| Sonnet+think (10k) | 52.7% (1738/3299) | 58.2% | 51.9% | 47.8% | 0.677 | 5.4s | 1 |
| Opus (effort=high) | 52.7% (1737/3295) | 57.5% | 51.5% | 49.1% | 0.731 | 7.4s | 5 |

All models cluster in a 0.2 percentage point band: 52.5% to 52.7%. The range is noise.

---

## Baseline Results

14 heuristic strategies were run on the same 3,300 pairs. No LLM involved, just mechanical rules applied to the same 15 metrics.

| Baseline | Overall | Easy | Medium | Hard | Description |
|---|---|---|---|---|---|
| random | 50.3% | 49.4% | 52.2% | 49.1% | Seeded coin flip |
| momentum | 49.8% | 51.4% | 49.1% | 48.8% | Pick higher trailing 6mo return |
| mean_reversion | 50.1% | 47.9% | 51.0% | 51.4% | Pick lower trailing return (contrarian) |
| lower_pe | 50.5% | 46.5% | 52.5% | 52.5% | Pick lower P/E |
| value | 50.8% | 49.0% | 52.4% | 51.0% | Low P/E + P/B + EV/EBITDA + high yield |
| greenblatt | 50.9% | 54.9% | 50.1% | 47.6% | Magic Formula: earnings yield + ROE |
| garp | 50.9% | 51.1% | 50.3% | 51.2% | Growth at Reasonable Price: revenue growth / PE |
| composite | 51.0% | 55.1% | 50.6% | 47.4% | Equal-weight: 1/PE + ROE + momentum + Piotroski |
| lower_pb | 51.1% | 50.5% | 52.2% | 50.5% | Pick lower P/B |
| higher_roe | 51.2% | 55.4% | 49.9% | 48.3% | Pick higher ROE |
| higher_piotroski | 51.5% | 54.0% | 50.7% | 49.8% | Pick higher Piotroski F-Score |
| low_vol | 51.9% | 54.1% | 52.6% | 49.0% | Pick less volatile stock |
| quality | 52.0% | 55.6% | 50.4% | 50.0% | ROE + ROA + margins + Piotroski + low leverage |
| kitchen_sink | 52.0% | 50.4% | 54.5% | 51.1% | All 15 factors, literature-based weights |

The best heuristics (quality, kitchen_sink) hit 52.0%. The LLMs top out at 52.7%. The gap is 0.7 percentage points.

---

## Accuracy by Difficulty

This is the most telling breakdown. All models follow the same curve: decent on easy pairs, coin-flip on hard ones.

| Difficulty | Haiku | Sonnet | Sonnet+think | Opus | Best Baseline |
|---|---|---|---|---|---|
| Easy (>15% spread) | 56.8% | 58.3% | 58.2% | 57.5% | 55.6% (quality) |
| Medium (5-15%) | 50.7% | 51.6% | 51.9% | 51.5% | 54.5% (kitchen_sink) |
| Hard (<5%) | 50.1% | 47.9% | 47.8% | 49.1% | 52.5% (lower_pe) |

On easy pairs (return spread >15%), LLMs beat all baselines by 2-3 points. On medium pairs, the kitchen_sink heuristic actually beats every LLM. On hard pairs, Sonnet and Sonnet+think fall below 50%, meaning they would have been better off flipping a coin.

---

## Accuracy by Year

| Year | Haiku | Sonnet | Sonnet+think |
|---|---|---|---|
| 2015 | 52.3% | 54.3% | 53.7% |
| 2016 | 56.7% | 51.3% | 52.0% |
| 2017 | 56.3% | 51.0% | 51.7% |
| 2018 | 48.0% | 50.3% | 50.3% |
| 2019 | 52.3% | 54.7% | 54.3% |
| 2020 | 45.7% | 44.3% | 44.7% |
| 2021 | 52.8% | 57.7% | 57.0% |
| 2022 | 55.3% | 55.3% | 55.3% |
| 2023 | 54.7% | 55.7% | 56.3% |
| 2024 | 50.3% | 51.7% | 51.7% |
| 2025 | 53.3% | 52.7% | 52.5% |

2020 stands out. All models dropped to 44-46%, well below random. COVID-era price action was driven by macro shock and liquidity, not fundamentals. The models had no way to anticipate that from balance sheet metrics alone.

The best year varies by model. Haiku peaked in 2016-2017, Sonnet in 2021. No model is consistently strong across years.

---

## Calibration

Models report a confidence score (0.5 to 1.0) with each pick. Good calibration means a 70% confidence prediction should be correct 70% of the time.

### Haiku

| Confidence Bin | Actual Accuracy | Expected |
|---|---|---|
| 0.50 - 0.60 | 51.4% | ~55% |
| 0.60 - 0.70 | 51.8% | ~65% |
| 0.70 - 0.80 | 53.1% | ~75% |
| 0.80 - 0.90 | 52.4% | ~85% |
| 0.90 - 1.00 | 58.0% | ~95% |

ECE: 0.1706

### Sonnet

| Confidence Bin | Actual Accuracy | Expected |
|---|---|---|
| 0.50 - 0.60 | 50.3% | ~55% |
| 0.60 - 0.70 | 51.7% | ~65% |
| 0.70 - 0.80 | 55.1% | ~75% |
| 0.80 - 0.90 | 56.5% | ~85% |
| 0.90 - 1.00 | 56.0% | ~95% |

ECE: 0.1532

Both models are massively overconfident. When Haiku says 85% confident, it's right 52% of the time. When Sonnet says 85%, it's right 57%. The gap between stated confidence and actual accuracy widens at every level. ECE scores of 0.15-0.17 confirm systematic miscalibration.

Sonnet is marginally better calibrated than Haiku, but both are poor in absolute terms.

---

## Pick Bias

| Model | Picks X | Picks Y |
|---|---|---|
| Haiku | 43.4% | 56.6% |
| Sonnet | 54.7% | 45.3% |
| Sonnet+think | 55.0% | 45.0% |

Models have a positional bias. Haiku favors Y (the second stock presented). Sonnet and Sonnet+think favor X (the first). Since stock assignment to X/Y is random, this bias shouldn't affect overall accuracy, but it reveals that the models aren't making purely metric-driven decisions. Presentation order matters.

---

## Extended Thinking: Does It Help?

No. Sonnet and Sonnet+think (10k budget) agreed on 97.6% of pairs (3,220 out of 3,299). On the 79 pairs where they disagreed, thinking got 40 right versus 39 for no-thinking. That's a coin flip.

| Metric | Value |
|---|---|
| Common pairs evaluated | 3,299 |
| Agreement | 3,220 (97.6%) |
| Disagreement | 79 (2.4%) |
| Thinking correct (on disagreements) | 40 |
| No-thinking correct (on disagreements) | 39 |

Extended thinking adds compute cost and latency (though in this run, latency was similar) without changing the outcome. The task doesn't benefit from chain-of-thought because the underlying signal is too weak for any reasoning strategy to extract.

---

## Opus vs Haiku: Does Scale Matter?

No. Opus (effort=high) scored 52.7%. Haiku scored 52.5%. The difference is 0.2 points on 3,300 pairs, well within noise. Opus also had 5 errors (malformed responses) compared to Haiku's 1.

The jump from the smallest model (Haiku) to the largest (Opus) produced no meaningful improvement. This suggests the task is bottlenecked by signal, not by model capability.

---

## Key Findings

**1. LLMs provide negligible edge over simple heuristics.** All four models landed at 52.5-52.7%. The best heuristic baselines (quality, kitchen_sink) hit 52.0%. The 0.7-point gap is not practically meaningful.

**2. Extended thinking doesn't help.** Sonnet+think matched Sonnet almost exactly. 97.6% agreement. On disagreements, it was 40-39. A literal coin flip.

**3. Model scale doesn't help.** Opus performed identically to Haiku. The problem isn't reasoning depth. It's signal scarcity.

**4. Calibration is broken.** ECE of 0.15-0.17. Models report high confidence on predictions that are barely above chance. A 90% confidence prediction is correct ~57% of the time.

**5. Easy pairs are where the edge lives.** LLMs hit 57-58% on pairs with >15% return spread. On hard pairs (<5% spread), they're at or below 50%.

**6. The kitchen_sink baseline is underrated.** It uniquely performs well on medium (54.5%) and hard (51.1%) pairs. No LLM matches it on either bucket. The all-factor weighted heuristic captures something the LLMs don't.

**7. COVID breaks everything.** All models dropped to 44-46% in 2020. Fundamental metrics can't predict macro shocks.

**8. Momentum is below random.** Trailing 6-month return does not predict forward 6-month return in this dataset (49.8%). This is consistent with the mean-reversion baseline also being near 50%.

---

## Interpretation

The pairwise comparison task strips away everything except fundamental metrics. No sector labels, no macro context, no news, no company names. With only 15 numbers to work with and a 6-month horizon, the forward return signal is extremely weak.

LLMs are doing something, just not much. They beat random (50.3%) by about 2 points. They beat simple single-factor heuristics. But they don't meaningfully beat a weighted combination of all 15 factors. The "intelligence" of the LLM, across model sizes and with or without extended thinking, amounts to roughly the same thing as applying textbook factor weights.

This doesn't mean LLMs are useless for financial analysis. It means that on a stripped-down, anonymized pairwise task with only fundamental metrics and a 6-month horizon, there isn't enough signal for any method to extract. The ceiling on this task appears to be around 53%.

---

## Prompt Variant Test (63 Pairs, Sonnet)

We tested four prompt strategies on a stratified 63-pair sample (21 easy, 21 medium, 21 hard) using Sonnet.

| Prompt | Accuracy | Avg Latency | Description |
|---|---|---|---|
| v1_direct | 61.9% | 5.3s | Data block + "Which stock? PICK/CONFIDENCE/REASONING" |
| v2_cot | 57.1% | 24.5s | "Think step by step: 1) valuation 2) profitability 3) health 4) momentum 5) decide" |
| v4_structured | 57.1% | 9.7s | "Score each category 1-10 for both stocks, then decide" |
| v3_expert | 55.6% | 23.2s | System prompt "You are a senior quant analyst..." + data block |

The simplest prompt wins. Chain-of-thought, expert personas, and structured scoring all hurt accuracy while increasing latency 2-5x. The direct prompt's 61.9% is inflated by the small sample (63 pairs gives wide CIs), but the relative ranking is clear: more prompting complexity = worse results.

None of the variants showed enough promise to justify a full 3,300-pair run.

### Run Directories (Prompt Variants)

```
outputs/runs/20260301_144754_us_claude-sonnet_v1_direct/     (63 pairs)
outputs/runs/20260301_144747_us_claude-sonnet_v2_cot/        (63 pairs)
outputs/runs/20260301_144748_us_claude-sonnet_v3_expert/     (63 pairs)
outputs/runs/20260301_144749_us_claude-sonnet_v4_structured/ (63 pairs)
```

---

## Infrastructure

| Component | Detail |
|---|---|
| LLM invocation | Claude CLI (`claude --print`), dedicated CLAUDE.md context |
| Logging | JSONL append-only with resume support |
| Data handling | Yearly price data chunking (5M API row limit, 38M total rows) |
| Cost | Zero marginal (CLI included with Claude subscription) |
| Total runtime | ~14 hours across 4 models (13,200 calls) |

### Run Directories

```
outputs/runs/20260227_143630_us_claude-haiku_v1_direct/
outputs/runs/20260227_152618_us_claude-sonnet_v1_direct/
outputs/runs/20260228_045144_us_claude-sonnet_v1_direct_think10000/
outputs/runs/20260228_125527_us_claude-opus_v1_direct_efforthigh/
```
