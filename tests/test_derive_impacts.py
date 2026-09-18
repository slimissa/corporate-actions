"""
Tests for tools/derive_impacts.py.

The tool derives impact multipliers from an action's ratio or amount.
It must:

- Produce the correct multipliers for each supported action type.
- Reject ratios that validate_arithmetic would also reject, so the two
  tools cannot disagree.
- Refuse to write the file if any action fails, leaving the original
  file byte-identical.
- Write atomically: no truncated file if the process dies mid-write.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.derive_impacts import derive_impact, parse_ratio


# ---------------------------------------------------------------------------
# parse_ratio
# ---------------------------------------------------------------------------

class TestParseRatio:

    @pytest.mark.parametrize("ratio,expected", [
        ("10:1", (10, 1)),
        ("4:1", (4, 1)),
        ("1:8", (1, 8)),
        ("3:2", (3, 2)),
        ("20:1", (20, 1)),
    ])
    def test_valid(self, ratio, expected):
        assert parse_ratio(ratio) == expected

    @pytest.mark.parametrize("ratio", [
        "4.5:1",     # decimal — accepted by the old float() parser
        "0.5:1",     # decimal
        "10:1.5",    # decimal on the other side
        "10 : 1",    # spaces
        "10-1",      # dash instead of colon
        "10/1",      # slash
        "0:1",       # zero numerator
        "1:0",       # zero denominator
        "-1:2",      # negative
        "1:-2",      # negative
        "a:b",       # non-numeric
        "10:",       # missing denominator
        ":1",        # missing numerator
        "",          # empty
        "10:1:2",    # too many parts
    ])
    def test_invalid(self, ratio):
        assert parse_ratio(ratio) is None

    def test_none_returns_none(self):
        assert parse_ratio(None) is None

    def test_int_returns_none(self):
        """A non-string input is rejected, not coerced."""
        assert parse_ratio(10) is None


# ---------------------------------------------------------------------------
# derive_impact
# ---------------------------------------------------------------------------

class TestDeriveImpact:

    def test_split_10_1(self):
        impact = derive_impact({"action_type": "SPLIT", "ratio": "10:1", "action_id": "A"})
        assert impact == {
            "price_multiplier": 0.1,
            "share_multiplier": 10.0,
            "cash_adjustment": 0.0,
        }

    def test_split_4_1(self):
        impact = derive_impact({"action_type": "SPLIT", "ratio": "4:1", "action_id": "A"})
        assert impact["price_multiplier"] == 0.25
        assert impact["share_multiplier"] == 4.0

    def test_reverse_split_1_8(self):
        impact = derive_impact({"action_type": "REVERSE_SPLIT", "ratio": "1:8", "action_id": "A"})
        assert impact["price_multiplier"] == 8.0
        assert impact["share_multiplier"] == 0.125

    def test_dividend(self):
        impact = derive_impact({"action_type": "DIVIDEND", "amount": 0.25, "action_id": "A"})
        assert impact == {
            "price_multiplier": 1.0,
            "share_multiplier": 1.0,
            "cash_adjustment": 0.25,
        }

    def test_special_dividend(self):
        impact = derive_impact({"action_type": "SPECIAL_DIVIDEND", "amount": 3.0, "action_id": "A"})
        assert impact["cash_adjustment"] == 3.0

    @pytest.mark.parametrize("action_type", [
        "SYMBOL_CHANGE", "DELISTING", "SPINOFF", "MERGER",
    ])
    def test_neutral_types(self, action_type):
        impact = derive_impact({"action_type": action_type, "action_id": "A"})
        assert impact == {
            "price_multiplier": 1.0,
            "share_multiplier": 1.0,
            "cash_adjustment": 0.0,
        }

    @pytest.mark.parametrize("action", [
        {"action_type": "SPLIT", "action_id": "A"},                       # missing ratio
        {"action_type": "SPLIT", "ratio": "4.5:1", "action_id": "A"},      # decimal ratio
        {"action_type": "SPLIT", "ratio": "0:1", "action_id": "A"},        # zero
        {"action_type": "DIVIDEND", "action_id": "A"},                     # missing amount
        {"action_type": "DIVIDEND", "amount": -0.25, "action_id": "A"},    # negative
        {"action_type": "DIVIDEND", "amount": "lots", "action_id": "A"},   # non-numeric
        {"action_type": "UNKNOWN_TYPE", "action_id": "A"},                 # unknown type
        {"action_id": "A"},                                                 # no type
    ])
    def test_failures_return_none(self, action):
        assert derive_impact(action) is None


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

def _run_tool(tmp_path, actions, *, dry_run=False):
    path = tmp_path / "actions.json"
    payload = {"meta": {"version": "1.0.0"}, "actions": actions}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    cmd = [
        sys.executable, str(REPO_ROOT / "tools" / "derive_impacts.py"),
        "--actions", str(path),
    ]
    if dry_run:
        cmd.append("--dry-run")

    return path, subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))


class TestIntegration:

    def test_valid_file_is_written(self, tmp_path):
        path, result = _run_tool(tmp_path, [
            {"action_id": "A", "action_type": "SPLIT", "ratio": "10:1"},
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        after = json.loads(path.read_text())
        assert after["actions"][0]["impact"]["share_multiplier"] == 10.0

    def test_failure_leaves_file_unchanged(self, tmp_path):
        """The critical guarantee: one bad action means no write at all."""
        actions = [
            {"action_id": "A", "action_type": "SPLIT", "ratio": "10:1"},
            {"action_id": "B", "action_type": "SPLIT", "ratio": "4.5:1"},   # bad
        ]
        path, result = _run_tool(tmp_path, actions)
        assert result.returncode == 1
        after = json.loads(path.read_text())
        # The good action must NOT have had its impact set.
        assert "impact" not in after["actions"][0]

    def test_failure_names_the_action(self, tmp_path):
        actions = [
            {"action_id": "US0000000001-SPLIT-2024-01-01-4-1",
             "action_type": "SPLIT", "ratio": "4.5:1"},
        ]
        _, result = _run_tool(tmp_path, actions)
        assert result.returncode == 1
        assert "US0000000001-SPLIT-2024-01-01-4-1" in result.stderr

    def test_dry_run_does_not_write(self, tmp_path):
        path, result = _run_tool(tmp_path, [
            {"action_id": "A", "action_type": "SPLIT", "ratio": "10:1"},
        ], dry_run=True)
        assert result.returncode == 0
        after = json.loads(path.read_text())
        assert "impact" not in after["actions"][0]

    def test_missing_file_exits_2(self, tmp_path):
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "derive_impacts.py"),
             "--actions", str(tmp_path / "nope.json")],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        assert result.returncode == 2

    def test_idempotent_on_valid_file(self, tmp_path):
        actions = [{"action_id": "A", "action_type": "SPLIT", "ratio": "10:1"}]
        path, result = _run_tool(tmp_path, actions)
        assert result.returncode == 0
        first = path.read_text()
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "derive_impacts.py"),
             "--actions", str(path)],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        assert path.read_text() == first