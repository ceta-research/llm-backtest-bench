"""M7 Pairwise Comparison: CLI entry point.

Usage:
    # Generate pairs only (no LLM calls)
    python3 -m m7.run --exchange us --pairs-only --pairs 10 --start-year 2024 --end-year 2025 --verbose

    # Quick test with Haiku (cheap)
    python3 -m m7.run --exchange us --model claude-haiku --prompt v1_direct --pairs 5 --start-year 2024 --end-year 2025 --verbose

    # Full run
    python3 -m m7.run --exchange us --model claude-sonnet --prompt v1_direct

    # Resume a previous run
    python3 -m m7.run --resume outputs/runs/20250227_us_claude-sonnet_v1_direct

    # Evaluate an existing run
    python3 -m m7.run --evaluate outputs/runs/20250227_us_claude-sonnet_v1_direct
"""

import argparse
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

from .config import (
    MODELS, PROMPT_VARIANTS, EXCHANGE_PRESETS,
    PAIRS_PER_REBALANCE, START_YEAR, END_YEAR, REBALANCE_FREQUENCY,
)
from .data import fetch_and_cache
from .pairs import generate_pairs, save_pairs, load_pairs
from .llm import LLMRunner, load_llm_results
from .baselines import evaluate_all_baselines
from .evaluate import evaluate_run, save_summary, print_summary

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.data_utils import generate_rebalance_dates


def parse_args():
    parser = argparse.ArgumentParser(
        description="M7 Pairwise Comparison: LLM vs heuristic stock picking"
    )

    # Exchange selection
    parser.add_argument("--exchange", type=str, default="us",
                        choices=list(EXCHANGE_PRESETS.keys()),
                        help="Exchange preset (default: us)")

    # Model and prompt
    parser.add_argument("--model", type=str, default="claude-sonnet",
                        choices=list(MODELS.keys()),
                        help="Model to use (default: claude-sonnet)")
    parser.add_argument("--prompt", type=str, default="v1_direct",
                        choices=PROMPT_VARIANTS,
                        help="Prompt variant (default: v1_direct)")

    # Experiment parameters
    parser.add_argument("--thinking-tokens", type=int, default=0,
                        help="Enable extended thinking with N tokens (e.g. 10000)")
    parser.add_argument("--effort", type=str, default=None,
                        choices=["low", "medium", "high"],
                        help="Effort level for claude CLI (e.g. high for Opus)")
    parser.add_argument("--pairs", type=int, default=PAIRS_PER_REBALANCE,
                        help=f"Pairs per rebalance date (default: {PAIRS_PER_REBALANCE})")
    parser.add_argument("--start-year", type=int, default=START_YEAR,
                        help=f"Start year (default: {START_YEAR})")
    parser.add_argument("--end-year", type=int, default=END_YEAR,
                        help=f"End year (default: {END_YEAR})")

    # Modes
    parser.add_argument("--pairs-only", action="store_true",
                        help="Generate pairs and exit (no LLM calls)")
    parser.add_argument("--pairs-file", type=str, default=None,
                        help="Use existing pairs.json (skip data fetch + pair generation)")
    parser.add_argument("--resume", type=str, default=None,
                        help="Resume a previous run from output directory")
    parser.add_argument("--evaluate", type=str, default=None,
                        help="Evaluate an existing run (no new LLM calls)")

    # Output
    parser.add_argument("--output", type=str, default=None,
                        help="Output directory (auto-generated if not specified)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")

    # API
    parser.add_argument("--api-key", type=str, default=None,
                        help="TradingStudio API key (or set TS_API_KEY)")

    return parser.parse_args()


def main():
    args = parse_args()

    exchanges = EXCHANGE_PRESETS[args.exchange]

    # Handle evaluate-only mode
    if args.evaluate:
        _evaluate_existing(args.evaluate, args.verbose)
        return

    # Determine output directory
    if args.resume:
        output_dir = args.resume
    elif args.output:
        output_dir = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        thinking_suffix = f"_think{args.thinking_tokens}" if args.thinking_tokens else ""
        effort_suffix = f"_effort{args.effort}" if args.effort else ""
        output_dir = f"outputs/runs/{timestamp}_{args.exchange}_{args.model}_{args.prompt}{thinking_suffix}{effort_suffix}"

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save run config
    config = {
        "exchange": args.exchange,
        "exchanges": exchanges,
        "model": args.model,
        "prompt_variant": args.prompt,
        "pairs_per_rebalance": args.pairs,
        "start_year": args.start_year,
        "end_year": args.end_year,
        "rebalance_frequency": REBALANCE_FREQUENCY,
        "thinking_tokens": args.thinking_tokens,
        "effort": args.effort,
        "timestamp": datetime.now().isoformat(),
    }
    config_path = output_dir / "config.json"
    if not config_path.exists():
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

    print("=" * 65)
    print("  M7 PAIRWISE COMPARISON")
    print(f"  Exchange: {args.exchange} ({', '.join(exchanges)})")
    print(f"  Model: {args.model} | Prompt: {args.prompt}")
    print(f"  Period: {args.start_year}-{args.end_year} | Pairs/date: {args.pairs}")
    print(f"  Output: {output_dir}")
    print("=" * 65)

    t0 = time.time()

    if args.pairs_file:
        # Skip data fetch + pair generation, use existing pairs
        print("\nPhase 1-2: Loading pairs from file...")
        all_pairs = load_pairs(args.pairs_file)
        # Copy pairs file into output dir
        pairs_path = output_dir / "pairs.json"
        if not pairs_path.exists():
            save_pairs(all_pairs, output_dir)
        data_time = 0
        pairs_time = 0
    else:
        # Phase 1: Fetch and cache data
        print("\nPhase 1: Data pipeline...")
        con = fetch_and_cache(
            exchanges, args.start_year, args.end_year,
            api_key=args.api_key, verbose=args.verbose,
        )
        data_time = time.time() - t0
        print(f"  Data loaded in {data_time:.0f}s")

        # Phase 2: Generate pairs
        print("\nPhase 2: Generating pairs...")
        t1 = time.time()

        pairs_path = output_dir / "pairs.json"
        if pairs_path.exists() and args.resume:
            print("  Loading existing pairs...")
            all_pairs = load_pairs(pairs_path)
        else:
            rebalance_dates = generate_rebalance_dates(
                args.start_year, args.end_year, REBALANCE_FREQUENCY
            )
            all_pairs = []
            for d in rebalance_dates:
                pairs = generate_pairs(
                    con, d, exchanges, n_pairs=args.pairs,
                    verbose=args.verbose,
                )
                all_pairs.extend(pairs)

            save_pairs(all_pairs, output_dir)

        pairs_time = time.time() - t1
        con.close()

    print(f"  {len(all_pairs)} total pairs in {pairs_time:.0f}s")

    # Difficulty distribution
    diff_counts = {}
    for p in all_pairs:
        diff_counts[p["difficulty"]] = diff_counts.get(p["difficulty"], 0) + 1
    print(f"  Difficulty: {diff_counts}")

    if args.pairs_only:
        print(f"\n  Pairs saved to {output_dir / 'pairs.json'}")
        if args.verbose and all_pairs:
            print("\n  Sample pair:")
            p = all_pairs[0]
            print(f"    Pair ID: {p['pair_id']}")
            print(f"    Difficulty: {p['difficulty']} (spread: {p['spread'] * 100:.1f}%)")
            print(f"    Winner: {p['winner']}")
            print(f"    X metrics: {json.dumps({k: round(v, 3) if isinstance(v, float) else v for k, v in list(p['stock_x']['metrics'].items())[:5]}, indent=6)}")
        return

    # Phase 3: Run LLM
    print(f"\nPhase 3: Running {args.model}...")
    t2 = time.time()
    runner = LLMRunner(args.model, args.prompt, output_dir, verbose=args.verbose,
                       thinking_tokens=args.thinking_tokens, effort=args.effort)
    llm_results = runner.run(all_pairs)
    llm_time = time.time() - t2
    print(f"  LLM completed in {llm_time:.0f}s")

    # Phase 4: Run baselines
    print("\nPhase 4: Running baselines...")
    baseline_results = evaluate_all_baselines(all_pairs)

    # Phase 5: Evaluate
    print("\nPhase 5: Evaluating...")
    summary = evaluate_run(all_pairs, llm_results, baseline_results)
    save_summary(summary, output_dir)

    # Save results
    results_path = output_dir / "results.json"
    with open(results_path, "w") as f:
        json.dump({
            "config": config,
            "llm_results_count": len(llm_results),
            "baseline_results": {
                name: {"accuracy": sum(1 for r in results if r["correct"]) / len(results) if results else 0,
                       "n": len(results)}
                for name, results in baseline_results.items()
            },
        }, f, indent=2)

    print_summary(summary)

    total_time = time.time() - t0
    print(f"\n  Total time: {total_time:.0f}s "
          f"(data: {data_time:.0f}s, pairs: {pairs_time:.0f}s, "
          f"llm: {llm_time:.0f}s)")


def _evaluate_existing(run_dir, verbose=False):
    """Re-evaluate an existing run without making new LLM calls."""
    run_dir = Path(run_dir)

    pairs = load_pairs(run_dir / "pairs.json")
    llm_results = load_llm_results(run_dir / "llm_calls.jsonl")

    print(f"  Loaded {len(pairs)} pairs and {len(llm_results)} LLM results")

    baseline_results = evaluate_all_baselines(pairs)
    summary = evaluate_run(pairs, llm_results, baseline_results)
    save_summary(summary, run_dir)
    print_summary(summary)


if __name__ == "__main__":
    main()
