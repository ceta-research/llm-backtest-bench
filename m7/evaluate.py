"""M7 Pairwise Comparison: evaluation metrics.

Accuracy, calibration, long-short portfolio, and statistical tests.
"""

import math
import json
from pathlib import Path


def _wilson_ci(n_correct, n_total, z=1.96):
    """Wilson score 95% confidence interval for a proportion."""
    if n_total == 0:
        return (0.0, 0.0)
    p_hat = n_correct / n_total
    denom = 1 + z ** 2 / n_total
    center = (p_hat + z ** 2 / (2 * n_total)) / denom
    spread = z * math.sqrt(p_hat * (1 - p_hat) / n_total + z ** 2 / (4 * n_total ** 2)) / denom
    return (max(0, center - spread), min(1, center + spread))


def _mcnemar_test(correct_a, correct_b):
    """McNemar's test for paired binary outcomes.

    Args:
        correct_a: list[bool] - correctness of method A
        correct_b: list[bool] - correctness of method B

    Returns:
        chi2 statistic, p_value (approximate)
    """
    # Count discordant pairs
    b_right_a_wrong = sum(1 for a, b in zip(correct_a, correct_b) if not a and b)
    a_right_b_wrong = sum(1 for a, b in zip(correct_a, correct_b) if a and not b)

    n_discordant = b_right_a_wrong + a_right_b_wrong
    if n_discordant == 0:
        return 0.0, 1.0

    # McNemar's chi-squared (with continuity correction)
    chi2 = (abs(b_right_a_wrong - a_right_b_wrong) - 1) ** 2 / n_discordant

    # Approximate p-value using chi-squared distribution with 1 df
    # Using the survival function approximation
    p_value = _chi2_survival(chi2, df=1)

    return chi2, p_value


def _chi2_survival(x, df=1):
    """Approximate chi-squared survival function (p-value).

    Good enough for our purposes. For df=1, uses normal approximation.
    """
    if x <= 0:
        return 1.0
    # For df=1, chi2 = z^2, so P(chi2 > x) = 2 * P(Z > sqrt(x))
    z = math.sqrt(x)
    # Abramowitz and Stegun approximation for normal CDF
    t = 1.0 / (1.0 + 0.2316419 * z)
    d = 0.3989422804014327  # 1/sqrt(2*pi)
    p = d * math.exp(-z * z / 2.0) * (
        t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    )
    return 2 * p  # two-tailed for McNemar's


def evaluate_run(pairs, llm_results, baseline_results):
    """Full evaluation of an M7 run.

    Args:
        pairs: list of pair dicts
        llm_results: list of LLM result dicts (from llm.py)
        baseline_results: dict of {baseline_name: [result_dicts]} (from baselines.py)

    Returns:
        summary dict with accuracy, calibration, long-short, statistical tests
    """
    # Build lookup for LLM results
    llm_by_pair = {r["pair_id"]: r for r in llm_results if r.get("pick")}

    # Overall accuracy
    n_correct = 0
    n_total = 0
    llm_correct_list = []

    for pair in pairs:
        llm_result = llm_by_pair.get(pair["pair_id"])
        if not llm_result:
            continue
        n_total += 1
        correct = llm_result["pick"] == pair["winner"]
        if correct:
            n_correct += 1
        llm_correct_list.append(correct)

    accuracy = n_correct / n_total if n_total > 0 else 0
    ci_low, ci_high = _wilson_ci(n_correct, n_total)

    # Accuracy by difficulty
    accuracy_by_difficulty = {}
    for tier in ["easy", "medium", "hard"]:
        tier_pairs = [p for p in pairs if p["difficulty"] == tier and p["pair_id"] in llm_by_pair]
        if tier_pairs:
            tier_correct = sum(
                1 for p in tier_pairs if llm_by_pair[p["pair_id"]]["pick"] == p["winner"]
            )
            tier_acc = tier_correct / len(tier_pairs)
            tier_ci = _wilson_ci(tier_correct, len(tier_pairs))
            accuracy_by_difficulty[tier] = {
                "accuracy": round(tier_acc, 4),
                "n": len(tier_pairs),
                "ci_95": [round(tier_ci[0], 4), round(tier_ci[1], 4)],
            }

    # Calibration (bucket by confidence)
    calibration = {}
    conf_buckets = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
    for lo, hi in conf_buckets:
        bucket_pairs = [
            (pair, llm_by_pair[pair["pair_id"]])
            for pair in pairs
            if pair["pair_id"] in llm_by_pair
            and llm_by_pair[pair["pair_id"]].get("confidence") is not None
            and lo <= llm_by_pair[pair["pair_id"]]["confidence"] < hi
        ]
        if bucket_pairs:
            bucket_correct = sum(1 for p, r in bucket_pairs if r["pick"] == p["winner"])
            bucket_acc = bucket_correct / len(bucket_pairs)
            label = f"{lo:.1f}-{hi:.1f}"
            calibration[label] = {
                "accuracy": round(bucket_acc, 4),
                "n": len(bucket_pairs),
                "mean_confidence": round(
                    sum(r["confidence"] for _, r in bucket_pairs) / len(bucket_pairs), 4
                ),
            }

    # ECE (Expected Calibration Error)
    ece = 0.0
    n_calibrated = 0
    for bucket_data in calibration.values():
        weight = bucket_data["n"]
        ece += weight * abs(bucket_data["accuracy"] - bucket_data["mean_confidence"])
        n_calibrated += weight
    ece = ece / n_calibrated if n_calibrated > 0 else None

    # Long-short portfolio returns
    # Group by rebalance date, compute avg return of LLM picks vs rejects
    by_date = {}
    for pair in pairs:
        if pair["pair_id"] not in llm_by_pair:
            continue
        d = pair["rebalance_date"]
        if d not in by_date:
            by_date[d] = {"pick_returns": [], "reject_returns": []}
        llm_pick = llm_by_pair[pair["pair_id"]]["pick"]
        if llm_pick == "X":
            by_date[d]["pick_returns"].append(pair["forward_return_x"])
            by_date[d]["reject_returns"].append(pair["forward_return_y"])
        else:
            by_date[d]["pick_returns"].append(pair["forward_return_y"])
            by_date[d]["reject_returns"].append(pair["forward_return_x"])

    long_short_returns = []
    for d in sorted(by_date.keys()):
        picks = by_date[d]["pick_returns"]
        rejects = by_date[d]["reject_returns"]
        if picks and rejects:
            avg_pick = sum(picks) / len(picks)
            avg_reject = sum(rejects) / len(rejects)
            long_short_returns.append({
                "date": d,
                "long_return": round(avg_pick, 6),
                "short_return": round(avg_reject, 6),
                "long_short_spread": round(avg_pick - avg_reject, 6),
                "n_pairs": len(picks),
            })

    # Aggregate long-short metrics
    ls_spreads = [r["long_short_spread"] for r in long_short_returns]
    ls_summary = None
    if ls_spreads:
        mean_spread = sum(ls_spreads) / len(ls_spreads)
        ls_summary = {
            "mean_spread": round(mean_spread, 6),
            "total_periods": len(ls_spreads),
            "positive_periods": sum(1 for s in ls_spreads if s > 0),
        }

    # Baseline accuracy comparison
    baseline_accuracy = {}
    for name, b_results in baseline_results.items():
        b_correct = sum(1 for r in b_results if r["correct"])
        b_total = len(b_results)
        b_acc = b_correct / b_total if b_total > 0 else 0
        b_ci = _wilson_ci(b_correct, b_total)
        baseline_accuracy[name] = {
            "accuracy": round(b_acc, 4),
            "n": b_total,
            "ci_95": [round(b_ci[0], 4), round(b_ci[1], 4)],
        }

    # Statistical tests: McNemar's test (LLM vs each baseline)
    statistical_tests = {}
    for name, b_results in baseline_results.items():
        # Align by pair_id
        b_by_pair = {r["pair_id"]: r["correct"] for r in b_results}
        llm_correct_aligned = []
        baseline_correct_aligned = []
        for pair in pairs:
            pid = pair["pair_id"]
            if pid in llm_by_pair and pid in b_by_pair:
                llm_correct_aligned.append(llm_by_pair[pid]["pick"] == pair["winner"])
                baseline_correct_aligned.append(b_by_pair[pid])

        if llm_correct_aligned:
            chi2, p_value = _mcnemar_test(llm_correct_aligned, baseline_correct_aligned)
            statistical_tests[name] = {
                "chi2": round(chi2, 4),
                "p_value": round(p_value, 6),
                "significant": p_value < 0.05,
                "n_pairs": len(llm_correct_aligned),
            }

    # Cost summary
    total_cost = sum(r.get("cost_usd", 0) for r in llm_results)
    total_tokens_in = sum(r.get("tokens_in", 0) for r in llm_results)
    total_tokens_out = sum(r.get("tokens_out", 0) for r in llm_results)
    avg_latency = (
        sum(r.get("latency_ms", 0) for r in llm_results) / len(llm_results)
        if llm_results else 0
    )
    parse_errors = sum(1 for r in llm_results if r.get("parse_error"))

    summary = {
        "model": llm_results[0]["model"] if llm_results else None,
        "prompt_variant": llm_results[0]["prompt_variant"] if llm_results else None,
        "n_pairs": n_total,
        "accuracy": {
            "overall": round(accuracy, 4),
            "ci_95": [round(ci_low, 4), round(ci_high, 4)],
            "by_difficulty": accuracy_by_difficulty,
        },
        "calibration": {
            "buckets": calibration,
            "ece": round(ece, 4) if ece is not None else None,
        },
        "long_short": {
            "summary": ls_summary,
            "periods": long_short_returns,
        },
        "baselines": baseline_accuracy,
        "statistical_tests": statistical_tests,
        "cost": {
            "total_usd": round(total_cost, 4),
            "tokens_in": total_tokens_in,
            "tokens_out": total_tokens_out,
            "avg_latency_ms": round(avg_latency, 1),
            "parse_errors": parse_errors,
        },
    }

    return summary


def save_summary(summary, output_dir):
    """Save evaluation summary to JSON."""
    path = Path(output_dir) / "summary.json"
    with open(path, "w") as f:
        json.dump(summary, f, indent=2)
    return path


def print_summary(summary):
    """Print a formatted summary to console."""
    print("\n" + "=" * 65)
    print(f"  M7 PAIRWISE COMPARISON RESULTS")
    print(f"  Model: {summary['model']} | Prompt: {summary['prompt_variant']}")
    print("=" * 65)

    acc = summary["accuracy"]
    print(f"\n  Overall Accuracy: {acc['overall'] * 100:.1f}% "
          f"({acc['ci_95'][0] * 100:.1f}% - {acc['ci_95'][1] * 100:.1f}% CI)")
    print(f"  Pairs evaluated: {summary['n_pairs']}")

    if acc["by_difficulty"]:
        print(f"\n  {'Difficulty':<12} {'Accuracy':>10} {'N':>6} {'95% CI':>20}")
        print("  " + "-" * 50)
        for tier in ["easy", "medium", "hard"]:
            if tier in acc["by_difficulty"]:
                d = acc["by_difficulty"][tier]
                print(f"  {tier:<12} {d['accuracy'] * 100:>9.1f}% {d['n']:>6} "
                      f"[{d['ci_95'][0] * 100:.1f}% - {d['ci_95'][1] * 100:.1f}%]")

    # Baselines comparison
    print(f"\n  {'Baseline':<20} {'Accuracy':>10} {'vs LLM':>10}")
    print("  " + "-" * 42)
    llm_acc = acc["overall"]
    for name, b in sorted(summary["baselines"].items()):
        diff = llm_acc - b["accuracy"]
        print(f"  {name:<20} {b['accuracy'] * 100:>9.1f}% {diff * 100:>+9.1f}%")

    # Statistical significance
    if summary["statistical_tests"]:
        print(f"\n  McNemar's Test (LLM vs baseline):")
        for name, test in sorted(summary["statistical_tests"].items()):
            sig = "*" if test["significant"] else ""
            print(f"    {name:<18} p={test['p_value']:.4f} {sig}")

    # Calibration
    cal = summary["calibration"]
    if cal["buckets"]:
        print(f"\n  Calibration (ECE = {cal['ece']:.4f}):" if cal["ece"] else "\n  Calibration:")
        print(f"  {'Confidence':>12} {'Accuracy':>10} {'N':>6}")
        print("  " + "-" * 30)
        for bucket, data in sorted(cal["buckets"].items()):
            print(f"  {bucket:>12} {data['accuracy'] * 100:>9.1f}% {data['n']:>6}")

    # Long-short
    ls = summary["long_short"]
    if ls["summary"]:
        s = ls["summary"]
        print(f"\n  Long-Short Portfolio:")
        print(f"    Mean spread per period: {s['mean_spread'] * 100:+.2f}%")
        print(f"    Positive periods: {s['positive_periods']}/{s['total_periods']}")

    # Cost
    c = summary["cost"]
    print(f"\n  Cost: ${c['total_usd']:.4f} | "
          f"Tokens: {c['tokens_in']:,} in / {c['tokens_out']:,} out | "
          f"Avg latency: {c['avg_latency_ms']:.0f}ms")
    if c["parse_errors"]:
        print(f"  Parse errors: {c['parse_errors']}")

    print("=" * 65)
