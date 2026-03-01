"""M7 Pairwise Comparison: pair generation, seeding, difficulty stratification."""

import hashlib
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from .config import (
    MARKET_CAP_MIN, FORWARD_TRADING_DAYS, TRAILING_TRADING_DAYS,
    PAIRS_PER_REBALANCE, DIFFICULTY_TIERS, DIFFICULTY_RATIOS,
    FUNDAMENTAL_METRICS, PROMPT_METRICS,
)


def _make_seed(exchange_key, date_str, run_id="default"):
    """Deterministic seed from exchange + date + run_id."""
    raw = f"{exchange_key}:{date_str}:{run_id}"
    return int(hashlib.sha256(raw.encode()).hexdigest()[:8], 16)


def _get_eligible_stocks(con, rebalance_date, forward_days=FORWARD_TRADING_DAYS):
    """Query DuckDB for stocks eligible for pairing at a given rebalance date.

    Eligibility:
    - marketCap > MARKET_CAP_MIN (most recent FY filing before rebalance_date)
    - All prompt metrics non-null
    - Price exists at rebalance_date AND at rebalance_date + forward period

    Returns list of dicts with symbol, metrics, and forward return.
    """
    rebalance_epoch = int(datetime.combine(rebalance_date, datetime.min.time()).timestamp())
    # Forward date: rebalance_date + ~6 months calendar
    forward_date = rebalance_date + timedelta(days=180)

    # Window for finding prices near the target dates (10 trading days)
    entry_window_end = rebalance_date + timedelta(days=14)
    exit_window_end = forward_date + timedelta(days=14)

    rows = con.execute("""
        WITH latest_metrics AS (
            SELECT symbol, returnOnEquity, returnOnAssets, currentRatio,
                   incomeQuality, evToEBITDA, marketCap, filing_epoch,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY filing_epoch DESC) AS rn
            FROM key_metrics_raw
            WHERE filing_epoch <= ?
        ),
        latest_ratios AS (
            SELECT symbol, priceToEarningsRatio, debtToEquityRatio, priceToBookRatio,
                   grossProfitMargin, netProfitMargin, freeCashFlowPerShare, dividendYield,
                   filing_epoch,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY filing_epoch DESC) AS rn
            FROM financial_ratios_raw
            WHERE filing_epoch <= ?
        ),
        latest_scores AS (
            SELECT symbol, piotroskiScore,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY symbol) AS rn
            FROM scores_raw
        ),
        latest_revenue_growth AS (
            SELECT symbol, revenue_growth_yoy,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY filing_epoch DESC) AS rn
            FROM revenue_growth
            WHERE filing_epoch <= ?
        ),
        entry_prices AS (
            SELECT symbol, adjClose AS entry_price, trade_epoch,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_epoch ASC) AS rn
            FROM price_features
            WHERE date >= ? AND date <= ?
        ),
        exit_prices AS (
            SELECT symbol, adjClose AS exit_price, trade_epoch,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_epoch ASC) AS rn
            FROM price_features
            WHERE date >= ? AND date <= ?
        ),
        trailing_data AS (
            SELECT symbol, trailing_6mo_return, trailing_volatility,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_epoch DESC) AS rn
            FROM price_features
            WHERE date <= ? AND trailing_6mo_return IS NOT NULL
        )
        SELECT
            m.symbol,
            m.returnOnEquity, m.returnOnAssets, m.currentRatio,
            m.incomeQuality, m.evToEBITDA, m.marketCap,
            r.priceToEarningsRatio, r.debtToEquityRatio, r.priceToBookRatio,
            r.grossProfitMargin, r.netProfitMargin, r.freeCashFlowPerShare,
            r.dividendYield,
            s.piotroskiScore,
            rg.revenue_growth_yoy,
            ep.entry_price,
            xp.exit_price,
            t.trailing_6mo_return,
            t.trailing_volatility
        FROM latest_metrics m
        JOIN latest_ratios r ON m.symbol = r.symbol AND r.rn = 1
        LEFT JOIN latest_scores s ON m.symbol = s.symbol AND s.rn = 1
        LEFT JOIN latest_revenue_growth rg ON m.symbol = rg.symbol AND rg.rn = 1
        JOIN entry_prices ep ON m.symbol = ep.symbol AND ep.rn = 1
        JOIN exit_prices xp ON m.symbol = xp.symbol AND xp.rn = 1
        LEFT JOIN trailing_data t ON m.symbol = t.symbol AND t.rn = 1
        WHERE m.rn = 1
          AND m.marketCap > ?
          AND ep.entry_price > 0
          AND xp.exit_price > 0
          AND m.returnOnEquity IS NOT NULL
          AND r.priceToEarningsRatio IS NOT NULL
    """, [
        rebalance_epoch,                          # latest_metrics
        rebalance_epoch,                          # latest_ratios
        rebalance_epoch,                          # latest_revenue_growth
        rebalance_date.isoformat(),               # entry_prices start
        entry_window_end.isoformat(),             # entry_prices end
        forward_date.isoformat(),                 # exit_prices start
        exit_window_end.isoformat(),              # exit_prices end
        rebalance_date.isoformat(),               # trailing cutoff
        MARKET_CAP_MIN,                           # market cap filter
    ]).fetchall()

    columns = [
        "symbol", "returnOnEquity", "returnOnAssets", "currentRatio",
        "incomeQuality", "evToEBITDA", "marketCap",
        "priceToEarningsRatio", "debtToEquityRatio", "priceToBookRatio",
        "grossProfitMargin", "netProfitMargin", "freeCashFlowPerShare",
        "dividendYield", "piotroskiScore", "revenue_growth_yoy",
        "entry_price", "exit_price", "trailing_6mo_return", "trailing_volatility",
    ]

    stocks = []
    for row in rows:
        d = dict(zip(columns, row))
        forward_return = (d["exit_price"] - d["entry_price"]) / d["entry_price"]

        # Build prompt-ready metrics dict
        metrics = {
            "Revenue Growth (YoY)": d["revenue_growth_yoy"],
            "Net Margin": d["netProfitMargin"],
            "Gross Margin": d["grossProfitMargin"],
            "ROE": d["returnOnEquity"],
            "ROA": d["returnOnAssets"],
            "P/E": d["priceToEarningsRatio"],
            "P/B": d["priceToBookRatio"],
            "D/E": d["debtToEquityRatio"],
            "Current Ratio": d["currentRatio"],
            "EV/EBITDA": d["evToEBITDA"],
            "FCF/Share": d["freeCashFlowPerShare"],
            "Dividend Yield": d["dividendYield"],
            "Piotroski F-Score": d["piotroskiScore"],
            "Trailing 6mo Return": d["trailing_6mo_return"],
            "Trailing Volatility": d["trailing_volatility"],
        }

        stocks.append({
            "symbol": d["symbol"],
            "metrics": metrics,
            "forward_return": forward_return,
            "market_cap": d["marketCap"],
        })

    return stocks


def _classify_difficulty(spread):
    """Classify pair difficulty based on absolute return spread."""
    for tier, bounds in DIFFICULTY_TIERS.items():
        if bounds["min_spread"] <= spread < bounds["max_spread"]:
            return tier
    # Edge case: exact zero spread
    return "hard"


def generate_pairs(con, rebalance_date, exchanges, n_pairs=PAIRS_PER_REBALANCE,
                   run_id="default", verbose=False):
    """Generate stratified, anonymized stock pairs for a rebalance date.

    Args:
        con: DuckDB connection with loaded data
        rebalance_date: date object
        exchanges: list of exchange codes (for seed generation)
        n_pairs: target number of pairs
        run_id: string for seed determinism
        verbose: bool

    Returns:
        list of pair dicts with pair_id, stock_x/y metrics, winner, difficulty
    """
    exchange_key = "_".join(sorted(exchanges))
    date_str = rebalance_date.isoformat()
    seed = _make_seed(exchange_key, date_str, run_id)
    rng = random.Random(seed)

    eligible = _get_eligible_stocks(con, rebalance_date)

    if verbose:
        print(f"    {date_str}: {len(eligible)} eligible stocks")

    if len(eligible) < 2:
        if verbose:
            print(f"    {date_str}: Not enough eligible stocks for pairs")
        return []

    # Generate candidate pairs (sample more than needed for stratification)
    n_candidates = min(n_pairs * 4, len(eligible) * (len(eligible) - 1) // 2)
    candidates = []

    # Sample random pairs
    attempted = set()
    while len(candidates) < n_candidates and len(attempted) < n_candidates * 3:
        i, j = rng.sample(range(len(eligible)), 2)
        key = (min(i, j), max(i, j))
        if key in attempted:
            continue
        attempted.add(key)

        a, b = eligible[i], eligible[j]
        spread = abs(a["forward_return"] - b["forward_return"])
        difficulty = _classify_difficulty(spread)

        # Randomly assign X/Y labels
        if rng.random() < 0.5:
            stock_x, stock_y = a, b
        else:
            stock_x, stock_y = b, a

        winner = "X" if stock_x["forward_return"] > stock_y["forward_return"] else "Y"

        candidates.append({
            "stock_x": stock_x,
            "stock_y": stock_y,
            "spread": spread,
            "difficulty": difficulty,
            "winner": winner,
        })

    # Stratify by difficulty
    by_difficulty = {"easy": [], "medium": [], "hard": []}
    for c in candidates:
        by_difficulty[c["difficulty"]].append(c)

    selected = []
    for tier, ratio in DIFFICULTY_RATIOS.items():
        target = int(n_pairs * ratio)
        pool = by_difficulty[tier]
        rng.shuffle(pool)
        selected.extend(pool[:target])

    # Fill remaining from any bucket
    remaining = n_pairs - len(selected)
    if remaining > 0:
        used = set(id(s) for s in selected)
        extras = [c for c in candidates if id(c) not in used]
        rng.shuffle(extras)
        selected.extend(extras[:remaining])

    # Build final pairs
    pairs = []
    for idx, s in enumerate(selected):
        pair = {
            "pair_id": f"{date_str}_{idx:04d}",
            "rebalance_date": date_str,
            "stock_x": {
                "metrics": s["stock_x"]["metrics"],
            },
            "stock_y": {
                "metrics": s["stock_y"]["metrics"],
            },
            "forward_return_x": round(s["stock_x"]["forward_return"], 6),
            "forward_return_y": round(s["stock_y"]["forward_return"], 6),
            "winner": s["winner"],
            "difficulty": s["difficulty"],
            "spread": round(s["spread"], 6),
        }
        pairs.append(pair)

    if verbose:
        diff_counts = {}
        for p in pairs:
            diff_counts[p["difficulty"]] = diff_counts.get(p["difficulty"], 0) + 1
        print(f"    Generated {len(pairs)} pairs: {diff_counts}")

    return pairs


def save_pairs(pairs, output_dir):
    """Save pairs to JSON file."""
    path = Path(output_dir) / "pairs.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(pairs, f, indent=2)
    return path


def load_pairs(path):
    """Load pairs from JSON file."""
    with open(path) as f:
        return json.load(f)
