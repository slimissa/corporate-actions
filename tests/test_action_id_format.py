"""
Tests for validate_action_id_format in tools/validate.py.

The function checks three things about an action's action_id:

1. Shape. The ID must match
       {isin}-{TYPE}-{effective_date}-{discriminator}
   where the ISIN is uppercase, the type is one of the eight known
   action types, the date is YYYY-MM-DD, and the discriminator is any
   non-empty suffix.

2. Internal consistency. The isin, action type, and date embedded in
   the ID must match the action's own isin, action_type, and
   dates.effective_date fields. Mismatches are the class of bug that
   silent ID-mutation (an edit, a merge, a hand fix) produces: the ID
   looks fine in isolation but lies about the data it labels.

3. Silence on missing input. If action_id is missing or empty, the
   function returns an empty list. The schema layer catches missing
   fields; this layer is a format check, not an existence check.

The function takes the whole action dict, not just the ID, because the
consistency checks need the surrounding fields.

Run
---
    python -m pytest tests/test_action_id_format.py -v
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.validate import validate_action_id_format


# ---------------------------------------------------------------------------
# Sanity
# ---------------------------------------------------------------------------

def test_function_is_importable():
    """Guard against accidental removal or rename."""
    assert callable(validate_action_id_format)


# ---------------------------------------------------------------------------
# Valid shape
# ---------------------------------------------------------------------------

class TestValidShape:
    """IDs that match the canonical shape and carry no surrounding fields.

    With no isin, action_type, or dates on the action, the consistency
    checks are skipped and only the regex runs. Every ID here must
    produce zero errors.
    """

    @pytest.mark.parametrize("action_id", [
        # Semantic discriminators
        "US67066G1040-SPLIT-2024-06-10-10-1",
        "US67066G1040-SPLIT-2024-06-10-4-1",
        "US67066G1040-REVERSE_SPLIT-2021-08-02-1-8",
        "US0378331005-DIVIDEND-2024-05-16-0.2500",
        "US0378331005-SPECIAL_DIVIDEND-2024-05-16-3.0000",
        "US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL",
        "US90184L1026-DELISTING-2022-10-28-DELISTED",
        "US3696041033-SPINOFF-2023-01-04-1-3",
        "US67066G1040-MERGER-2024-06-10-1-1",
        # Other ISIN country codes
        "GB0007099541-DIVIDEND-2020-03-12-0.2500",
        "JP3633400001-SPLIT-2021-09-30-3-1",
        # All digits in the ISIN's 9-char body
        "US1234567890-SPLIT-2024-06-10-10-1",
        # Single-character discriminator
        "US67066G1040-SPLIT-2024-06-10-X",
        # Long discriminator
        "US67066G1040-SPLIT-2024-06-10-a-very-long-discriminator-here",
    ])
    def test_accepts(self, action_id):
        errors = validate_action_id_format({"action_id": action_id})
        assert errors == [], f"unexpected errors for {action_id!r}: {errors}"


# ---------------------------------------------------------------------------
# Invalid shape
# ---------------------------------------------------------------------------

class TestShapeRejections:
    """IDs that do not match the canonical shape.

    Every case here has no surrounding fields on the action, so the only
    possible source of error is the regex.
    """

    @pytest.mark.parametrize("action_id", [
        # Missing or malformed ISIN
        "US67066G104-SPLIT-2024-06-10-10-1",             # ISIN too short
        "US67066G10400-SPLIT-2024-06-10-10-1",           # ISIN too long
        "us67066g1040-SPLIT-2024-06-10-10-1",            # lowercase ISIN
        "Us67066G1040-SPLIT-2024-06-10-10-1",            # mixed case
        "1S67066G1040-SPLIT-2024-06-10-10-1",            # ISIN starts with digit
        "US67066G104X-SPLIT-2024-06-10-10-1",            # ISIN does not end with digit

        # Missing or malformed type
        "US67066G1040-split-2024-06-10-10-1",            # lowercase type
        "US67066G1040-SPLT-2024-06-10-10-1",             # typo'd type
        "US67066G1040-NOT_A_TYPE-2024-06-10-10-1",       # unknown type
        "US67066G1040-SPLITDIVIDEND-2024-06-10-10-1",    # concatenated types
        "US67066G1040--2024-06-10-10-1",                 # empty type

        # Missing or malformed date
        "US67066G1040-SPLIT-20240610-10-1",              # no date separators
        "US67066G1040-SPLIT-2024-6-10-10-1",             # single-digit month
        "US67066G1040-SPLIT-2024-06-1-10-1",             # single-digit day
        "US67066G1040-SPLIT-2024/06/10-10-1",            # slashes
        "US67066G1040-SPLIT-24-06-10-10-1",              # two-digit year
        "US67066G1040-SPLIT--10-1",                      # empty date

        # Missing or empty discriminator
        "US67066G1040-SPLIT-2024-06-10",                 # no discriminator
        "US67066G1040-SPLIT-2024-06-10-",                # empty discriminator

        # Missing separators
        "US67066G1040SPLIT2024061010-1",                 # no dashes at all
        "US67066G1040_SPLIT_2024-06-10_10-1",            # underscores
        "US67066G1040 SPLIT 2024-06-10 10-1",            # spaces

        # Not even close
        "not-an-id",
        "hello world",
        "US67066G1040",
    ])
    def test_rejects(self, action_id):
        errors = validate_action_id_format({"action_id": action_id})
        assert errors, f"expected rejection for {action_id!r}"
        # Every shape rejection must produce exactly one error, the shape one.
        # No consistency check runs when the shape does not match.
        assert len(errors) == 1, f"expected 1 error, got {len(errors)}: {errors}"
        assert "canonical" in errors[0].lower() or "does not match" in errors[0]


# ---------------------------------------------------------------------------
# Consistency: isin
# ---------------------------------------------------------------------------

class TestIsinConsistency:

    def test_matching_isin_passes(self):
        errors = validate_action_id_format({
            "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
            "isin": "US67066G1040",
        })
        assert errors == []

    def test_mismatched_isin_fails(self):
        errors = validate_action_id_format({
            "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
            "isin": "US0378331005",
        })
        assert any("isin" in e for e in errors)
        assert any("US67066G1040" in e for e in errors)
        assert any("US0378331005" in e for e in errors)

    def test_missing_isin_on_action_skips_check(self):
        """If the action has no isin, the consistency check does not fire.

        The schema requires isin, so this is a defensive branch, not a
        supported use case.
        """
        errors = validate_action_id_format({
            "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
        })
        assert errors == []

    def test_empty_isin_on_action_skips_check(self):
        errors = validate_action_id_format({
            "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
            "isin": "",
        })
        assert errors == []


# ---------------------------------------------------------------------------
# Consistency: action_type
# ---------------------------------------------------------------------------

class TestActionTypeConsistency:

    def test_matching_type_passes(self):
        errors = validate_action_id_format({
            "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
            "action_type": "SPLIT",
        })
        assert errors == []

    def test_mismatched_type_fails(self):
        errors = validate_action_id_format({
            "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
            "action_type": "DIVIDEND",
        })
        assert any("type" in e.lower() for e in errors)
        assert any("SPLIT" in e for e in errors)
        assert any("DIVIDEND" in e for e in errors)

    def test_missing_type_on_action_skips_check(self):
        errors = validate_action_id_format({
            "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
        })
        assert errors == []


# ---------------------------------------------------------------------------
# Consistency: dates.effective_date
# ---------------------------------------------------------------------------

class TestDateConsistency:

    def test_matching_date_passes(self):
        errors = validate_action_id_format({
            "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
            "dates": {"effective_date": "2024-06-10"},
        })
        assert errors == []

    def test_mismatched_date_fails(self):
        errors = validate_action_id_format({
            "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
            "dates": {"effective_date": "2020-01-01"},
        })
        assert any("date" in e.lower() for e in errors)
        assert any("2024-06-10" in e for e in errors)
        assert any("2020-01-01" in e for e in errors)

    def test_missing_dates_skips_check(self):
        errors = validate_action_id_format({
            "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
        })
        assert errors == []

    def test_missing_effective_date_skips_check(self):
        errors = validate_action_id_format({
            "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
            "dates": {"announcement": "2024-05-22"},
        })
        assert errors == []

    def test_dates_is_none_skips_check(self):
        errors = validate_action_id_format({
            "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
            "dates": None,
        })
        assert errors == []


# ---------------------------------------------------------------------------
# Multiple errors
# ---------------------------------------------------------------------------

class TestMultipleErrors:

    def test_all_three_mismatches_produce_three_errors(self):
        """A wholly inconsistent ID yields one error per check."""
        errors = validate_action_id_format({
            "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
            "isin": "US0378331005",
            "action_type": "DIVIDEND",
            "dates": {"effective_date": "2020-01-01"},
        })
        assert len(errors) == 3, errors

    def test_shape_failure_suppresses_consistency_checks(self):
        """If the shape does not match, no consistency check runs.

        The regex cannot extract the parts, so the function returns early.
        """
        errors = validate_action_id_format({
            "action_id": "not-an-id",
            "isin": "US0378331005",
            "action_type": "DIVIDEND",
            "dates": {"effective_date": "2020-01-01"},
        })
        assert len(errors) == 1
        assert "canonical" in errors[0].lower() or "does not match" in errors[0]


# ---------------------------------------------------------------------------
# Missing action_id
# ---------------------------------------------------------------------------

class TestMissingActionId:

    def test_missing_key_returns_empty(self):
        assert validate_action_id_format({}) == []

    def test_none_returns_empty(self):
        assert validate_action_id_format({"action_id": None}) == []

    def test_empty_string_returns_empty(self):
        assert validate_action_id_format({"action_id": ""}) == []

    def test_missing_id_does_not_mask_other_fields(self):
        """With no id, no error is produced even if other fields are odd."""
        assert validate_action_id_format({
            "isin": "not-an-isin",
            "action_type": "NOT_A_TYPE",
        }) == []


# ---------------------------------------------------------------------------
# Discriminator flexibility
# ---------------------------------------------------------------------------

class TestDiscriminatorIsFreeForm:
    """The discriminator is `.+` — the function does not check its content.

    That is deliberate: the discriminator encodes action-specific
    meaning (a ratio, an amount, a keyword). The function checks the
    shape of the surrounding ID, not the semantics of the suffix.
    """

    @pytest.mark.parametrize("disc", [
        "10-1",
        "4-1",
        "1-8",
        "0.2500",
        "3.0000",
        "0001",
        "0002",
        "SYMBOL",
        "DELISTED",
        "x",
        "a" * 200,
        "with spaces in it",
        "with-punctuation.!?",
        "10:1",  # a raw ratio with a colon; still valid as a suffix
    ])
    def test_accepts_any_discriminator(self, disc):
        action_id = f"US67066G1040-SPLIT-2024-06-10-{disc}"
        errors = validate_action_id_format({"action_id": action_id})
        assert errors == [], errors


# ---------------------------------------------------------------------------
# Real registry
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_actions():
    """The committed actions.json's action list, loaded once per session."""
    path = REPO_ROOT / "actions.json"
    return json.loads(path.read_text(encoding="utf-8"))["actions"]


class TestRealRegistry:
    """The committed actions.json must not produce a single ID-format error.

    After Phase 1 canonicalized every ID, this is the end-to-end guard:
    if a future edit introduces a malformed ID, this test fails before
    the file is ever committed.
    """

    def test_every_id_passes(self, real_actions):
        failures = []
        for action in real_actions:
            errors = validate_action_id_format(action)
            if errors:
                failures.append((action.get("action_id"), errors))
        assert not failures, (
            f"{len(failures)} action(s) have malformed action_id:\n"
            + "\n".join(f"  {aid}: {errs}" for aid, errs in failures[:10])
        )

    def test_at_least_one_action_exists(self, real_actions):
        """Guard against the file being emptied and the previous test
        vacuously passing."""
        assert len(real_actions) > 0

class TestDiscriminatorConsistency:
    """The discriminator suffix must match the action's fields.

    These tests pin the behavior that validate_action_id_format now
    enforces: the suffix after the effective_date is derived from the
    action, not free-form.
    """

    def test_split_correct_discriminator_passes(self):
        assert validate_action_id_format({
            "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
            "action_type": "SPLIT",
            "ratio": "10:1",
        }) == []

    def test_split_wrong_discriminator_rejected(self):
        errors = validate_action_id_format({
            "action_id": "US67066G1040-SPLIT-2024-06-10-999-999",
            "action_type": "SPLIT",
            "ratio": "10:1",
        })
        assert any("discriminator" in e for e in errors), errors

    def test_split_colon_form_rejected(self):
        errors = validate_action_id_format({
            "action_id": "US67066G1040-SPLIT-2024-06-10-10:1",
            "action_type": "SPLIT",
            "ratio": "10:1",
        })
        assert any("discriminator" in e for e in errors), errors

    def test_dividend_correct_discriminator_passes(self):
        assert validate_action_id_format({
            "action_id": "US0378331005-DIVIDEND-2024-05-16-0.2500",
            "action_type": "DIVIDEND",
            "amount": 0.25,
        }) == []

    def test_dividend_wrong_discriminator_rejected(self):
        errors = validate_action_id_format({
            "action_id": "US0378331005-DIVIDEND-2024-05-16-9999",
            "action_type": "DIVIDEND",
            "amount": 0.25,
        })
        assert any("discriminator" in e for e in errors), errors

    def test_symbol_change_must_use_symbol(self):
        errors = validate_action_id_format({
            "action_id": "US30303M1027-SYMBOL_CHANGE-2022-06-09-META",
            "action_type": "SYMBOL_CHANGE",
        })
        assert any("SYMBOL" in e for e in errors), errors

    def test_symbol_change_correct_form_passes(self):
        assert validate_action_id_format({
            "action_id": "US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL",
            "action_type": "SYMBOL_CHANGE",
        }) == []

    def test_delisting_must_use_delisted(self):
        errors = validate_action_id_format({
            "action_id": "US90184L1026-DELISTING-2022-10-28-WRONG",
            "action_type": "DELISTING",
        })
        assert any("DELISTED" in e for e in errors), errors

    def test_delisting_correct_form_passes(self):
        assert validate_action_id_format({
            "action_id": "US90184L1026-DELISTING-2022-10-28-DELISTED",
            "action_type": "DELISTING",
        }) == []