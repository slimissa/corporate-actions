"""
Tests for scripts/notify_on_change.py

Covers:
  - Hash computation
  - State file load/save
  - First-run behavior (no state file)
  - Change detection (hash differs → notification)
  - No-change detection (same hash → silent)
  - Webhook failure handling
  - CLI usage via subprocess
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Ensure the repo root and scripts dir are importable.
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

import notify_on_change as noc  # noqa: E402


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------

@pytest.fixture
def tmp_actions(tmp_path):
    """Create a small actions.json-like file and return its path."""
    p = tmp_path / "actions.json"
    p.write_text('{"meta": {"version": "1.0.0"}, "actions": []}', encoding="utf-8")
    return p


@pytest.fixture
def tmp_state(tmp_path):
    """Return a state file path inside a temp directory."""
    return tmp_path / ".notify_state.json"


# ----------------------------------------------------------------------
# compute_sha256
# ----------------------------------------------------------------------

class TestComputeSha256:
    def test_returns_hex_digest(self, tmp_actions):
        digest = noc.compute_sha256(str(tmp_actions))
        assert isinstance(digest, str)
        assert len(digest) == 64
        int(digest, 16)  # must be valid hex

    def test_matches_manual_hash(self, tmp_actions):
        expected = hashlib.sha256(tmp_actions.read_bytes()).hexdigest()
        assert noc.compute_sha256(str(tmp_actions)) == expected

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            noc.compute_sha256(str(tmp_path / "nope.json"))

    def test_hash_changes_with_content(self, tmp_actions):
        h1 = noc.compute_sha256(str(tmp_actions))
        tmp_actions.write_text('{"meta": {"version": "2.0.0"}, "actions": []}', encoding="utf-8")
        h2 = noc.compute_sha256(str(tmp_actions))
        assert h1 != h2


# ----------------------------------------------------------------------
# load_state / save_state
# ----------------------------------------------------------------------

class TestStatePersistence:
    def test_load_missing_returns_empty(self, tmp_state):
        assert noc.load_state(str(tmp_state)) == {}

    def test_load_invalid_json_returns_empty(self, tmp_state):
        tmp_state.write_text("not json", encoding="utf-8")
        assert noc.load_state(str(tmp_state)) == {}

    def test_save_then_load_roundtrip(self, tmp_state):
        noc.save_state(str(tmp_state), "deadbeef")
        state = noc.load_state(str(tmp_state))
        assert state["hash"] == "deadbeef"
        assert "updated_at" in state

    def test_save_overwrites(self, tmp_state):
        noc.save_state(str(tmp_state), "aaa")
        noc.save_state(str(tmp_state), "bbb")
        assert noc.load_state(str(tmp_state))["hash"] == "bbb"

    def test_save_produces_valid_json(self, tmp_state):
        noc.save_state(str(tmp_state), "cafebabe")
        data = json.loads(tmp_state.read_text(encoding="utf-8"))
        assert set(data.keys()) >= {"hash", "updated_at"}


# ----------------------------------------------------------------------
# send_webhook_notification
# ----------------------------------------------------------------------

class TestWebhook:
    def test_unreachable_webhook_returns_false(self):
        # Reserved TEST-NET-1 address per RFC 5737, guaranteed unroutable.
        result = noc.send_webhook_notification(
            webhook_url="http://192.0.2.1/hook",
            old_hash="aaa",
            new_hash="bbb",
            actions_path="actions.json",
        )
        assert result is False

    def test_invalid_url_returns_false(self):
        result = noc.send_webhook_notification(
            webhook_url="not-a-url",
            old_hash=None,
            new_hash="bbb",
            actions_path="actions.json",
        )
        assert result is False


# ----------------------------------------------------------------------
# CLI end-to-end via subprocess
# ----------------------------------------------------------------------

def run_cli(args, cwd):
    """Run notify_on_change.py as a subprocess and capture output."""
    script = SCRIPTS_DIR / "notify_on_change.py"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, str(script)] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


class TestCLI:
    def test_first_run_detects_change(self, tmp_actions, tmp_state):
        result = run_cli(
            [
                "--actions", str(tmp_actions),
                "--state", str(tmp_state),
            ],
            cwd=str(tmp_actions.parent),
        )
        assert result.returncode == 0
        assert "First run detected" in result.stdout or "Change detected" in result.stdout
        assert tmp_state.exists()

    def test_second_run_silent(self, tmp_actions, tmp_state):
        # First run: establish state.
        run_cli(
            ["--actions", str(tmp_actions), "--state", str(tmp_state)],
            cwd=str(tmp_actions.parent),
        )
        # Second run: no change.
        result = run_cli(
            ["--actions", str(tmp_actions), "--state", str(tmp_state)],
            cwd=str(tmp_actions.parent),
        )
        assert result.returncode == 0
        assert "Change detected" not in result.stdout
        assert "First run" not in result.stdout

    def test_content_change_detected(self, tmp_actions, tmp_state):
        # First run.
        run_cli(
            ["--actions", str(tmp_actions), "--state", str(tmp_state)],
            cwd=str(tmp_actions.parent),
        )
        # Modify.
        tmp_actions.write_text('{"meta": {"version": "2.0.0"}, "actions": []}', encoding="utf-8")
        # Second run should detect.
        result = run_cli(
            ["--actions", str(tmp_actions), "--state", str(tmp_state)],
            cwd=str(tmp_actions.parent),
        )
        assert result.returncode == 0
        assert "Change detected" in result.stdout

    def test_missing_actions_file_exits_1(self, tmp_path, tmp_state):
        result = run_cli(
            [
                "--actions", str(tmp_path / "nope.json"),
                "--state", str(tmp_state),
            ],
            cwd=str(tmp_path),
        )
        assert result.returncode == 1
        assert "not found" in result.stderr.lower()

    def test_verbose_flag(self, tmp_actions, tmp_state):
        result = run_cli(
            [
                "--actions", str(tmp_actions),
                "--state", str(tmp_state),
                "--verbose",
            ],
            cwd=str(tmp_actions.parent),
        )
        assert result.returncode == 0
        assert "Actions path" in result.stdout
        assert "New hash" in result.stdout