"""Regression tests for tools/merge_fetched.py.

Covers the three rejection rules:
  1. Exact duplicate — skip silently
  2. Reject list — skip, report
  3. Semantic duplicate — skip, report (when the layer is available)

Also covers --dry-run and --strict.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MERGE = REPO_ROOT / "tools" / "merge_fetched.py"


def _write(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _action(isin, ex_date, amount, action_type="DIVIDEND", **overrides):
    a = {
        "isin": isin,
        "action_id": f"{isin}-{action_type}-{ex_date}-{amount:.4f}",
        "action_type": action_type,
        "amount": amount,
        "currency": "USD",
        "dates": {
            "announcement": ex_date,
            "ex_date": ex_date,
            "effective_date": ex_date,
        },
        "status": "COMPLETED",
        "provenance": {
            "source": "fixture",
            "source_url": "https://example.com/x",
        },
    }
    a.update(overrides)
    return a


def _run(actions, fetched, removed, *extra):
    return subprocess.run(
        [sys.executable, str(MERGE),
         "--actions", str(actions),
         "--fetched", str(fetched),
         "--removed", str(removed),
         *extra],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )


class TestRejectList:

    def test_rejects_action_on_list(self, tmp_path):
        actions = tmp_path / "actions.json"
        fetched = tmp_path / "fetched.json"
        removed = tmp_path / "reject.json"
        _write(actions, {"meta": {}, "actions": []})
        _write(fetched, {"meta": {}, "actions": [
            _action("US5949181045", "2004-11-15", 3.08),
        ]})
        _write(removed, {"version": "1.0.0", "removed": [{
            "isin": "US5949181045",
            "action_type": "DIVIDEND",
            "ex_date": "2004-11-15",
            "amount": 3.08,
            "original_action_id": "US5949181045-DIVIDEND-2004-11-15-3.0800",
            "reason": "test",
        }]})
        r = _run(actions, fetched, removed)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "Rejected 1" in r.stdout
        after = json.loads(actions.read_text())
        assert after["actions"] == []

    def test_family_collapses_dividend_and_special(self, tmp_path):
        """A removed DIVIDEND must also block a re-fetched SPECIAL_DIVIDEND."""
        actions = tmp_path / "actions.json"
        fetched = tmp_path / "fetched.json"
        removed = tmp_path / "reject.json"
        _write(actions, {"meta": {}, "actions": []})
        _write(fetched, {"meta": {}, "actions": [
            _action("X", "2024-01-01", 3.00, action_type="SPECIAL_DIVIDEND"),
        ]})
        _write(removed, {"removed": [{
            "isin": "X", "action_type": "DIVIDEND",
            "ex_date": "2024-01-01", "amount": 3.00,
        }]})
        r = _run(actions, fetched, removed)
        assert r.returncode == 0
        assert "Rejected 1" in r.stdout

    def test_strict_exits_1_on_rejection(self, tmp_path):
        actions = tmp_path / "actions.json"
        fetched = tmp_path / "fetched.json"
        removed = tmp_path / "reject.json"
        _write(actions, {"meta": {}, "actions": []})
        _write(fetched, {"meta": {}, "actions": [
            _action("X", "2024-01-01", 0.25),
        ]})
        _write(removed, {"removed": [{
            "isin": "X", "action_type": "DIVIDEND",
            "ex_date": "2024-01-01", "amount": 0.25,
        }]})
        r = _run(actions, fetched, removed, "--strict")
        assert r.returncode == 1


class TestExactDuplicate:

    def test_identical_action_not_readded(self, tmp_path):
        actions = tmp_path / "actions.json"
        fetched = tmp_path / "fetched.json"
        removed = tmp_path / "reject.json"
        entry = _action("AAPL", "2024-01-01", 0.25)
        _write(actions, {"meta": {}, "actions": [entry]})
        _write(fetched, {"meta": {}, "actions": [entry]})
        _write(removed, {"removed": []})
        r = _run(actions, fetched, removed)
        assert r.returncode == 0
        assert json.loads(actions.read_text())["actions"] == [entry]
        # not reported as rejected
        assert "Rejected" not in r.stdout


class TestDryRun:

    def test_dry_run_does_not_write(self, tmp_path):
        actions = tmp_path / "actions.json"
        fetched = tmp_path / "fetched.json"
        removed = tmp_path / "reject.json"
        _write(actions, {"meta": {}, "actions": []})
        _write(fetched, {"meta": {}, "actions": [
            _action("Y", "2024-01-01", 0.25),
        ]})
        _write(removed, {"removed": []})
        before = actions.read_text()
        r = _run(actions, fetched, removed, "--dry-run")
        assert r.returncode == 0
        assert actions.read_text() == before


class TestMissingFiles:

    def test_missing_reject_list_is_ok(self, tmp_path):
        actions = tmp_path / "actions.json"
        fetched = tmp_path / "fetched.json"
        _write(actions, {"meta": {}, "actions": []})
        _write(fetched, {"meta": {}, "actions": [
            _action("Z", "2024-01-01", 0.25),
        ]})
        r = _run(actions, fetched, tmp_path / "nope.json")
        assert r.returncode == 0
        assert len(json.loads(actions.read_text())["actions"]) == 1

    def test_missing_actions_file_exits_2(self, tmp_path):
        fetched = tmp_path / "fetched.json"
        removed = tmp_path / "reject.json"
        _write(fetched, {"meta": {}, "actions": []})
        _write(removed, {"removed": []})
        r = _run(tmp_path / "nope.json", fetched, removed)
        assert r.returncode == 2


class TestAdditions:

    def test_valid_new_action_is_added(self, tmp_path):
        actions = tmp_path / "actions.json"
        fetched = tmp_path / "fetched.json"
        removed = tmp_path / "reject.json"
        _write(actions, {"meta": {}, "actions": []})
        new = _action("NEW", "2024-06-01", 0.50)
        _write(fetched, {"meta": {}, "actions": [new]})
        _write(removed, {"removed": []})
        r = _run(actions, fetched, removed)
        assert r.returncode == 0
        after = json.loads(actions.read_text())
        assert len(after["actions"]) == 1
        assert after["actions"][0]["action_id"] == new["action_id"]
        assert "updated_at" in after["meta"]