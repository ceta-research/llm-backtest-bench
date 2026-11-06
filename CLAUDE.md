# CLAUDE.md

## What this is

llm-backtest-bench benchmarks LLMs on financial signal generation. Its one experiment, M7, shows Claude two anonymized stocks with 15 metrics each, asks which will return more over 6 months, and scores the answers against 14 heuristic baselines. [README.md](README.md) holds the results summary, usage examples and flag table.

## Layout

- `m7/`: the M7 package. The README's "Project Structure" says what each module does. `python3 -m m7.run` is the CLI. `python3 -m m7.analyze` compares finished runs, or writes `report.md` into one.
- `lib/`: backtest helpers. `m7` imports only `lib/ts_client.py` (the TradingStudio API client) and `lib/data_utils.py`. The `lib/` docstrings describe strategy folders (`qarp/`, `piotroski/`) and a `fetch_data()` that aren't in this repo.
- `RESULTS.md` is the full M7 write-up, `RESEARCH.md` the literature review, `METHODOLOGIES.md` the plan for experiments M1 to M10.
- `data/` (parquet cache) and `outputs/runs/<run>/` (one folder per run) are gitignored. Both are created under the current directory, so run everything from the repo root.

## Setup from a fresh clone

The README asks for Python 3.10 or later; these steps use 3.11. From the repo root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- The data step needs `TS_API_KEY`: export it or pass `--api-key`. No code reads `.env`. When present it holds credentials: never quote it.
- Model runs need the `claude` CLI installed and logged in, and the `~/.m7-runner/CLAUDE.md` persona from the README's "Runner Directory" section.
- `--evaluate <run_dir>` and `python3 -m m7.analyze <run_dir>...` need neither the key nor the CLI.

## Tests and CI gates

There are no tests and no CI. With the venv active, from the repo root:

```bash
python -m py_compile m7/*.py lib/*.py
python3 -m m7.run --help
```

This checks the data and pair steps and makes no LLM calls (not run here: needs `TS_API_KEY`):

```bash
python3 -m m7.run --exchange us --pairs-only --pairs 10 --start-year 2024 --end-year 2025 --verbose
```

## How changes ship

Merging to `main` builds and deploys nothing: no CI, no package, no release. No code writes `README.md` or `RESULTS.md`; their numbers are edited by hand from run outputs.

<!-- shared:public-rules v1. Every public repo of ours carries this block word for word. -->
## Rules for every change

- No AI attribution: no Co-Authored-By trailer, no "Generated with Claude Code" line and no session link in commits or PR bodies.
- Never commit a secret, an API key, a server address, or anything that isn't meant to be public.
- One copy of everything. Never copy a block of code: reuse it, or move it into a shared helper. Instructions follow the same rule: each rule lives in one file and other files point to it. Keep files and functions small.
- Treat the default branch as released code: it can reach users without a further step.
- Write plainly: short sentences, lead with the point, no em-dash connectors.
<!-- /shared:public-rules -->

## Gotchas

- `m7/llm.py` runs `claude` with `cwd` set to `~/.m7-runner` (`CLI_RUNNER_DIR`), so benchmark calls load that folder's persona and never this file. Keep `CLI_RUNNER_DIR` and the `cwd=` argument as they are.
- If `~/.m7-runner` is missing, every LLM call fails and is logged as an error.
- Every model run costs Claude subscription time. The four full runs took about 14 hours for 13,200 calls (`RESULTS.md`). Start one only when asked, and try changes with `--pairs 5 --start-year 2024 --end-year 2025` first.
- `--resume` reads nothing back from the run's `config.json`. Pass the original `--model`, `--prompt`, `--thinking-tokens` and `--effort` again, or the remaining pairs run on the defaults. The README's resume example omits them.
- `--resume` treats every pair in `llm_calls.jsonl` as done, failed calls included. Delete the error lines to retry those pairs.
- Without `--pairs-file`, `--resume` runs the data step again for the `--exchange` and year flags given (default US, 2015 to 2025) and needs `TS_API_KEY`. `--resume <run_dir> --pairs-file <run_dir>/pairs.json` skips it.
- The cache in `data/` expires after 24 hours (`CACHE_MAX_AGE_HOURS` in `m7/data.py`), and a later run fetches everything again. The README's "Data" section gives the sizes.
- `model_id` in `m7/config.py` is only a label in the results. The CLI gets the alias `haiku`, `sonnet` or `opus`, so the model called is whatever the installed CLI maps that alias to.
- `BLOG_POST.md` and `REDDIT_POST.md` are post drafts that quote the M7 numbers. Leave them as they are when results change.
- `.venv/` isn't in `.gitignore`. Keep it out of commits.
