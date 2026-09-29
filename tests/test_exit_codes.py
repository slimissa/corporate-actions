"""Verify every tool uses the standard exit codes.

See docs/exit_codes.md for the convention.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _run(tool: str, *args: str) -> int:
    r = subprocess.run(
        [sys.executable, str(REPO / tool), *args],
        capture_output=True,
    )
    return r.returncode


@pytest.mark.parametrize("tool,missing_arg", [
    ("tools/validate.py",          ["--actions", "/nonexistent.json"]),
    ("tools/build.py",             ["--actions", "/nonexistent.json"]),
    ("tools/derive_impacts.py",    ["--actions", "/nonexistent.json"]),
    ("tools/merge_fetched.py",     ["--actions", "/nonexistent.json",
                                    "--fetched", "/nonexistent.json"]),
])
def test_missing_file_exits_3(tool: str, missing_arg: list) -> None:
    assert _run(tool, *missing_arg) == 3


@pytest.mark.parametrize("tool", [
    "tools/validate.py",
    "tools/build.py",
    "tools/derive_impacts.py",
    "tools/merge_fetched.py",
])
def test_bad_flag_exits_2(tool: str) -> None:
    assert _run(tool, "--no-such-flag") == 2