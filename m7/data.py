"""M7 Pairwise Comparison: data pipeline.

Fetches financial data from TradingStudio API, caches to parquet on disk,
loads into DuckDB for fast local querying. Computes derived features
(trailing returns, volatility, revenue growth).
"""

import os
import sys
import time
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.ts_client import TradingStudio
from lib.data_utils import query_parquet


CACHE_MAX_AGE_HOURS = 24


def _cache_path(cache_dir, exchange_key, table_name):
    """Build cache file path for a given table."""
    d = Path(cache_dir) / exchange_key
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{table_name}.parquet"


def _cache_is_fresh(path, max_age_hours=CACHE_MAX_AGE_HOURS):
    """Check if a cached parquet file exists and is fresh enough."""
    if not path.exists():
        return False
    age_hours = (time.time() - path.stat().st_mtime) / 3600
    return age_hours < max_age_hours


def _fetch_and_save_parquet(ts, sql, cache_path, verbose=False, limit=5000000, timeout=600):
    """Fetch query as parquet bytes, save to disk, return bytes."""
    parquet_bytes = ts.query(sql, format="parquet", limit=limit, timeout=timeout,
                             verbose=verbose, memory_mb=16384, threads=6)
    if parquet_bytes:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "wb") as f:
            f.write(parquet_bytes)
    return parquet_bytes


def _load_parquet_to_duckdb(con, table_name, parquet_path):
    """Load a parquet file into a DuckDB table. Returns row count."""
    if not parquet_path.exists():
        con.execute(f"CREATE TABLE {table_name}(dummy INTEGER)")
        con.execute(f"DELETE FROM {table_name}")
        return 0
    con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet('{parquet_path}')")
    return con.execute(f"SELECT count(*) FROM {table_name}").fetchone()[0]


def _load_parquet_bytes_to_duckdb(con, table_name, parquet_bytes):
    """Load parquet bytes into DuckDB via temp file. Returns row count."""
    if not parquet_bytes:
        con.execute(f"CREATE TABLE {table_name}(dummy INTEGER)")
        con.execute(f"DELETE FROM {table_name}")
        return 0
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        f.write(parquet_bytes)
        tmp_path = f.name
    try:
        con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet('{tmp_path}')")
        return con.execute(f"SELECT count(*) FROM {table_name}").fetchone()[0]
    finally:
        os.unlink(tmp_path)


def _fetch_prices_chunked(ts, sym_filter, start_year, end_year, cache_dir, exchange_key,
                          verbose=False):
    """Fetch prices in yearly chunks to avoid API row limits.

    The full US price dataset is ~38M rows (2014-2026), exceeding the 5M row API limit.
    Fetching per-year keeps each chunk under 5M rows.

    Returns: list of parquet file paths (one per year).
    """
    price_dir = Path(cache_dir) / exchange_key / "prices"
    price_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for year in range(start_year - 1, end_year + 2):  # extra year each side
        chunk_path = price_dir / f"prices_{year}.parquet"

        if _cache_is_fresh(chunk_path):
            if verbose:
                print(f"    {year}: cached")
            paths.append(chunk_path)
            continue

        sql = f"""SELECT symbol, date, dateEpoch as trade_epoch, adjClose
                  FROM stock_eod
                  WHERE {sym_filter}
                    AND date >= '{year}-01-01' AND date <= '{year}-12-31'"""

        if verbose:
            print(f"    {year}: fetching...")

        parquet_bytes = ts.query(sql, format="parquet", limit=5000000, timeout=600,
                                 verbose=False, memory_mb=16384, threads=6)
        if parquet_bytes:
            with open(chunk_path, "wb") as f:
                f.write(parquet_bytes)
            paths.append(chunk_path)
            if verbose:
                # Quick row count
                tmp_con = duckdb.connect(":memory:")
                cnt = tmp_con.execute(f"SELECT count(*) FROM read_parquet('{chunk_path}')").fetchone()[0]
                tmp_con.close()
                print(f"    {year}: {cnt:,} rows")
        else:
            if verbose:
                print(f"    {year}: no data")

    return paths


def fetch_and_cache(exchanges, start_year, end_year, api_key=None, cache_dir="data",
                    verbose=False):
    """Fetch all data needed for M7, cache to disk, load into DuckDB.

    Args:
        exchanges: list of exchange codes (e.g. ["NYSE", "NASDAQ", "AMEX"])
        start_year: int
        end_year: int
        api_key: str or None (falls back to TS_API_KEY env var)
        cache_dir: str - directory for parquet cache
        verbose: bool

    Returns:
        duckdb.Connection with tables loaded and derived features computed
    """
    ts = TradingStudio(api_key=api_key)

    ex_filter = ", ".join(f"'{e}'" for e in exchanges)
    exchange_key = "_".join(sorted(exchanges))

    # Symbol filter subquery
    sym_filter = f"symbol IN (SELECT DISTINCT symbol FROM profile WHERE exchange IN ({ex_filter}))"

    con = duckdb.connect(":memory:")
    con.execute("SET memory_limit='4GB'")

    # Define non-price queries (all fit within 5M row limit)
    queries = [
        ("universe", f"SELECT DISTINCT symbol, exchange FROM profile WHERE exchange IN ({ex_filter})",
         "exchange membership"),

        ("key_metrics_raw",
         f"""SELECT symbol, returnOnEquity, returnOnAssets, currentRatio, incomeQuality,
                    evToEBITDA, marketCap, dateEpoch as filing_epoch, period
             FROM key_metrics
             WHERE period = 'FY' AND {sym_filter}""",
         "key metrics"),

        ("financial_ratios_raw",
         f"""SELECT symbol, priceToEarningsRatio, debtToEquityRatio, priceToBookRatio,
                    grossProfitMargin, netProfitMargin, freeCashFlowPerShare, dividendYield,
                    dateEpoch as filing_epoch, period
             FROM financial_ratios
             WHERE period = 'FY' AND {sym_filter}""",
         "financial ratios"),

        ("income_raw",
         f"""SELECT symbol, revenue, dateEpoch as filing_epoch, period
             FROM income_statement
             WHERE period = 'FY' AND {sym_filter}""",
         "income statements"),

        ("scores_raw",
         f"""SELECT symbol, piotroskiScore
             FROM scores
             WHERE {sym_filter}""",
         "Piotroski scores"),
    ]

    for table_name, sql, label in queries:
        cache_file = _cache_path(cache_dir, exchange_key, table_name)

        if _cache_is_fresh(cache_file):
            if verbose:
                print(f"  Loading {label} from cache...")
            count = _load_parquet_to_duckdb(con, table_name, cache_file)
        else:
            print(f"  Fetching {label}...")
            parquet_bytes = _fetch_and_save_parquet(ts, sql, cache_file, verbose=verbose)
            count = _load_parquet_bytes_to_duckdb(con, table_name, parquet_bytes)

        print(f"    -> {count:,} rows")

    # Fetch prices in yearly chunks (too large for single query)
    print(f"  Fetching daily prices ({start_year-1}-{end_year+1})...")
    price_paths = _fetch_prices_chunked(
        ts, sym_filter, start_year, end_year, cache_dir, exchange_key, verbose=verbose
    )

    if price_paths:
        glob_pattern = str(Path(cache_dir) / exchange_key / "prices" / "prices_*.parquet")
        con.execute(f"CREATE TABLE prices_raw AS SELECT * FROM read_parquet('{glob_pattern}')")
        count = con.execute("SELECT count(*) FROM prices_raw").fetchone()[0]
    else:
        con.execute("CREATE TABLE prices_raw(symbol VARCHAR, date VARCHAR, trade_epoch BIGINT, adjClose DOUBLE)")
        count = 0
    print(f"    -> {count:,} rows")

    # Create indexes for performance
    try:
        con.execute("CREATE INDEX idx_prices_sym ON prices_raw(symbol)")
        con.execute("CREATE INDEX idx_prices_epoch ON prices_raw(trade_epoch)")
    except Exception:
        pass

    # Compute derived features
    _compute_derived_features(con, verbose)

    return con


def _compute_derived_features(con, verbose=False):
    """Compute trailing returns, volatility, and revenue growth in DuckDB."""
    if verbose:
        print("  Computing derived features...")

    # Trailing 6mo return and volatility per symbol per date
    # Uses window functions over the prices table
    con.execute("""
        CREATE TABLE price_features AS
        WITH daily_returns AS (
            SELECT symbol, date, trade_epoch, adjClose,
                   (adjClose - LAG(adjClose) OVER (PARTITION BY symbol ORDER BY trade_epoch))
                   / NULLIF(LAG(adjClose) OVER (PARTITION BY symbol ORDER BY trade_epoch), 0)
                   AS daily_return,
                   LAG(adjClose, 126) OVER (PARTITION BY symbol ORDER BY trade_epoch) AS price_126d_ago,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_epoch) AS row_num
            FROM prices_raw
        )
        SELECT symbol, date, trade_epoch, adjClose,
               CASE WHEN price_126d_ago IS NOT NULL AND price_126d_ago > 0
                    THEN (adjClose - price_126d_ago) / price_126d_ago
                    ELSE NULL END AS trailing_6mo_return,
               -- Annualized volatility: stddev of daily returns over 126 days * sqrt(252)
               STDDEV(daily_return) OVER (
                   PARTITION BY symbol ORDER BY trade_epoch
                   ROWS BETWEEN 125 PRECEDING AND CURRENT ROW
               ) * SQRT(252) AS trailing_volatility
        FROM daily_returns
        WHERE row_num > 1
    """)

    # Revenue growth YoY from consecutive FY income statements
    con.execute("""
        CREATE TABLE revenue_growth AS
        WITH ranked AS (
            SELECT symbol, revenue, filing_epoch,
                   LAG(revenue) OVER (PARTITION BY symbol ORDER BY filing_epoch) AS prev_revenue
            FROM income_raw
            WHERE period = 'FY'
        )
        SELECT symbol, filing_epoch,
               CASE WHEN prev_revenue IS NOT NULL AND prev_revenue > 0
                    THEN (revenue - prev_revenue) / prev_revenue
                    ELSE NULL END AS revenue_growth_yoy
        FROM ranked
        WHERE prev_revenue IS NOT NULL
    """)

    if verbose:
        pf_count = con.execute("SELECT count(*) FROM price_features").fetchone()[0]
        rg_count = con.execute("SELECT count(*) FROM revenue_growth").fetchone()[0]
        print(f"    -> {pf_count:,} price feature rows, {rg_count:,} revenue growth rows")
