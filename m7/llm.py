"""M7 Pairwise Comparison: LLM runner via claude CLI with logging and resume."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from .config import MODELS
from .prompts import build_prompt, parse_response

# Model key -> claude CLI alias
CLI_MODEL_ALIAS = {
    "claude-haiku": "haiku",
    "claude-sonnet": "sonnet",
    "claude-opus": "opus",
}

# Run claude CLI from this directory so it picks up the M7 CLAUDE.md
# instead of ATO_SUITE's CLAUDE.md (which tells models they're coding assistants)
CLI_RUNNER_DIR = os.path.expanduser("~/.m7-runner")


def _find_claude():
    """Find the claude CLI binary."""
    path = shutil.which("claude")
    if path:
        return path
    # Common install locations
    for candidate in ["/opt/homebrew/bin/claude", "/usr/local/bin/claude"]:
        if os.path.isfile(candidate):
            return candidate
    return None


class LLMRunner:
    """Runs LLM calls via claude CLI with logging and resumability.

    Uses `claude --print` to call models without needing an API key.
    Logs every call to a JSONL file. On resume, skips completed pair_ids.
    """

    def __init__(self, model_key, prompt_variant, output_dir, verbose=False,
                 thinking_tokens=0, effort=None):
        self.model_key = model_key
        self.model_config = MODELS[model_key]
        self.cli_model = CLI_MODEL_ALIAS[model_key]
        self.prompt_variant = prompt_variant
        self.output_dir = Path(output_dir)
        self.verbose = verbose
        self.thinking_tokens = thinking_tokens
        self.effort = effort
        self.timeout = 120 if not thinking_tokens and not effort else 180

        self.claude_path = _find_claude()
        if not self.claude_path:
            raise RuntimeError("claude CLI not found. Install from https://claude.ai/claude-code")

        self.log_path = self.output_dir / "llm_calls.jsonl"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load completed pair_ids for resume
        self.completed = {}
        if self.log_path.exists():
            with open(self.log_path) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        self.completed[entry["pair_id"]] = entry
                    except (json.JSONDecodeError, KeyError):
                        continue
            if self.verbose:
                print(f"  Resuming: {len(self.completed)} pairs already completed")

    def run(self, pairs):
        """Run LLM on all pairs, skipping completed ones.

        Returns list of result dicts.
        """
        results = list(self.completed.values())
        remaining = [p for p in pairs if p["pair_id"] not in self.completed]

        if self.verbose:
            print(f"  Running {len(remaining)} pairs "
                  f"({len(self.completed)} already done, {len(pairs)} total)")

        for i, pair in enumerate(remaining):
            result = self._call_claude(pair)
            results.append(result)

            with open(self.log_path, "a") as f:
                f.write(json.dumps(result) + "\n")

            if self.verbose and (i + 1) % 10 == 0:
                cost_so_far = sum(r.get("cost_usd", 0) for r in results)
                print(f"    {i + 1}/{len(remaining)} done, "
                      f"${cost_so_far:.4f} total cost")

        return results

    def _call_claude(self, pair):
        """Call claude CLI for a single pair. Returns result dict."""
        system_prompt, user_prompt = build_prompt(
            pair["stock_x"]["metrics"],
            pair["stock_y"]["metrics"],
            self.prompt_variant,
        )

        cmd = [
            self.claude_path,
            "--print",
            "--model", self.cli_model,
            "--output-format", "json",
            "--no-session-persistence",
            "--tools", "",
        ]
        if self.thinking_tokens:
            cmd.extend(["--max-thinking-tokens", str(self.thinking_tokens)])
        if self.effort:
            cmd.extend(["--effort", self.effort])
        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])

        # Strip CLAUDECODE env var to allow nested invocation
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        t0 = time.time()
        try:
            result = subprocess.run(
                cmd,
                input=user_prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
                cwd=CLI_RUNNER_DIR,
            )

            latency_ms = int((time.time() - t0) * 1000)

            if result.returncode != 0:
                error_msg = result.stderr.strip()[:500] if result.stderr else f"exit code {result.returncode}"
                return self._error_result(pair, latency_ms, error_msg)

            # Parse JSON response from claude CLI
            try:
                response = json.loads(result.stdout)
            except json.JSONDecodeError:
                # Fallback: treat stdout as raw text
                text = result.stdout.strip()
                parsed = parse_response(text)
                return self._build_result(pair, latency_ms, text, parsed,
                                          tokens_in=0, tokens_out=0, cost=0)

            text = response.get("result", "")
            usage = response.get("usage", {})
            tokens_in = usage.get("input_tokens", 0)
            tokens_out = usage.get("output_tokens", 0)
            cost = response.get("total_cost_usd", 0)

            parsed = parse_response(text)

            return self._build_result(pair, latency_ms, text, parsed,
                                      tokens_in=tokens_in, tokens_out=tokens_out,
                                      cost=cost)

        except subprocess.TimeoutExpired:
            latency_ms = int((time.time() - t0) * 1000)
            return self._error_result(pair, latency_ms, f"Timed out after {self.timeout}s")

        except Exception as e:
            latency_ms = int((time.time() - t0) * 1000)
            return self._error_result(pair, latency_ms, str(e))

    def _build_result(self, pair, latency_ms, text, parsed, tokens_in, tokens_out, cost):
        return {
            "pair_id": pair["pair_id"],
            "model": self.model_key,
            "model_id": self.model_config["model_id"],
            "prompt_variant": self.prompt_variant,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": latency_ms,
            "cost_usd": round(cost, 6),
            "pick": parsed["pick"],
            "confidence": parsed["confidence"],
            "reasoning": parsed["reasoning"],
            "parse_error": parsed["parse_error"],
            "raw_response": text[:2000],
            "error": None,
        }

    def _error_result(self, pair, latency_ms, error_msg):
        return {
            "pair_id": pair["pair_id"],
            "model": self.model_key,
            "model_id": self.model_config["model_id"],
            "prompt_variant": self.prompt_variant,
            "tokens_in": 0,
            "tokens_out": 0,
            "latency_ms": latency_ms,
            "cost_usd": 0,
            "pick": None,
            "confidence": None,
            "reasoning": "",
            "parse_error": None,
            "raw_response": "",
            "error": error_msg,
        }


def load_llm_results(path):
    """Load LLM results from JSONL file."""
    results = []
    with open(path) as f:
        for line in f:
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return results
