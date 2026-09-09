"""
Tests for temporal validation in the Corporate Actions Registry.

These tests verify that `validate_temporal` correctly enforces the
per-action-type date ordering rules.

The function under test lives in `tools/validate.py`.
"""

import os
import sys

# Ensure repository root is on sys.path so we can import tools.validate
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.validate import validate_temporal


# ----------------------------------------------------------------------
# Basic checks (all action types)
# ----------------------------------------------------------------------
class TestBasicTemporal:
    def test_missing_announcement(self):
        action = {
            "action_type": "SPLIT",
            "dates": {"effective_date": "2024-06-10"},
        }
        errors = validate_temporal(action)
        assert any("Missing announcement date" in e for e in errors)

    def test_missing_effective_date(self):
        action = {
            "action_type": "SPLIT",
            "dates": {"announcement": "2024-05-22"},
        }
        errors = validate_temporal(action)
        assert any("Missing effective date" in e for e in errors)

    def test_announcement_after_effective(self):
        action = {
            "action_type": "SPLIT",
            "dates": {
                "announcement": "2024-06-10",
                "effective_date": "2024-05-22",
            },
        }
        errors = validate_temporal(action)
        assert any("Announcement date" in e and "after effective date" in e for e in errors)

    def test_announcement_equal_effective_is_ok(self):
        action = {
            "action_type": "SYMBOL_CHANGE",
            "dates": {
                "announcement": "2022-06-09",
                "effective_date": "2022-06-09",
            },
        }
        assert validate_temporal(action) == []


# ----------------------------------------------------------------------
# SPLIT / REVERSE_SPLIT
# ----------------------------------------------------------------------
class TestSplitTemporal:
    def test_valid_split_dates(self):
        action = {
            "action_type": "SPLIT",
            "dates": {
                "announcement": "2024-05-22",
                "ex_date": "2024-06-10",
                "record_date": "2024-06-07",
                "effective_date": "2024-06-10",
            },
        }
        assert validate_temporal(action) == []

    def test_valid_reverse_split_dates(self):
        action = {
            "action_type": "REVERSE_SPLIT",
            "dates": {
                "announcement": "2021-07-30",
                "ex_date": "2021-08-02",
                "record_date": "2021-07-30",
                "effective_date": "2021-08-02",
            },
        }
        assert validate_temporal(action) == []

    def test_split_ex_date_not_equal_effective(self):
        action = {
            "action_type": "SPLIT",
            "dates": {
                "announcement": "2024-05-22",
                "ex_date": "2024-06-10",
                "effective_date": "2024-06-11",
            },
        }
        errors = validate_temporal(action)
        assert any("ex_date" in e and "must equal effective_date" in e for e in errors)

    def test_split_record_after_ex_date(self):
        action = {
            "action_type": "SPLIT",
            "dates": {
                "announcement": "2024-05-22",
                "ex_date": "2024-06-10",
                "record_date": "2024-06-11",
                "effective_date": "2024-06-10",
            },
        }
        errors = validate_temporal(action)
        assert any("record_date" in e and "after ex_date" in e for e in errors)

    def test_split_announcement_after_ex_date(self):
        action = {
            "action_type": "REVERSE_SPLIT",
            "dates": {
                "announcement": "2021-08-03",
                "ex_date": "2021-08-02",
                "effective_date": "2021-08-02",
            },
        }
        errors = validate_temporal(action)
        assert any("Announcement" in e and "after ex_date" in e for e in errors)

    def test_split_missing_ex_date_is_ok(self):
        # ex_date optional; if missing, only basic checks apply.
        action = {
            "action_type": "SPLIT",
            "dates": {
                "announcement": "2024-05-22",
                "effective_date": "2024-06-10",
            },
        }
        assert validate_temporal(action) == []

    def test_split_record_date_without_ex_date_is_ok(self):
        action = {
            "action_type": "SPLIT",
            "dates": {
                "announcement": "2024-05-22",
                "record_date": "2024-06-07",
                "effective_date": "2024-06-10",
            },
        }
        # record_date only checked if ex_date present
        assert validate_temporal(action) == []


# ----------------------------------------------------------------------
# DIVIDEND / SPECIAL_DIVIDEND
# ----------------------------------------------------------------------
class TestDividendTemporal:
    def test_valid_dividend_dates(self):
        action = {
            "action_type": "DIVIDEND",
            "dates": {
                "announcement": "2024-05-02",
                "ex_date": "2024-05-16",
                "record_date": "2024-05-17",
                "effective_date": "2024-05-23",
            },
        }
        assert validate_temporal(action) == []

    def test_valid_special_dividend_dates(self):
        action = {
            "action_type": "SPECIAL_DIVIDEND",
            "dates": {
                "announcement": "2004-11-15",
                "ex_date": "2004-11-17",
                "record_date": "2004-11-19",
                "effective_date": "2004-12-03",
            },
        }
        assert validate_temporal(action) == []

    def test_dividend_ex_date_not_before_record(self):
        action = {
            "action_type": "DIVIDEND",
            "dates": {
                "announcement": "2024-05-02",
                "ex_date": "2024-05-17",
                "record_date": "2024-05-16",
                "effective_date": "2024-05-23",
            },
        }
        errors = validate_temporal(action)
        assert any("ex_date" in e and "must be before record_date" in e for e in errors)

    def test_dividend_record_after_effective(self):
        action = {
            "action_type": "DIVIDEND",
            "dates": {
                "announcement": "2024-05-02",
                "ex_date": "2024-05-16",
                "record_date": "2024-05-24",
                "effective_date": "2024-05-23",
            },
        }
        errors = validate_temporal(action)
        assert any("record_date" in e and "after effective_date" in e for e in errors)

    def test_dividend_announcement_after_ex_date(self):
        action = {
            "action_type": "DIVIDEND",
            "dates": {
                "announcement": "2024-05-20",
                "ex_date": "2024-05-16",
                "record_date": "2024-05-17",
                "effective_date": "2024-05-23",
            },
        }
        errors = validate_temporal(action)
        assert any("Announcement" in e and "after ex_date" in e for e in errors)

    def test_dividend_missing_record_date_is_ok(self):
        action = {
            "action_type": "DIVIDEND",
            "dates": {
                "announcement": "2024-05-02",
                "ex_date": "2024-05-16",
                "effective_date": "2024-05-23",
            },
        }
        assert validate_temporal(action) == []

    def test_dividend_missing_ex_date_is_ok(self):
        action = {
            "action_type": "DIVIDEND",
            "dates": {
                "announcement": "2024-05-02",
                "record_date": "2024-05-17",
                "effective_date": "2024-05-23",
            },
        }
        assert validate_temporal(action) == []

    def test_dividend_ex_date_equal_record_date_invalid(self):
        action = {
            "action_type": "DIVIDEND",
            "dates": {
                "announcement": "2024-05-02",
                "ex_date": "2024-05-17",
                "record_date": "2024-05-17",
                "effective_date": "2024-05-23",
            },
        }
        errors = validate_temporal(action)
        assert any("ex_date" in e and "must be before record_date" in e for e in errors)


# ----------------------------------------------------------------------
# SYMBOL_CHANGE
# ----------------------------------------------------------------------
class TestSymbolChangeTemporal:
    def test_valid_symbol_change(self):
        action = {
            "action_type": "SYMBOL_CHANGE",
            "dates": {
                "announcement": "2022-06-09",
                "effective_date": "2022-06-09",
            },
        }
        assert validate_temporal(action) == []

    def test_symbol_change_announcement_before_effective(self):
        action = {
            "action_type": "SYMBOL_CHANGE",
            "dates": {
                "announcement": "2022-06-01",
                "effective_date": "2022-06-09",
            },
        }
        assert validate_temporal(action) == []

    def test_symbol_change_ignores_ex_and_record(self):
        # Even if ex_date/record_date present, should not be checked.
        action = {
            "action_type": "SYMBOL_CHANGE",
            "dates": {
                "announcement": "2022-06-09",
                "ex_date": "2021-01-01",
                "record_date": "2020-01-01",
                "effective_date": "2022-06-09",
            },
        }
        assert validate_temporal(action) == []


# ----------------------------------------------------------------------
# SPINOFF
# ----------------------------------------------------------------------
class TestSpinoffTemporal:
    def test_valid_spinoff(self):
        action = {
            "action_type": "SPINOFF",
            "dates": {
                "announcement": "2023-01-04",
                "ex_date": "2023-01-04",
                "effective_date": "2023-01-04",
            },
        }
        assert validate_temporal(action) == []

    def test_spinoff_ex_date_not_equal_effective(self):
        action = {
            "action_type": "SPINOFF",
            "dates": {
                "announcement": "2023-01-04",
                "ex_date": "2023-01-05",
                "effective_date": "2023-01-04",
            },
        }
        errors = validate_temporal(action)
        assert any("ex_date" in e and "must equal effective_date" in e for e in errors)

    def test_spinoff_announcement_after_ex_date(self):
        action = {
            "action_type": "SPINOFF",
            "dates": {
                "announcement": "2023-01-10",
                "ex_date": "2023-01-04",
                "effective_date": "2023-01-04",
            },
        }
        errors = validate_temporal(action)
        assert any("Announcement" in e and "after ex_date" in e for e in errors)

    def test_spinoff_no_record_rule(self):
        # record_date ignored even if present
        action = {
            "action_type": "SPINOFF",
            "dates": {
                "announcement": "2023-01-04",
                "ex_date": "2023-01-04",
                "record_date": "2023-06-01",
                "effective_date": "2023-01-04",
            },
        }
        assert validate_temporal(action) == []


# ----------------------------------------------------------------------
# DELISTING
# ----------------------------------------------------------------------
class TestDelistingTemporal:
    def test_valid_delisting(self):
        action = {
            "action_type": "DELISTING",
            "dates": {
                "announcement": "2022-10-27",
                "effective_date": "2022-10-28",
            },
        }
        assert validate_temporal(action) == []

    def test_delisting_with_ex_date_invalid(self):
        action = {
            "action_type": "DELISTING",
            "dates": {
                "announcement": "2022-10-27",
                "ex_date": "2022-10-28",
                "effective_date": "2022-10-28",
            },
        }
        errors = validate_temporal(action)
        assert any("DELISTING should not have ex_date" in e for e in errors)

    def test_delisting_with_record_date_invalid(self):
        action = {
            "action_type": "DELISTING",
            "dates": {
                "announcement": "2022-10-27",
                "record_date": "2022-10-28",
                "effective_date": "2022-10-28",
            },
        }
        errors = validate_temporal(action)
        assert any("DELISTING should not have record_date" in e for e in errors)

    def test_delisting_with_both_ex_and_record_invalid(self):
        action = {
            "action_type": "DELISTING",
            "dates": {
                "announcement": "2022-10-27",
                "ex_date": "2022-10-28",
                "record_date": "2022-10-28",
                "effective_date": "2022-10-28",
            },
        }
        errors = validate_temporal(action)
        assert len(errors) == 2
        assert any("ex_date" in e for e in errors)
        assert any("record_date" in e for e in errors)


# ----------------------------------------------------------------------
# MERGER (placeholder)
# ----------------------------------------------------------------------
class TestMergerTemporal:
    def test_valid_merger_basic(self):
        action = {
            "action_type": "MERGER",
            "dates": {
                "announcement": "2024-01-01",
                "effective_date": "2024-02-01",
            },
        }
        assert validate_temporal(action) == []

    def test_merger_announcement_after_effective(self):
        action = {
            "action_type": "MERGER",
            "dates": {
                "announcement": "2024-02-01",
                "effective_date": "2024-01-01",
            },
        }
        errors = validate_temporal(action)
        assert any("Announcement date" in e and "after effective date" in e for e in errors)

    def test_merger_ignores_ex_record(self):
        action = {
            "action_type": "MERGER",
            "dates": {
                "announcement": "2024-01-01",
                "ex_date": "2024-01-15",
                "record_date": "2024-01-20",
                "effective_date": "2024-02-01",
            },
        }
        # No additional checks, so should pass if basic ordering valid.
        assert validate_temporal(action) == []


# ----------------------------------------------------------------------
# Edge cases and robustness
# ----------------------------------------------------------------------
class TestEdgeCases:
    def test_no_dates_key(self):
        action = {"action_type": "SPLIT"}
        errors = validate_temporal(action)
        assert any("Missing announcement date" in e for e in errors)
        assert any("Missing effective date" in e for e in errors)

    def test_dates_is_none(self):
        action = {"action_type": "SPLIT", "dates": None}
        errors = validate_temporal(action)
        assert any("Missing announcement date" in e for e in errors)
        assert any("Missing effective date" in e for e in errors)

    def test_dates_empty_dict(self):
        action = {"action_type": "SPLIT", "dates": {}}
        errors = validate_temporal(action)
        assert any("Missing announcement date" in e for e in errors)
        assert any("Missing effective date" in e for e in errors)

    def test_all_dates_same_valid_for_split(self):
        action = {
            "action_type": "SPLIT",
            "dates": {
                "announcement": "2024-01-01",
                "ex_date": "2024-01-01",
                "record_date": "2024-01-01",
                "effective_date": "2024-01-01",
            },
        }
        # ex_date == effective, record_date <= ex_date (equal is allowed)
        assert validate_temporal(action) == []

    def test_all_dates_same_valid_for_symbol_change(self):
        action = {
            "action_type": "SYMBOL_CHANGE",
            "dates": {
                "announcement": "2024-01-01",
                "ex_date": "2024-01-01",
                "record_date": "2024-01-01",
                "effective_date": "2024-01-01",
            },
        }
        assert validate_temporal(action) == []