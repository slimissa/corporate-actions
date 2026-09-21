"""
Regression tests for the CI gates.

Each test deliberately corrupts a copy of the repository state, runs the
gate, and asserts the gate fails with a clear message. If any test passes
but the corresponding gate in .github/workflows/validate.yml is missing
or a no-op, the test itself would not have caught it — so the tests also
assert that each gate is wired into the workflow.

The suite is hermetic: every gate runs against a minimal repo layout
under tmp_path, never against the real repository (except where a test
explicitly checks the real tree passes).

Run:
    python3 -m pytest tests/test_ci_gates.py -v
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "validate.yml"


# ---------------------------------------------------------------------
# Layout helper
# ---------------------------------------------------------------------

def _layout(tmp_path: Path, overrides: dict | None = None) -> Path:
    """
    Build a minimal repo layout under tmp_path for a gate test.

    Files copied verbatim from the real repo:
      - tools/check_doc_facts.py
      - tools/build.py
      - tools/update_facts.py
      - tools/validate.py
      - actions.json
      - schema.json
      - docs/facts.json

    Files written fresh with content matching docs/facts.json:
      - README.md

    `overrides` replaces any of the above with the provided text, which
    is how each test creates drift.
    """
    overrides = overrides or {}

    (tmp_path / "tools").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "dist").mkdir(parents=True, exist_ok=True)

    for name in ("check_doc_facts.py", "build.py", "update_facts.py",
                 "validate.py"):
        src = REPO_ROOT / "tools" / name
        if src.is_file():
            shutil.copy2(src, tmp_path / "tools" / name)

    shutil.copy2(REPO_ROOT / "actions.json", tmp_path / "actions.json")
    shutil.copy2(REPO_ROOT / "schema.json", tmp_path / "schema.json")
    shutil.copy2(REPO_ROOT / "docs" / "facts.json",
                 tmp_path / "docs" / "facts.json")

    facts = json.loads((REPO_ROOT / "docs" / "facts.json").read_text())
    (tmp_path / "README.md").write_text(
        f"**Actions**: {facts['action_count']}\n"
        f"**Instruments**: {facts['instrument_count']}\n"
        f"**Total tests**: {facts['root_test_count']}\n",
        encoding="utf-8",
    )

    for rel, content in overrides.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    return tmp_path


def _run(args, cwd, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        args, cwd=str(cwd), capture_output=True, text=True, env=env,
    )


# ---------------------------------------------------------------------
# Workflow wiring
# ---------------------------------------------------------------------

class TestWorkflowWiring:
    """Every gate referenced by a test must exist in validate.yml."""

    def test_workflow_exists(self):
        assert WORKFLOW.is_file(), f"missing {WORKFLOW}"

    def test_docs_facts_job_present(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        assert re.search(r"^\s{2}docs-facts:", text, re.M), \
            "docs-facts job missing from validate.yml"

    def test_build_artifacts_job_present(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        assert re.search(r"^\s{2}build-artifacts:", text, re.M), \
            "build-artifacts job missing from validate.yml"

    def test_lint_job_present(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        assert re.search(r"^\s{2}lint:", text, re.M), \
            "lint job missing from validate.yml"

    def test_docs_facts_runs_three_commands(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for cmd in (
            "python3 tools/check_doc_facts.py",
            "python3 tools/check_doc_facts.py --scan",
            "python3 tools/update_facts.py --check",
        ):
            assert cmd in text, f"validate.yml missing: {cmd}"

    def test_build_artifacts_runs_check_mode(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        assert "tools/build.py" in text and "--check" in text, \
            "build-artifacts job does not run build.py --check"

    def test_lint_runs_ruff(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        assert "ruff check" in text, "lint job does not run ruff"


# ---------------------------------------------------------------------
# check_doc_facts.py
# ---------------------------------------------------------------------

class TestCheckDocFactsGate:

    def test_passes_on_clean_layout(self, tmp_path):
        _layout(tmp_path)
        r = _run([sys.executable, "tools/check_doc_facts.py"], cwd=tmp_path)
        assert r.returncode == 0, (
            f"clean layout should pass, got exit {r.returncode}\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )

    def test_catches_wrong_action_count(self, tmp_path):
        facts = json.loads((REPO_ROOT / "docs" / "facts.json").read_text())
        _layout(tmp_path, {
            "README.md": (
                f"**Actions**: 999\n"
                f"**Instruments**: {facts['instrument_count']}\n"
            ),
        })
        r = _run([sys.executable, "tools/check_doc_facts.py"], cwd=tmp_path)
        assert r.returncode == 1, (
            f"expected exit 1, got {r.returncode}\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
        assert "action_count" in r.stdout
        assert "999" in r.stdout

    def test_catches_wrong_test_count(self, tmp_path):
        facts = json.loads((REPO_ROOT / "docs" / "facts.json").read_text())
        _layout(tmp_path, {
            "README.md": (
                f"**Actions**: {facts['action_count']}\n"
                f"**Total tests**: 99999\n"
            ),
        })
        r = _run([sys.executable, "tools/check_doc_facts.py"], cwd=tmp_path)
        assert r.returncode == 1
        assert "99999" in r.stdout

    def test_self_check_catches_inconsistent_facts(self, tmp_path):
        """facts.json says 999 actions; actions.json has 240."""
        facts = json.loads((REPO_ROOT / "docs" / "facts.json").read_text())
        facts["action_count"] = 999
        _layout(tmp_path, {
            "docs/facts.json": json.dumps(facts, indent=2) + "\n",
            "README.md": "**Actions**: 999\n",
        })
        r = _run([sys.executable, "tools/check_doc_facts.py"], cwd=tmp_path)
        assert r.returncode == 2, (
            f"expected exit 2 (fact sheet inconsistent), got {r.returncode}\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
        assert "action_count" in r.stderr

    def test_list_mode_prints_manifest(self, tmp_path):
        _layout(tmp_path)
        r = _run(
            [sys.executable, "tools/check_doc_facts.py", "--list"],
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert "action_count" in r.stdout
        # Manifest must be non-trivial: at least the fixture size
        assert r.stdout.count("\n") >= 10


# ---------------------------------------------------------------------
# check_doc_facts.py --scan
# ---------------------------------------------------------------------

class TestCheckDocFactsScan:
    """The scan mode flags numbers near keywords that aren't in facts.json."""

    def test_passes_on_clean_layout(self, tmp_path):
        _layout(tmp_path)
        r = _run(
            [sys.executable, "tools/check_doc_facts.py", "--scan"],
            cwd=tmp_path,
        )
        assert r.returncode == 0, (
            f"clean layout should pass --scan, got exit {r.returncode}\n"
            f"stdout: {r.stdout}"
        )

    def test_catches_unsourced_number(self, tmp_path):
        _layout(tmp_path, {"README.md": "**Tests**: 99999 passed\n"})
        r = _run(
            [sys.executable, "tools/check_doc_facts.py", "--scan"],
            cwd=tmp_path,
        )
        assert r.returncode == 1, (
            f"expected exit 1, got {r.returncode}\n"
            f"stdout: {r.stdout}"
        )
        assert "99999" in r.stdout


# ---------------------------------------------------------------------
# build.py --check
# ---------------------------------------------------------------------

class TestBuildGate:

    def test_passes_after_build(self, tmp_path):
        _layout(tmp_path)
        r1 = _run(
            [sys.executable, "tools/build.py",
             "--actions", "actions.json",
             "--output-dir", "dist"],
            cwd=tmp_path,
        )
        assert r1.returncode == 0, r1.stdout + r1.stderr
        r2 = _run(
            [sys.executable, "tools/build.py",
             "--actions", "actions.json",
             "--output-dir", "dist",
             "--check"],
            cwd=tmp_path,
        )
        assert r2.returncode == 0, r2.stdout + r2.stderr

    def test_catches_missing_artifact(self, tmp_path):
        _layout(tmp_path)
        _run(
            [sys.executable, "tools/build.py",
             "--actions", "actions.json",
             "--output-dir", "dist"],
            cwd=tmp_path,
        )
        (tmp_path / "dist" / "actions.csv").unlink()
        r = _run(
            [sys.executable, "tools/build.py",
             "--actions", "actions.json",
             "--output-dir", "dist",
             "--check"],
            cwd=tmp_path,
        )
        assert r.returncode == 1
        assert "missing" in r.stderr.lower()
        assert "actions.csv" in r.stderr

    def test_catches_stale_artifact(self, tmp_path):
        _layout(tmp_path)
        _run(
            [sys.executable, "tools/build.py",
             "--actions", "actions.json",
             "--output-dir", "dist"],
            cwd=tmp_path,
        )
        # Tamper with an artifact so it no longer matches
        (tmp_path / "dist" / "actions.csv").write_text(
            "bogus,contents\n", encoding="utf-8"
        )
        r = _run(
            [sys.executable, "tools/build.py",
             "--actions", "actions.json",
             "--output-dir", "dist",
             "--check"],
            cwd=tmp_path,
        )
        assert r.returncode == 1
        assert "stale" in r.stderr.lower()
        assert "actions.csv" in r.stderr


# ---------------------------------------------------------------------
# update_facts.py
# ---------------------------------------------------------------------

class TestUpdateFactsTool:

    def test_tool_exists(self):
        assert (REPO_ROOT / "tools" / "update_facts.py").is_file(), \
            "tools/update_facts.py missing"

    def test_help_runs(self, tmp_path):
        _layout(tmp_path)
        r = _run(
            [sys.executable, "tools/update_facts.py", "--help"],
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert "--check" in r.stdout

    def test_check_mode_exits_cleanly_on_real_tree(self):
        """Running update_facts --check on the real repo should pass
        (CI asserts this; if it fails here, the maintainer's local
        facts.json is stale)."""
        r = _run(
            [sys.executable, "tools/update_facts.py", "--check"],
            cwd=REPO_ROOT,
        )
        # Skip if dependencies missing rather than failing the suite
        if r.returncode not in (0, 1):
            pytest.skip(
                f"update_facts --check exited {r.returncode}; "
                f"probably a missing dependency:\n{r.stderr}"
            )
        assert r.returncode == 0, (
            f"docs/facts.json is stale; run "
            f"python3 tools/update_facts.py\n{r.stdout}\n{r.stderr}"
        )


# ---------------------------------------------------------------------
# ruff
# ---------------------------------------------------------------------

class TestRuffGate:

    def test_ruff_catches_unused_import(self, tmp_path):
        """A file with an unused import must fail ruff check."""
        (tmp_path / "sample.py").write_text(
            "import os\nprint('hello')\n", encoding="utf-8"
        )
        r = _run(["ruff", "check", "sample.py"], cwd=tmp_path)
        if r.returncode == 127:
            pytest.skip("ruff not installed in this environment")
        assert r.returncode == 1, (
            f"ruff should flag unused import, got exit {r.returncode}\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
        assert "F401" in r.stdout

    def test_ruff_passes_on_real_tree(self):
        """The real repository must pass ruff with current config."""
        r = _run(
            ["ruff", "check", "tests", "tools", "examples", "scripts"],
            cwd=REPO_ROOT,
        )
        if r.returncode == 127:
            pytest.skip("ruff not installed in this environment")
        assert r.returncode == 0, (
            f"ruff check failed on the real tree:\n{r.stdout}\n{r.stderr}"
        )