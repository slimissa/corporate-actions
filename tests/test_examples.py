"""End-to-end tests for the four example CLIs.

Each example is a standalone program a user copies and runs. These
tests execute them as subprocesses and assert on exit codes and
output substrings — the class of test that would have caught the four
example bugs fixed in H6.

Run from the repo root:
    python3 -m pytest tests/test_examples.py -v

Marked tests:
    @pytest.mark.network — runs yfinance fetches (backtest demo)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def run(cmd, cwd=REPO, timeout=120):
    return subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(cwd), timeout=timeout,
    )


class TestPythonExample:

    def test_lookup_runs(self):
        r = run([sys.executable, "examples/python_lookup.py",
                 "--actions", "actions.json"])
        assert r.returncode == 0, r.stdout + r.stderr
        assert "Loading registry from:" in r.stdout
        assert "total actions:" in r.stdout

    def test_lookup_with_isin(self):
        r = run([sys.executable, "examples/python_lookup.py",
                 "--actions", "actions.json",
                 "--isin", "US0378331005"])
        assert r.returncode == 0, r.stdout + r.stderr
        assert "Lookup by ISIN" in r.stdout


class TestJSExample:

    def test_lookup_runs(self):
        r = run(["node", "examples/javascript_lookup.js",
                 "--actions", "actions.json"])
        assert r.returncode == 0, r.stdout + r.stderr
        assert "Loading registry from:" in r.stdout

    def test_date_range_missing_end_exits_2(self):
        """#102: single-arg --date-range was silently accepted."""
        r = run(["node", "examples/javascript_lookup.js",
                 "--actions", "actions.json",
                 "--date-range", "2024-01-01"])
        assert r.returncode == 2, (
            f"expected exit 2, got {r.returncode}\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )

    def test_summary_suppresses_illustration(self):
        """#103: --summary didn't suppress the illustration block."""
        r = run(["node", "examples/javascript_lookup.js",
                 "--actions", "actions.json", "--summary"])
        assert r.returncode == 0, r.stdout + r.stderr
        assert "First 3 actions" not in r.stdout, (
            f"--summary should suppress illustration:\n{r.stdout}"
        )


class TestGoExample:
    """Go examples need `go run` from wrappers/go."""

    def test_lookup_runs(self):
        r = run(
            ["go", "run", "../../examples/go_lookup.go",
             "--actions", "../../actions.json"],
            cwd=REPO / "wrappers" / "go",
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert "Loading registry from:" in r.stdout


class TestRustExample:
    """Rust example needs `cargo run --example` from wrappers/rust."""

    def test_lookup_runs(self):
        r = run(
            ["cargo", "run", "--quiet", "--example", "rust_lookup", "--",
             "--actions", "../../actions.json"],
            cwd=REPO / "wrappers" / "rust",
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert "Loading registry from:" in r.stdout

    def test_default_does_not_double_print(self):
        """#101: 'First 3 actions' was printed twice without --summary."""
        r = run(
            ["cargo", "run", "--quiet", "--example", "rust_lookup", "--",
             "--actions", "../../actions.json"],
            cwd=REPO / "wrappers" / "rust",
        )
        assert r.returncode == 0, r.stdout + r.stderr
        count = r.stdout.count("First 3 actions")
        assert count == 1, (
            f"expected 1 illustration, got {count}:\n{r.stdout[:500]}"
        )

    def test_summary_suppresses_illustration(self):
        r = run(
            ["cargo", "run", "--quiet", "--example", "rust_lookup", "--",
             "--actions", "../../actions.json", "--summary"],
            cwd=REPO / "wrappers" / "rust",
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert "First 3 actions" not in r.stdout, (
            f"--summary should suppress illustration:\n{r.stdout}"
        )
