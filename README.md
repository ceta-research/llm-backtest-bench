# llm-backtest-bench

Benchmarking LLMs on financial signal generation. Can Claude pick stocks from anonymized fundamentals?

## M7: Pairwise Stock Comparison

The first experiment. Two anonymized stocks, 15 financial metrics each, one question: which delivers higher 6-month return?

**Results:** All four Claude models (Haiku through Opus) cluster at 52.5-52.7% accuracy. A weighted heuristic using the same 15 metrics gets 52.0%. Extended thinking and model scale make no difference.

See [RESULTS.md](RESULTS.md) for the full write-up.

### Quick Numbers

| Model | Accuracy | 95% CI |
|---|---|---|
| Haiku | 52.5% | 50.8-54.2% |
| Sonnet | 52.6% | 50.9-54.3% |
| Sonnet + extended thinking | 52.7% | 51.0-54.4% |
| Opus (effort=high) | 52.7% | 51.0-54.4% |
| kitchen_sink baseline | 52.0% | - |
| random | 50.3% | - |

3,300 pairs, 22 rebalance dates, 10 years of US equities (2015-2025), 14 heuristic baselines, McNemar's paired tests.

## Setup

### Requirements

- Python 3.10+
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) (included with Claude subscription)
- [TradingStudio API key](https://tradingstudio.finance) (for fetching financial data)

```bash
pip install -r requirements.txt
export TS_API_KEY=your_key_here
```

The Claude CLI must be installed and authenticated separately. All LLM calls go through `claude --print`, so there's no need for an Anthropic API key.

### Runner Directory

The CLI is invoked from `~/.m7-runner/` to avoid picking up any parent project's CLAUDE.md. Create it with the quant analyst persona:

```bash
mkdir -p ~/.m7-runner
cat > ~/.m7-runner/CLAUDE.md << 'EOF'
You are a quantitative financial analyst participating in a research study on stock selection.
Your task is to compare two anonymized stocks based on their financial metrics and predict
which one will deliver a higher total return over the next 6 months.

This is an academic benchmarking exercise, not investment advice. Always provide your best
analytical judgment.

Respond in exactly this format:
PICK: X or Y
CONFIDENCE: 0.50 to 1.00
REASONING: Brief explanation (1-3 sentences)
EOF
```

## Usage

### Generate pairs only (no LLM calls)

```bash
python3 -m m7.run --exchange us --pairs-only --pairs 10 --start-year 2024 --end-year 2025 --verbose
```

### Quick test with Haiku

```bash
python3 -m m7.run --exchange us --model claude-haiku --prompt v1_direct --pairs 5 --start-year 2024 --end-year 2025 --verbose
```

### Full run

```bash
python3 -m m7.run --exchange us --model claude-sonnet --prompt v1_direct
```

### Resume a previous run

```bash
python3 -m m7.run --resume outputs/runs/<run_dir>
```

### Reuse pairs from another run (skip data loading)

```bash
python3 -m m7.run --exchange us --model claude-opus --prompt v1_direct \
  --pairs-file outputs/runs/<existing_run>/pairs.json --effort high
```

### Evaluate an existing run

```bash
python3 -m m7.run --evaluate outputs/runs/<run_dir>
```

### Compare multiple runs

```bash
python3 -m m7.analyze outputs/runs/<run1> outputs/runs/<run2> outputs/runs/<run3>
```

## CLI Flags

| Flag | Description |
|---|---|
| `--exchange` | Exchange preset: us, india, hongkong, australia, germany, canada |
| `--model` | claude-haiku, claude-sonnet, claude-opus |
| `--prompt` | v1_direct, v2_cot, v3_expert, v4_structured |
| `--pairs` | Pairs per rebalance date (default: 150) |
| `--start-year` | Start year (default: 2015) |
| `--end-year` | End year (default: 2025) |
| `--thinking-tokens` | Enable extended thinking with N tokens (e.g., 10000) |
| `--effort` | Effort level for Claude CLI: low, medium, high |
| `--pairs-file` | Skip data loading, reuse existing pairs.json |
| `--pairs-only` | Generate pairs and exit (no LLM calls) |
| `--resume` | Resume a previous run from output directory |
| `--evaluate` | Re-evaluate an existing run (no new LLM calls) |

## Project Structure

```
llm-backtest-bench/
├── m7/                  # M7 experiment
│   ├── config.py        # Constants, metrics, model definitions
│   ├── data.py          # Fetch from API, cache to parquet, load DuckDB
│   ├── pairs.py         # Pair generation, stratification, anonymization
│   ├── prompts.py       # 4 prompt variants + response parser
│   ├── llm.py           # Claude CLI runner with logging and resume
│   ├── baselines.py     # 14 heuristic baselines
│   ├── evaluate.py      # Accuracy, calibration, long-short, McNemar's
│   ├── run.py           # CLI entry point
│   └── analyze.py       # Cross-run comparison
├── lib/                 # Shared utilities (API client, metrics)
├── RESULTS.md           # Full experiment results
├── RESEARCH.md          # Literature review
├── data/                # Cached parquet files (gitignored)
└── outputs/             # Run results (gitignored)
    └── runs/{run_id}/
        ├── config.json
        ├── pairs.json
        ├── llm_calls.jsonl
        └── summary.json
```

## Baselines

14 heuristic strategies, from single-factor to multi-factor:

| Baseline | Description |
|---|---|
| random | Seeded coin flip |
| lower_pe | Pick lower P/E |
| higher_roe | Pick higher ROE |
| higher_piotroski | Pick higher Piotroski F-Score |
| lower_pb | Pick lower P/B |
| momentum | Pick higher trailing 6mo return |
| mean_reversion | Pick lower trailing return (contrarian) |
| low_vol | Pick less volatile stock |
| composite | Equal-weight: value + quality + momentum + Piotroski |
| greenblatt | Magic Formula: earnings yield + ROE |
| garp | Growth at Reasonable Price: revenue growth / PE |
| quality | ROE + margins + Piotroski + low leverage |
| value | Low P/E + P/B + EV/EBITDA + high dividend yield |
| kitchen_sink | All 15 factors, literature-based weights |

## Data

Financial data is fetched from the [TradingStudio API](https://tradingstudio.finance) (FMP warehouse) and cached locally as parquet files. The US dataset is approximately 38M price rows and 265K metric rows covering 22K symbols.

Price data is fetched in yearly chunks to stay within API row limits. Derived features (trailing return, trailing volatility, revenue growth YoY) are computed in DuckDB after loading.

## License

MIT
