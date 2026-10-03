"""Cross-language redistribution round-trip tests.

Verifies that all four wrappers preserve the `redistribution` field
through load → query → save, using a single shared fixture.

The Python wrapper is exercised in-process. The other three are
invoked via their own test runners, filtered to their redistribution
tests where the runner supports it. If a toolchain (Node.js, Go,
Cargo) is not installed, the corresponding test skips cleanly.

Run:
    pytest tests/test_cross_language_redistribution.py -v

Exit codes match the rest of the suite: 0 on success, 1 on any
failure. A skipped test is not a failure; it means the toolchain
was not available.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# The shared fixture
# ---------------------------------------------------------------------------

# Minimal action with `redistribution: "secondary-source"`. Just enough to
# prove the field survives a round-trip. No `provenance`, no `impact` —
# the wrappers don't need them for this test, and the validator is not
# invoked here.
FIXTURE = {
    "meta": {},
    "actions": [
        {
            "isin": "US0000000001",
            "action_id": "US0000000001-SPLIT-2024-01-01-2-1",
            "action_type": "SPLIT",
            "ratio": "2:1",
            "redistribution": "secondary-source",
            "dates": {
                "announcement": "2024-01-01",
                "effective_date": "2024-01-01",
            },
        }
    ],
}

# Same shape, but with the field absent. Used to prove no wrapper invents
# the field.
FIXTURE_NO_REDIST = {
    "meta": {},
    "actions": [
        {
            "isin": "US0000000001",
            "action_id": "US0000000001-SPLIT-2024-01-01-2-1",
            "action_type": "SPLIT",
            "ratio": "2:1",
            "dates": {
                "announcement": "2024-01-01",
                "effective_date": "2024-01-01",
            },
        }
    ],
}

ACTION_ID = "US0000000001-SPLIT-2024-01-01-2-1"
EXPECTED = "secondary-source"


# ---------------------------------------------------------------------------
# Python — the reference implementation
# ---------------------------------------------------------------------------

class TestPython:
    """The Python wrapper, loaded and exercised in-process."""

    @pytest.fixture(scope="class")
    def registry_cls(self):
        sys.path.insert(0, str(REPO_ROOT / "wrappers" / "python"))
        try:
            from corporate_actions_registry import CorporateActionsRegistry
        except ImportError as e:
            pytest.skip(f"Python wrapper not importable: {e}")
        return CorporateActionsRegistry

    def test_load_preserves_field(self, registry_cls):
        reg = registry_cls(actions_data=FIXTURE)
        action = reg.by_action_id(ACTION_ID)
        assert action is not None, "by_action_id returned None"
        assert action.redistribution == EXPECTED, (
            f"loaded redistribution={action.redistribution!r}, "
            f"expected {EXPECTED!r}"
        )

    def test_save_writes_field(self, registry_cls, tmp_path):
        reg = registry_cls(actions_data=FIXTURE)
        out = tmp_path / "out.json"
        reg.save(str(out))
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["actions"][0]["redistribution"] == EXPECTED, (
            f"saved file carries "
            f"redistribution={data['actions'][0].get('redistribution')!r}"
        )

    def test_absent_field_is_not_invented(self, registry_cls, tmp_path):
        reg = registry_cls(actions_data=FIXTURE_NO_REDIST)
        out = tmp_path / "out.json"
        reg.save(str(out))
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "redistribution" not in data["actions"][0], (
            "wrapper invented a redistribution value that was not in the input"
        )


# ---------------------------------------------------------------------------
# Rust
# ---------------------------------------------------------------------------

class TestRust:
    """Shell out to `cargo test`, filtered to redistribution tests."""

    @pytest.fixture(scope="class")
    def cargo(self):
        if not shutil.which("cargo"):
            pytest.skip("cargo not installed")
        return "cargo"

    def test_redistribution_tests_pass(self, cargo):
        result = subprocess.run(
            ["cargo", "test", "--quiet", "redistribution"],
            cwd=str(REPO_ROOT / "wrappers" / "rust"),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            pytest.fail(
                "cargo test redistribution failed:\n"
                f"--- stdout ---\n{result.stdout}\n"
                f"--- stderr ---\n{result.stderr}"
            )
        # `cargo test --quiet` prints only failures. A clean run prints
        # nothing. The exit code is the assertion.


# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------

class TestGo:
    """Shell out to `go test`, filtered to redistribution tests."""

    @pytest.fixture(scope="class")
    def go(self):
        if not shutil.which("go"):
            pytest.skip("go not installed")
        return "go"

    def test_redistribution_tests_pass(self, go):
        result = subprocess.run(
            ["go", "test", "./registry", "-run", "Redistribution", "-v"],
            cwd=str(REPO_ROOT / "wrappers" / "go"),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            pytest.fail(
                "go test -run Redistribution failed:\n"
                f"--- stdout ---\n{result.stdout}\n"
                f"--- stderr ---\n{result.stderr}"
            )
        # The Go test names are known. Assert each ran.
        for name in (
            "TestRedistributionRoundTrip",
            "TestAbsentRedistributionNotSerialized",
            "TestDeepCopyRedistribution",
        ):
            assert f"--- PASS: {name}" in result.stdout, (
                f"expected PASS for {name}, got:\n{result.stdout}"
            )


# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------

class TestJavaScript:
    """Shell out to `node --test`, then confirm the redistribution tests ran."""

    @pytest.fixture(scope="class")
    def node(self):
        if not shutil.which("node"):
            pytest.skip("node not installed")
        return "node"

    def test_redistribution_tests_pass(self, node):
        result = subprocess.run(
            ["node", "--test", "test/test_wrapper.js"],
            cwd=str(REPO_ROOT / "wrappers" / "javascript"),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            pytest.fail(
                "node --test failed:\n"
                f"--- stdout ---\n{result.stdout}\n"
                f"--- stderr ---\n{result.stderr}"
            )
        # Node's default reporter prints every test name in stdout.
        # The JS suite includes two redistribution tests.
        lower = result.stdout.lower()
        assert "redistribution" in lower, (
            "JS test output does not mention redistribution tests; "
            f"they may have been removed:\n{result.stdout}"
        )
        assert "# fail 0" in result.stdout, (
            f"JS test output reports failures:\n{result.stdout}"
        )