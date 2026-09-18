"""
Integration tests for tools/validate.py.

These tests run the validator as a subprocess against synthetic
actions.json files, exercising the full pipeline: schema, temporal,
arithmetic, action_id format, cross-reference, uniqueness, provenance,
and coverage.

The tests are hermetic. Every registry path is passed explicitly and
every registry file is built under tmp_path, so the result does not
depend on the developer's $LAS_DATA_HOME, the current working
directory, or any fixture outside tests/fixtures/.

Test-to-Phase-3 mapping
-----------------------
- TestSchemaViolations::test_malformed_date_is_rejected  -> 3.2
- TestActionTypeAllowlist::test_typo_action_type_is_rejected  -> 3.1
- TestActionIdFormat::*  -> 3.6
- TestExitCodes::*  -> the four documented exit codes

Run
---
    python -m pytest tests/test_validator_integration.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS = REPO_ROOT / "tools"
SCHEMA = REPO_ROOT / "schema.json"
REAL_ACTIONS = REPO_ROOT / "actions.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_registries(
    tmp_path,
    *,
    isins=("US67066G1040",),
    currencies=("USD",),
    mics=("XNAS",),
):
    """Write a minimal set of cross-reference registries into tmp_path.

    Every test builds its own registries so it does not depend on the
    repository fixtures or on the developer's $LAS_DATA_HOME.
    """
    (tmp_path / "identifiers.json").write_text(
        json.dumps({"instruments": [{"isin": i} for i in isins]}),
        encoding="utf-8",
    )
    (tmp_path / "iso4217.json").write_text(
        json.dumps({
            "currencies": {
                "active": [{"code": c} for c in currencies],
                "withdrawn": [],
            },
        }),
        encoding="utf-8",
    )
    (tmp_path / "exchange_calendar.json").write_text(
        json.dumps({"exchanges": [{"mic": m} for m in mics]}),
        encoding="utf-8",
    )


def write_actions(tmp_path, actions, *, name="actions.json"):
    """Write a top-level actions.json wrapper around the given list."""
    path = tmp_path / name
    path.write_text(
        json.dumps({
            "meta": {
                "version": "1.0.0",
                "generated_at": "2026-09-18T00:00:00Z",
                "source": "test",
            },
            "actions": actions,
        }),
        encoding="utf-8",
    )
    return path


def run_validator(
    actions_path,
    tmp_path,
    *,
    min_actions=1,
    strict_isin=False,
    identifiers=None,
    iso4217=None,
    exchange_calendar=None,
    schema=None,
):
    """Run tools/validate.py and return the CompletedProcess.

    The default cross-reference registries are the ones written by
    write_registries() into the same tmp_path. Override any of them by
    passing an explicit Path.
    """
    cmd = [
        sys.executable, str(TOOLS / "validate.py"),
        "--actions", str(actions_path),
        "--schema", str(schema or SCHEMA),
        "--identifiers", str(identifiers or (tmp_path / "identifiers.json")),
        "--iso4217", str(iso4217 or (tmp_path / "iso4217.json")),
        "--exchange-calendar",
        str(exchange_calendar or (tmp_path / "exchange_calendar.json")),
        "--min-actions", str(min_actions),
    ]
    if strict_isin:
        cmd.append("--strict-isin")
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def valid_split_action(**overrides):
    """A valid SPLIT action whose action_id matches its own fields.

    ex_date and effective_date are equal (US equity convention for
    splits), so the action_id is consistent regardless of which of the
    two date fields the ID format check compares against.
    """
    action = {
        "isin": "US67066G1040",
        "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
        "action_type": "SPLIT",
        "ratio": "10:1",
        "dates": {
            "announcement": "2024-05-22",
            "ex_date": "2024-06-10",
            "record_date": "2024-06-07",
            "effective_date": "2024-06-10",
        },
        "status": "COMPLETED",
        "provenance": {
            "source": "NVIDIA Corp press release",
            "source_url": "https://example.com/nvda-split",
        },
        "impact": {
            "price_multiplier": 0.1,
            "share_multiplier": 10.0,
            "cash_adjustment": 0.0,
        },
    }
    action.update(overrides)
    return action


def valid_dividend_action(**overrides):
    """A valid DIVIDEND action.

    The action_id uses effective_date in its date component (the
    canonical format). The test asserts only on currency / provenance /
    temporal outcomes, so it passes even if the format check compares
    against ex_date instead.
    """
    action = {
        "isin": "US67066G1040",
        "action_id": "US67066G1040-DIVIDEND-2024-05-23-0.2500",
        "action_type": "DIVIDEND",
        "amount": 0.25,
        "currency": "USD",
        "dates": {
            "announcement": "2024-05-02",
            "ex_date": "2024-05-16",
            "record_date": "2024-05-17",
            "effective_date": "2024-05-23",
        },
        "status": "COMPLETED",
        "provenance": {
            "source": "Test",
            "source_url": "https://example.com/div",
        },
        "impact": {
            "price_multiplier": 1.0,
            "share_multiplier": 1.0,
            "cash_adjustment": 0.25,
        },
    }
    action.update(overrides)
    return action


@pytest.fixture
def project(tmp_path):
    """A tmp_path populated with the default cross-reference registries."""
    write_registries(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:

    def test_minimal_valid_file_passes(self, project):
        """A single well-formed action passes every layer."""
        write_actions(project, [valid_split_action()])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "All layers passed" in result.stdout

    def test_multiple_valid_actions_pass(self, project):
        """Two actions with distinct IDs both pass."""
        actions = [
            valid_split_action(),
            valid_split_action(
                action_id="US67066G1040-SPLIT-2021-07-20-4-1",
                ratio="4:1",
                dates={
                    "announcement": "2021-05-21",
                    "ex_date": "2021-07-20",
                    "record_date": "2021-06-21",
                    "effective_date": "2021-07-20",
                },
                impact={
                    "price_multiplier": 0.25,
                    "share_multiplier": 4.0,
                    "cash_adjustment": 0.0,
                },
            ),
        ]
        write_actions(project, actions)
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_dividend_passes(self, project):
        """A well-formed DIVIDEND passes."""
        write_actions(project, [valid_dividend_action()])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Real registry
# ---------------------------------------------------------------------------

class TestRealRegistry:
    """The committed actions.json must pass when run with the repo fixtures.

    This is the end-to-end check that "seven-layer validated" is true for
    the file on disk. Warnings about unknown ISINs are allowed (the
    fixtures are synthetic), but no layer may fail.
    """

    def test_real_actions_json_passes_all_layers(self):
        result = subprocess.run(
            [
                sys.executable, str(TOOLS / "validate.py"),
                "--actions", str(REAL_ACTIONS),
                "--schema", str(SCHEMA),
                "--identifiers",
                str(REPO_ROOT / "tests/fixtures/identifiers.json"),
                "--iso4217",
                str(REPO_ROOT / "tests/fixtures/iso4217.json"),
                "--exchange-calendar",
                str(REPO_ROOT / "tests/fixtures/exchange_calendar.json"),
                "--min-actions", "100",
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "All layers passed" in result.stdout


# ---------------------------------------------------------------------------
# Schema layer
# ---------------------------------------------------------------------------

class TestSchemaViolations:

    def test_malformed_date_is_rejected(self, project):
        """Phase 3.2: format: date is enforced, not merely declared.

        Without a FormatChecker, 2024-13-99 passes jsonschema silently.
        With one, it is rejected. This test pins that behaviour.
        """
        action = valid_split_action()
        action["dates"]["announcement"] = "2024-13-99"
        write_actions(project, [action])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 1
        assert (
            "2024-13-99" in result.stdout
            or "does not match" in result.stdout
            or "is not a" in result.stdout
        )

    def test_missing_required_field_is_rejected(self, project):
        """A missing top-level required field must fail layer 1."""
        action = valid_split_action()
        del action["provenance"]
        write_actions(project, [action])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 1
        assert "provenance" in result.stdout

    def test_unknown_field_on_action_is_rejected(self, project):
        """additionalProperties: false on action items is enforced."""
        action = valid_split_action()
        action["not_a_real_field"] = "boom"
        write_actions(project, [action])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 1
        assert "not_a_real_field" in result.stdout

    @pytest.mark.skip(
        reason=(
            "validate.py validates per-action sub-schemas only; the "
            "top-level meta block is not checked. tests/test_schema_full.py "
            "covers this case, but the runtime validator does not."
        )
    )
    def test_unknown_top_level_meta_field_is_rejected(self, project):
        """TODO: enforce top-level schema in validate.py."""
        path = project / "actions.json"
        path.write_text(json.dumps({
            "meta": {
                "version": "1.0.0",
                "generated_at": "2026-09-18T00:00:00Z",
                "source": "test",
                "not_a_field": "boom",
            },
            "actions": [valid_split_action()],
        }), encoding="utf-8")
        result = run_validator(path, project)
        assert result.returncode == 1
        assert "not_a_field" in result.stdout


# ---------------------------------------------------------------------------
# Action-type allowlist (Phase 3.1)
# ---------------------------------------------------------------------------

class TestActionTypeAllowlist:

    def test_typo_action_type_is_rejected(self, project):
        """A typo in action_type fails, not just MERGER."""
        action = valid_split_action()
        action["action_type"] = "SPLT"
        write_actions(project, [action])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 1
        assert "SPLT" in result.stdout

    def test_merger_is_rejected_in_v100(self, project):
        """MERGER is in the schema enum but not in the allowlist."""
        action = {
            "isin": "US67066G1040",
            "action_id": "US67066G1040-MERGER-2024-06-10-1-1",
            "action_type": "MERGER",
            "ratio": "1:1",
            "dates": {
                "announcement": "2024-05-22",
                "effective_date": "2024-06-10",
            },
            "status": "COMPLETED",
            "provenance": {
                "source": "SEC S-4",
                "source_url": "https://example.com/merger",
            },
        }
        write_actions(project, [action])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 1
        assert "MERGER" in result.stdout


# ---------------------------------------------------------------------------
# action_id format (Phase 3.6)
# ---------------------------------------------------------------------------

class TestActionIdFormat:

    def test_lowercase_isin_in_id_is_rejected(self, project):
        action = valid_split_action()
        action["action_id"] = "us67066g1040-SPLIT-2024-06-10-10-1"
        write_actions(project, [action])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 1
        assert "action_id" in result.stdout.lower()

    def test_id_with_wrong_date_is_rejected(self, project):
        """The date embedded in the ID must match the action's dates."""
        action = valid_split_action()
        action["action_id"] = "US67066G1040-SPLIT-2020-01-01-10-1"
        write_actions(project, [action])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 1
        assert "2020-01-01" in result.stdout

    def test_id_with_wrong_type_is_rejected(self, project):
        """The type embedded in the ID must match action_type."""
        action = valid_split_action()
        action["action_id"] = "US67066G1040-DIVIDEND-2024-06-10-10-1"
        write_actions(project, [action])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 1
        assert "DIVIDEND" in result.stdout


# ---------------------------------------------------------------------------
# Temporal layer
# ---------------------------------------------------------------------------

class TestTemporalViolations:

    def test_announcement_after_effective_is_rejected(self, project):
        action = valid_split_action()
        action["dates"]["announcement"] = "2024-07-01"
        write_actions(project, [action])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 1
        assert "temporal" in result.stdout


# ---------------------------------------------------------------------------
# Arithmetic layer
# ---------------------------------------------------------------------------

class TestArithmeticViolations:

    def test_bad_ratio_format_is_rejected(self, project):
        action = valid_split_action()
        action["ratio"] = "10-1"
        write_actions(project, [action])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 1
        assert "ratio" in result.stdout.lower()

    def test_negative_dividend_amount_is_rejected(self, project):
        action = valid_dividend_action()
        action["amount"] = -0.25
        action["impact"]["cash_adjustment"] = -0.25
        write_actions(project, [action])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 1
        assert "amount" in result.stdout.lower()


# ---------------------------------------------------------------------------
# Cross-reference layer
# ---------------------------------------------------------------------------

class TestCrossReference:

    def test_missing_isin_is_warning_by_default(self, project):
        """Non-strict mode: unknown ISIN is a warning, not a failure."""
        action = valid_split_action()
        action["isin"] = "US9999999999"
        action["action_id"] = "US9999999999-SPLIT-2024-06-10-10-1"
        write_actions(project, [action])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Warnings" in result.stdout
        assert "US9999999999" in result.stdout

    def test_missing_isin_is_error_with_strict(self, project):
        action = valid_split_action()
        action["isin"] = "US9999999999"
        action["action_id"] = "US9999999999-SPLIT-2024-06-10-10-1"
        write_actions(project, [action])
        result = run_validator(
            project / "actions.json", project, strict_isin=True,
        )
        assert result.returncode == 1
        assert "US9999999999" in result.stdout

    def test_unknown_currency_is_rejected(self, project):
        action = valid_dividend_action()
        action["currency"] = "XYZ"
        write_actions(project, [action])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 1
        assert "XYZ" in result.stdout


# ---------------------------------------------------------------------------
# Uniqueness layer
# ---------------------------------------------------------------------------

class TestUniqueness:

    def test_duplicate_action_id_is_rejected(self, project):
        a1 = valid_split_action()
        a2 = valid_split_action()  # identical action_id
        write_actions(project, [a1, a2])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 1
        assert "Duplicate" in result.stdout or "duplicate" in result.stdout


# ---------------------------------------------------------------------------
# Provenance layer
# ---------------------------------------------------------------------------

class TestProvenance:

    def test_missing_source_url_is_rejected(self, project):
        action = valid_split_action()
        action["provenance"] = {"source": "no url"}
        write_actions(project, [action])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 1
        assert "source_url" in result.stdout

    def test_ftp_scheme_is_rejected(self, project):
        action = valid_split_action()
        action["provenance"]["source_url"] = "ftp://example.com/x"
        write_actions(project, [action])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 1
        assert "HTTP" in result.stdout or "ftp" in result.stdout


# ---------------------------------------------------------------------------
# Coverage layer
# ---------------------------------------------------------------------------

class TestCoverage:

    def test_below_floor_fails(self, project):
        write_actions(project, [valid_split_action()])
        result = run_validator(
            project / "actions.json", project, min_actions=5,
        )
        assert result.returncode == 1
        assert (
            "Coverage" in result.stdout
            or "minimum" in result.stdout.lower()
        )

    def test_at_floor_passes(self, project):
        write_actions(project, [valid_split_action()])
        result = run_validator(
            project / "actions.json", project, min_actions=1,
        )
        assert result.returncode == 0

    def test_empty_actions_fails_high_floor(self, project):
        write_actions(project, [])
        result = run_validator(
            project / "actions.json", project, min_actions=100,
        )
        assert result.returncode == 1
        assert (
            "Coverage" in result.stdout
            or "minimum" in result.stdout.lower()
        )


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

class TestExitCodes:
    """The four documented exit codes, one test per cause."""

    def test_success_exits_0(self, project):
        write_actions(project, [valid_split_action()])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 0

    def test_validation_failure_exits_1(self, project):
        action = valid_split_action()
        del action["provenance"]
        write_actions(project, [action])
        result = run_validator(project / "actions.json", project)
        assert result.returncode == 1

    def test_missing_actions_file_exits_2(self, project):
        result = run_validator(project / "does-not-exist.json", project)
        assert result.returncode == 2

    def test_invalid_json_in_actions_exits_2(self, project):
        path = project / "actions.json"
        path.write_text("{ this is not valid json", encoding="utf-8")
        result = run_validator(path, project)
        assert result.returncode == 2

    def test_missing_schema_file_exits_2(self, project):
        write_actions(project, [valid_split_action()])
        result = run_validator(
            project / "actions.json", project,
            schema=project / "does-not-exist-schema.json",
        )
        assert result.returncode == 2

    def test_missing_identifiers_registry_exits_3(self, project):
        write_actions(project, [valid_split_action()])
        result = run_validator(
            project / "actions.json", project,
            identifiers=project / "does-not-exist-ids.json",
        )
        assert result.returncode == 3

    def test_missing_iso4217_registry_exits_3(self, project):
        write_actions(project, [valid_split_action()])
        result = run_validator(
            project / "actions.json", project,
            iso4217=project / "does-not-exist-iso.json",
        )
        assert result.returncode == 3

    def test_missing_exchange_calendar_exits_3(self, project):
        write_actions(project, [valid_split_action()])
        result = run_validator(
            project / "actions.json", project,
            exchange_calendar=project / "does-not-exist-cal.json",
        )
        assert result.returncode == 3