"""M7 Pairwise Comparison: heuristic baseline evaluators.

Each baseline takes a pair dict and returns {"pick": "X"|"Y", "rule": str}.
"""

import hashlib
import random


def baseline_lower_pe(pair):
    """Pick the stock with lower P/E ratio (classic value)."""
    pe_x = pair["stock_x"]["metrics"].get("P/E")
    pe_y = pair["stock_y"]["metrics"].get("P/E")
    if pe_x is None or pe_y is None:
        return {"pick": "X", "rule": "lower_pe (missing data, default X)"}
    pick = "X" if pe_x < pe_y else "Y"
    return {"pick": pick, "rule": "lower_pe"}


def baseline_higher_roe(pair):
    """Pick the stock with higher ROE (quality)."""
    roe_x = pair["stock_x"]["metrics"].get("ROE")
    roe_y = pair["stock_y"]["metrics"].get("ROE")
    if roe_x is None or roe_y is None:
        return {"pick": "X", "rule": "higher_roe (missing data, default X)"}
    pick = "X" if roe_x > roe_y else "Y"
    return {"pick": pick, "rule": "higher_roe"}


def baseline_higher_piotroski(pair):
    """Pick the stock with higher Piotroski F-Score (financial health)."""
    pio_x = pair["stock_x"]["metrics"].get("Piotroski F-Score")
    pio_y = pair["stock_y"]["metrics"].get("Piotroski F-Score")
    if pio_x is None or pio_y is None:
        return {"pick": "X", "rule": "higher_piotroski (missing data, default X)"}
    pick = "X" if pio_x > pio_y else "Y"
    return {"pick": pick, "rule": "higher_piotroski"}


def baseline_lower_pb(pair):
    """Pick the stock with lower P/B ratio (deep value)."""
    pb_x = pair["stock_x"]["metrics"].get("P/B")
    pb_y = pair["stock_y"]["metrics"].get("P/B")
    if pb_x is None or pb_y is None:
        return {"pick": "X", "rule": "lower_pb (missing data, default X)"}
    pick = "X" if pb_x < pb_y else "Y"
    return {"pick": pick, "rule": "lower_pb"}


def baseline_momentum(pair):
    """Pick the stock with higher trailing 6-month return (momentum)."""
    mom_x = pair["stock_x"]["metrics"].get("Trailing 6mo Return")
    mom_y = pair["stock_y"]["metrics"].get("Trailing 6mo Return")
    if mom_x is None or mom_y is None:
        return {"pick": "X", "rule": "momentum (missing data, default X)"}
    pick = "X" if mom_x > mom_y else "Y"
    return {"pick": pick, "rule": "momentum"}


def _normalize(value, all_values):
    """Min-max normalize a value within a list."""
    mn = min(all_values)
    mx = max(all_values)
    if mx == mn:
        return 0.5
    return (value - mn) / (mx - mn)


def baseline_composite(pair):
    """Multi-factor composite: value + quality + momentum, pick higher score.

    Factors (normalized 0-1, higher = better):
    - Value: inverse of P/E (lower P/E = higher score)
    - Quality: ROE (higher = better)
    - Momentum: trailing 6mo return (higher = better)
    """
    metrics_x = pair["stock_x"]["metrics"]
    metrics_y = pair["stock_y"]["metrics"]

    score_x = 0.0
    score_y = 0.0
    n_factors = 0

    # Value: lower P/E = better
    pe_x = metrics_x.get("P/E")
    pe_y = metrics_y.get("P/E")
    if pe_x is not None and pe_y is not None and pe_x > 0 and pe_y > 0:
        inv_pe = [1.0 / pe_x, 1.0 / pe_y]
        score_x += _normalize(inv_pe[0], inv_pe)
        score_y += _normalize(inv_pe[1], inv_pe)
        n_factors += 1

    # Quality: higher ROE = better
    roe_x = metrics_x.get("ROE")
    roe_y = metrics_y.get("ROE")
    if roe_x is not None and roe_y is not None:
        score_x += _normalize(roe_x, [roe_x, roe_y])
        score_y += _normalize(roe_y, [roe_x, roe_y])
        n_factors += 1

    # Momentum: higher trailing return = better
    mom_x = metrics_x.get("Trailing 6mo Return")
    mom_y = metrics_y.get("Trailing 6mo Return")
    if mom_x is not None and mom_y is not None:
        score_x += _normalize(mom_x, [mom_x, mom_y])
        score_y += _normalize(mom_y, [mom_x, mom_y])
        n_factors += 1

    # Financial health: higher Piotroski = better
    pio_x = metrics_x.get("Piotroski F-Score")
    pio_y = metrics_y.get("Piotroski F-Score")
    if pio_x is not None and pio_y is not None:
        score_x += _normalize(pio_x, [pio_x, pio_y])
        score_y += _normalize(pio_y, [pio_x, pio_y])
        n_factors += 1

    if n_factors == 0:
        return {"pick": "X", "rule": "composite (no data, default X)"}

    pick = "X" if score_x >= score_y else "Y"
    return {"pick": pick, "rule": "composite"}


def baseline_random(pair, seed=None):
    """Random pick (seeded for reproducibility)."""
    if seed is None:
        seed = int(hashlib.sha256(pair["pair_id"].encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    pick = rng.choice(["X", "Y"])
    return {"pick": pick, "rule": "random"}


def _safe_get(metrics, key, default=None):
    """Get metric value, treating None and 0 appropriately."""
    v = metrics.get(key)
    return v if v is not None else default


def _score_stock(metrics, weights):
    """Score a stock using weighted factors. Higher = better.

    Each weight is (metric_key, weight, invert).
    If invert=True, lower metric values produce higher scores.
    Returns normalized score.
    """
    score = 0.0
    n = 0
    for key, w, invert in weights:
        v = _safe_get(metrics, key)
        if v is None:
            continue
        val = -v if invert else v
        score += w * val
        n += 1
    return score if n > 0 else None


def baseline_greenblatt(pair):
    """Greenblatt Magic Formula: earnings yield + ROE.

    Rank by 1/PE (earnings yield) + ROE. Classic quality-at-a-price.
    """
    mx, my = pair["stock_x"]["metrics"], pair["stock_y"]["metrics"]
    pe_x, pe_y = _safe_get(mx, "P/E"), _safe_get(my, "P/E")
    roe_x, roe_y = _safe_get(mx, "ROE"), _safe_get(my, "ROE")

    sx = (1.0 / pe_x if pe_x and pe_x > 0 else 0) + (roe_x or 0)
    sy = (1.0 / pe_y if pe_y and pe_y > 0 else 0) + (roe_y or 0)

    pick = "X" if sx >= sy else "Y"
    return {"pick": pick, "rule": "greenblatt"}


def baseline_garp(pair):
    """Growth at Reasonable Price: revenue growth / PE.

    Higher growth relative to valuation wins. Classic Peter Lynch metric.
    """
    mx, my = pair["stock_x"]["metrics"], pair["stock_y"]["metrics"]
    growth_x = _safe_get(mx, "Revenue Growth (YoY)")
    growth_y = _safe_get(my, "Revenue Growth (YoY)")
    pe_x = _safe_get(mx, "P/E")
    pe_y = _safe_get(my, "P/E")

    sx = (growth_x / pe_x) if growth_x is not None and pe_x and pe_x > 0 else 0
    sy = (growth_y / pe_y) if growth_y is not None and pe_y and pe_y > 0 else 0

    pick = "X" if sx >= sy else "Y"
    return {"pick": pick, "rule": "garp"}


def baseline_quality(pair):
    """Quality factor: ROE + margins + Piotroski + low leverage.

    Picks the fundamentally stronger company regardless of price.
    """
    weights = [
        ("ROE", 2.0, False),
        ("ROA", 1.0, False),
        ("Net Margin", 1.5, False),
        ("Gross Margin", 1.0, False),
        ("Piotroski F-Score", 2.0, False),
        ("D/E", 1.0, True),            # lower debt = better
        ("Current Ratio", 0.5, False),
    ]
    sx = _score_stock(pair["stock_x"]["metrics"], weights)
    sy = _score_stock(pair["stock_y"]["metrics"], weights)

    if sx is None or sy is None:
        return {"pick": "X", "rule": "quality (missing data)"}
    pick = "X" if sx >= sy else "Y"
    return {"pick": pick, "rule": "quality"}


def baseline_value(pair):
    """Deep value: low P/E + low P/B + low EV/EBITDA + high dividend yield."""
    weights = [
        ("P/E", 2.0, True),            # lower = cheaper
        ("P/B", 1.5, True),
        ("EV/EBITDA", 1.5, True),
        ("Dividend Yield", 1.0, False), # higher = better
        ("FCF/Share", 1.0, False),
    ]
    sx = _score_stock(pair["stock_x"]["metrics"], weights)
    sy = _score_stock(pair["stock_y"]["metrics"], weights)

    if sx is None or sy is None:
        return {"pick": "X", "rule": "value (missing data)"}
    pick = "X" if sx >= sy else "Y"
    return {"pick": pick, "rule": "value"}


def baseline_mean_reversion(pair):
    """Contrarian: pick the stock that has underperformed (lower trailing return).

    Bets on mean reversion rather than momentum continuation.
    """
    mom_x = _safe_get(pair["stock_x"]["metrics"], "Trailing 6mo Return")
    mom_y = _safe_get(pair["stock_y"]["metrics"], "Trailing 6mo Return")
    if mom_x is None or mom_y is None:
        return {"pick": "X", "rule": "mean_reversion (missing data)"}
    pick = "X" if mom_x < mom_y else "Y"  # pick the loser
    return {"pick": pick, "rule": "mean_reversion"}


def baseline_low_vol(pair):
    """Low volatility: pick the less volatile stock.

    Low-vol anomaly — less volatile stocks tend to outperform risk-adjusted.
    """
    vol_x = _safe_get(pair["stock_x"]["metrics"], "Trailing Volatility")
    vol_y = _safe_get(pair["stock_y"]["metrics"], "Trailing Volatility")
    if vol_x is None or vol_y is None:
        return {"pick": "X", "rule": "low_vol (missing data)"}
    pick = "X" if vol_x < vol_y else "Y"
    return {"pick": pick, "rule": "low_vol"}


def baseline_kitchen_sink(pair):
    """All-factor weighted model using all 15 metrics.

    Weights derived from established factor literature:
    - Value: 25% (P/E, P/B, EV/EBITDA)
    - Quality: 30% (ROE, ROA, margins, Piotroski)
    - Momentum: 15% (trailing return)
    - Growth: 15% (revenue growth)
    - Safety: 15% (low vol, low leverage, current ratio)
    """
    weights = [
        # Value (lower = cheaper, so invert)
        ("P/E", 2.0, True),
        ("P/B", 1.5, True),
        ("EV/EBITDA", 1.5, True),
        # Quality (higher = better)
        ("ROE", 2.5, False),
        ("ROA", 1.5, False),
        ("Net Margin", 1.5, False),
        ("Gross Margin", 1.0, False),
        ("Piotroski F-Score", 2.0, False),
        # Momentum
        ("Trailing 6mo Return", 2.0, False),
        # Growth
        ("Revenue Growth (YoY)", 2.0, False),
        # Safety
        ("Trailing Volatility", 1.5, True),   # lower vol = better
        ("D/E", 1.0, True),                   # lower debt = better
        ("Current Ratio", 0.5, False),
        # Income
        ("Dividend Yield", 0.5, False),
        ("FCF/Share", 1.0, False),
    ]
    sx = _score_stock(pair["stock_x"]["metrics"], weights)
    sy = _score_stock(pair["stock_y"]["metrics"], weights)

    if sx is None or sy is None:
        return {"pick": "X", "rule": "kitchen_sink (missing data)"}
    pick = "X" if sx >= sy else "Y"
    return {"pick": pick, "rule": "kitchen_sink"}


ALL_BASELINES = {
    "random": baseline_random,
    "lower_pe": baseline_lower_pe,
    "higher_roe": baseline_higher_roe,
    "higher_piotroski": baseline_higher_piotroski,
    "lower_pb": baseline_lower_pb,
    "momentum": baseline_momentum,
    "mean_reversion": baseline_mean_reversion,
    "low_vol": baseline_low_vol,
    "composite": baseline_composite,
    "greenblatt": baseline_greenblatt,
    "garp": baseline_garp,
    "quality": baseline_quality,
    "value": baseline_value,
    "kitchen_sink": baseline_kitchen_sink,
}


def evaluate_all_baselines(pairs):
    """Run all 7 baselines on all pairs.

    Returns:
        dict of {baseline_name: [{"pair_id": ..., "pick": ..., "correct": bool}, ...]}
    """
    results = {}
    for name, fn in ALL_BASELINES.items():
        baseline_results = []
        for pair in pairs:
            result = fn(pair)
            correct = result["pick"] == pair["winner"]
            baseline_results.append({
                "pair_id": pair["pair_id"],
                "pick": result["pick"],
                "correct": correct,
                "rule": result["rule"],
            })
        results[name] = baseline_results
    return results
