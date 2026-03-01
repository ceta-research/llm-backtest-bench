"""TradingStudio data provider. Used by default in backtest scripts.

Thin client for TradingStudio's SQL execution API. Backtest scripts
call fetch_data() which uses this client internally. To swap data
sources, replace fetch_data() in each script. See README.md.

Usage:

    from ts_client import TradingStudio

    ts = TradingStudio(api_key="your_api_key")

    # JSON format (default) - for quick exploration, small queries
    results = ts.query("SELECT symbol, piotroskiScore FROM scores WHERE piotroskiScore >= 7")
    for row in results:
        print(row["symbol"], row["piotroskiScore"])

    # Parquet format - for bulk data, backtests, loading into DuckDB/pandas
    # 10-100x smaller payloads, native binary format
    import duckdb
    parquet_bytes = ts.query(
        "SELECT * FROM stock_eod WHERE symbol IN ('AAPL', 'MSFT')",
        format="parquet",
        limit=5000000
    )
    with open("prices.parquet", "wb") as f:
        f.write(parquet_bytes)
    df = duckdb.execute("SELECT * FROM read_parquet('prices.parquet')").df()
"""

import os
import time
import json
import requests

DEFAULT_BASE_URL = "https://api.tradingstudio.finance/api/v1"
DEFAULT_POLL_INTERVAL = 2.0  # seconds
DEFAULT_TIMEOUT = 300  # seconds


class TradingStudioError(Exception):
    """Base exception for TradingStudio API errors."""
    pass


class QueryTimeoutError(TradingStudioError):
    pass


class QueryFailedError(TradingStudioError):
    pass


class TradingStudio:
    """Thin client for TradingStudio's SQL execution API.

    Args:
        api_key: Your API key (from tradingstudio.finance).
                 Falls back to TS_API_KEY environment variable.
        base_url: API base URL. Defaults to production.
    """

    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or os.environ.get("TS_API_KEY")
        if not self.api_key:
            raise TradingStudioError(
                "No API key provided. Pass api_key= or set TS_API_KEY environment variable.\n"
                "Get your key at: https://tradingstudio.finance"
            )
        self.base_url = (base_url or os.environ.get("TS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        })

    def query(self, sql, timeout=DEFAULT_TIMEOUT, limit=100000, format="json",
             verbose=False, memory_mb=None, threads=None):
        """Execute SQL and return results.

        Args:
            sql: SQL query string.
            timeout: Max execution time in seconds.
            limit: Max rows to return.
            format: Output format (json, csv, parquet).
            verbose: Print progress messages.
            memory_mb: Server-side memory allocation in MB (default: server decides).
                       Use 16384 for large backtests, None for simple queries.
            threads: Server-side thread count (default: server decides).
                     Use 6 for large backtests, None for simple queries.

        Returns:
            List of dicts (one per row) for JSON format.
            Raw text for CSV format.
            Raw bytes for parquet format.
        """
        task_id = self._submit(sql, timeout=timeout, limit=limit, format=format,
                               memory_mb=memory_mb, threads=threads)
        if verbose:
            print(f"  Query submitted (task: {task_id[:8]}...)")

        task = self._poll(task_id, timeout=timeout, verbose=verbose)

        if task["status"] == "completed":
            return self._download(task, format=format)
        elif task["status"] in ("failed", "execution_timed_out", "wait_timed_out", "cancelled"):
            error_msg = task.get("error", task["status"])
            raise QueryFailedError(f"Query failed: {error_msg}")
        else:
            raise QueryTimeoutError(f"Query timed out after {timeout}s (status: {task['status']})")

    def _submit(self, sql, timeout=300, limit=100000, format="json",
                memory_mb=None, threads=None):
        """Submit a query and return the task ID."""
        body = {
            "query": sql,
            "options": {
                "timeout": timeout,
                "limit": limit,
                "format": format,
            },
        }
        if memory_mb is not None or threads is not None:
            resources = {}
            if memory_mb is not None:
                resources["memoryMb"] = memory_mb
            if threads is not None:
                resources["threads"] = threads
            body["resources"] = resources
        resp = self.session.post(f"{self.base_url}/data-explorer/execute", json=body)
        if resp.status_code == 429:
            raise TradingStudioError(f"Rate limited. Retry after {resp.headers.get('Retry-After', '60')}s")
        if resp.status_code not in (200, 201, 202):
            raise TradingStudioError(f"Submit failed ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        return data.get("taskId") or resp.headers.get("X-Task-ID")

    def _poll(self, task_id, timeout=300, verbose=False):
        """Poll task status until completion or timeout."""
        deadline = time.time() + timeout + 30  # extra buffer for poll overhead
        while time.time() < deadline:
            resp = self.session.get(f"{self.base_url}/data-explorer/tasks/{task_id}")
            if resp.status_code != 200:
                raise TradingStudioError(f"Poll failed ({resp.status_code}): {resp.text[:500]}")
            task = resp.json()
            status = task.get("status", "unknown")

            if status in ("completed", "failed", "execution_timed_out", "wait_timed_out", "cancelled"):
                return task

            if verbose:
                print(f"  Status: {status}...")
            time.sleep(DEFAULT_POLL_INTERVAL)

        return {"status": "poll_timeout"}

    def _download(self, task, format="json"):
        """Download results from a completed task.

        The server stores results as parquet (native). JSON/CSV are converted
        on demand. The download endpoint may return:
          1. Inline data (the actual content)
          2. A presigned URL response: {"available": true, "url": "..."}
          3. A preparing response: {"available": false, "retryAfter": 5}
        """
        artifact_id = task.get("artifactId")
        data_url = task.get("dataUrl")

        # Build download URL. dataUrl always points to result.json, so for
        # other formats we construct the URL from artifactId directly.
        ext_map = {"json": "result.json", "csv": "result.csv", "parquet": "result.parquet"}
        filename = ext_map.get(format, "result.json")

        if artifact_id:
            url = f"{self.base_url}/data-explorer/artifacts/{artifact_id}/download/{filename}"
        elif data_url:
            if format != "json" and "result.json" in data_url:
                data_url = data_url.replace("result.json", filename)
            if data_url.startswith("http"):
                url = data_url
            elif data_url.startswith("/"):
                origin = self.base_url.split("/api/")[0]
                url = f"{origin}/api{data_url}"
            else:
                url = f"{self.base_url}/{data_url}"
        else:
            raise TradingStudioError("No artifact ID or data URL in completed task")

        resp = self._fetch_with_retry(url, format)
        return self._parse_response(resp, format)

    def _fetch_with_retry(self, url, format, max_retries=20, initial_wait=2):
        """Fetch URL, following presigned URLs and retrying if file is preparing.

        Args:
            max_retries: Max retry attempts (default 20 = ~2 min for large files)
            initial_wait: Initial retry wait time in seconds (grows with backoff)
        """
        wait_time = initial_wait
        for attempt in range(max_retries):
            resp = self.session.get(url)

            if resp.status_code != 200:
                raise TradingStudioError(f"Download failed ({resp.status_code}): {resp.text[:500]}")

            # Check if this is a presigned URL / preparing response.
            # Inline data for parquet is binary (not JSON), so only check
            # for JSON responses that look like metadata.
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type or (format != "parquet" and not content_type):
                try:
                    body = resp.json()
                    if isinstance(body, dict):
                        if body.get("available") and body.get("url"):
                            # Presigned URL - fetch the actual file
                            presigned_resp = requests.get(body["url"], timeout=300)
                            if presigned_resp.status_code != 200:
                                raise TradingStudioError(
                                    f"Presigned URL fetch failed ({presigned_resp.status_code})"
                                )
                            return presigned_resp
                        if body.get("available") is False:
                            # File is being prepared (JSON/CSV conversion from parquet)
                            # Use server's suggested retry time, or exponential backoff
                            wait = body.get("retryAfter", wait_time)
                            time.sleep(wait)
                            # Exponential backoff, capped at 10s
                            wait_time = min(wait_time * 1.5, 10)
                            continue
                except (json.JSONDecodeError, ValueError):
                    pass

            # Got inline data (parquet binary or JSON array)
            return resp

        raise TradingStudioError(f"File still preparing after {max_retries} retries (~{max_retries * initial_wait}s)")

    def _parse_response(self, resp, format):
        """Parse the final response based on requested format."""
        if format == "json":
            return resp.json()
        elif format == "csv":
            return resp.text
        else:
            return resp.content

    def query_saved(self, query_id, parameters=None, timeout=300, limit=100000):
        """Execute a saved query by ID.

        Args:
            query_id: The saved query ID (e.g., from a shared URL).
            parameters: Optional dict of parameter overrides.
            timeout: Max execution time.
            limit: Max rows.

        Returns:
            List of dicts.
        """
        body = {"options": {"timeout": timeout, "limit": limit}}
        if parameters:
            body["parameters"] = parameters

        resp = self.session.post(
            f"{self.base_url}/data-explorer/queries/{query_id}/execute",
            json=body,
        )
        if resp.status_code not in (200, 201, 202):
            raise TradingStudioError(f"Submit failed ({resp.status_code}): {resp.text[:500]}")
        task_id = resp.json().get("taskId") or resp.headers.get("X-Task-ID")

        task = self._poll(task_id, timeout=timeout)
        if task["status"] == "completed":
            return self._download(task)
        raise QueryFailedError(f"Saved query failed: {task.get('error', task['status'])}")
