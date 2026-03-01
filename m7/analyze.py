"""M7 Pairwise Comparison: cross-run comparison and report generation."""

import json
from pathlib import Path


def compare_runs(run_dirs):
    """Load summaries from multiple runs and print comparison table.

    Args:
        run_dirs: list of path strings to run output directories
    """
    runs = []
    for d in run_dirs:
        summary_path = Path(d) / "summary.json"
        config_path = Path(d) / "config.json"
        if not summary_path.exists():
            print(f"  Skipping {d}: no summary.json")
            continue

        with open(summary_path) as f:
            summary = json.load(f)
        config = {}
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)

        runs.append({
            "dir": d,
            "config": config,
            "summary": summary,
        })

    if not runs:
        print("No valid runs found.")
        return

    # Print comparison table
    print("\n" + "=" * 90)
    print("  M7 CROSS-RUN COMPARISON")
    print("=" * 90)

    header = f"  {'Model':<18} {'Prompt':<14} {'Exchange':<10} {'Accuracy':>10} {'95% CI':>18} {'Cost':>10} {'N':>6}"
    print(header)
    print("  " + "-" * 86)

    for run in runs:
        s = run["summary"]
        c = run["config"]
        acc = s["accuracy"]["overall"]
        ci = s["accuracy"]["ci_95"]
        cost = s["cost"]["total_usd"]
        n = s["n_pairs"]
        model = c.get("model", s.get("model", "?"))
        prompt = c.get("prompt_variant", s.get("prompt_variant", "?"))
        exchange = c.get("exchange", "?")
        think = c.get("thinking_tokens", 0)
        effort = c.get("effort", None)
        if think:
            model = f"{model}+think{think}"
        if effort:
            model = f"{model}({effort})"

        print(f"  {model:<18} {prompt:<14} {exchange:<10} "
              f"{acc * 100:>9.1f}% [{ci[0] * 100:.1f}-{ci[1] * 100:.1f}%] "
              f"${cost:>8.4f} {n:>6}")

    # Baseline comparison (from first run)
    if runs:
        s = runs[0]["summary"]
        print(f"\n  Baselines (from first run):")
        print(f"  {'Baseline':<20} {'Accuracy':>10}")
        print("  " + "-" * 32)
        for name, b in sorted(s["baselines"].items()):
            print(f"  {name:<20} {b['accuracy'] * 100:>9.1f}%")

    print("=" * 90)


def generate_report(run_dir):
    """Generate a markdown report for a single run.

    Args:
        run_dir: path to run output directory

    Returns:
        str - markdown report
    """
    run_dir = Path(run_dir)
    summary_path = run_dir / "summary.json"
    config_path = run_dir / "config.json"

    with open(summary_path) as f:
        summary = json.load(f)

    config = {}
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)

    lines = []
    lines.append("# M7 Pairwise Comparison Results\n")

    # Config
    lines.append("## Configuration\n")
    lines.append(f"- **Model**: {config.get('model', summary.get('model', '?'))}")
    lines.append(f"- **Prompt**: {config.get('prompt_variant', summary.get('prompt_variant', '?'))}")
    lines.append(f"- **Exchange**: {config.get('exchange', '?')} ({', '.join(config.get('exchanges', []))})")
    lines.append(f"- **Period**: {config.get('start_year', '?')}-{config.get('end_year', '?')}")
    lines.append(f"- **Pairs**: {summary['n_pairs']}")
    lines.append("")

    # Accuracy
    acc = summary["accuracy"]
    lines.append("## Accuracy\n")
    lines.append(f"**Overall: {acc['overall'] * 100:.1f}%** "
                 f"(95% CI: {acc['ci_95'][0] * 100:.1f}%-{acc['ci_95'][1] * 100:.1f}%)\n")

    if acc["by_difficulty"]:
        lines.append("| Difficulty | Accuracy | N | 95% CI |")
        lines.append("|---|---|---|---|")
        for tier in ["easy", "medium", "hard"]:
            if tier in acc["by_difficulty"]:
                d = acc["by_difficulty"][tier]
                lines.append(f"| {tier} | {d['accuracy'] * 100:.1f}% | {d['n']} | "
                             f"{d['ci_95'][0] * 100:.1f}%-{d['ci_95'][1] * 100:.1f}% |")
        lines.append("")

    # Baselines
    lines.append("## Baselines\n")
    lines.append("| Method | Accuracy | vs LLM |")
    lines.append("|---|---|---|")
    lines.append(f"| **LLM ({summary.get('model', '?')})** | **{acc['overall'] * 100:.1f}%** | - |")
    for name, b in sorted(summary["baselines"].items()):
        diff = acc["overall"] - b["accuracy"]
        lines.append(f"| {name} | {b['accuracy'] * 100:.1f}% | {diff * 100:+.1f}% |")
    lines.append("")

    # Calibration
    cal = summary["calibration"]
    if cal["buckets"]:
        lines.append("## Calibration\n")
        if cal["ece"] is not None:
            lines.append(f"Expected Calibration Error: **{cal['ece']:.4f}**\n")
        lines.append("| Confidence | Accuracy | N |")
        lines.append("|---|---|---|")
        for bucket, data in sorted(cal["buckets"].items()):
            lines.append(f"| {bucket} | {data['accuracy'] * 100:.1f}% | {data['n']} |")
        lines.append("")

    # Long-short
    ls = summary["long_short"]
    if ls["summary"]:
        s = ls["summary"]
        lines.append("## Long-Short Portfolio\n")
        lines.append(f"- Mean spread per period: **{s['mean_spread'] * 100:+.2f}%**")
        lines.append(f"- Positive periods: {s['positive_periods']}/{s['total_periods']}")
        lines.append("")

    # Cost
    c = summary["cost"]
    lines.append("## Cost\n")
    lines.append(f"- Total: **${c['total_usd']:.4f}**")
    lines.append(f"- Tokens: {c['tokens_in']:,} in / {c['tokens_out']:,} out")
    lines.append(f"- Avg latency: {c['avg_latency_ms']:.0f}ms")
    if c["parse_errors"]:
        lines.append(f"- Parse errors: {c['parse_errors']}")
    lines.append("")

    report = "\n".join(lines)

    # Save report
    report_path = run_dir / "report.md"
    with open(report_path, "w") as f:
        f.write(report)

    return report


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 -m m7.analyze <run_dir1> [run_dir2] ...")
        sys.exit(1)

    if len(sys.argv) == 2:
        report = generate_report(sys.argv[1])
        print(report)
    else:
        compare_runs(sys.argv[1:])
