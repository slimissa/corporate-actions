"""
Tests for arithmetic validation in the Corporate Actions Registry.

These tests verify that `validate_arithmetic` correctly validates:
- Split/reverse split ratios (must be "N:M" with positive integers)
- Dividend amounts (must be positive numbers)
- Missing ratio/amount for applicable action types
- That non-applicable action types are ignored

The function under test lives in `tools/validate.py`.
"""

import os
import sys

# Ensure repository root is on sys.path so we can import tools.validate
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.validate import validate_arithmetic


class TestSplitRatioValidation:
    def test_valid_forward_split_ratio(self):
        action = {"action_type": "SPLIT", "ratio": "10:1"}
        assert validate_arithmetic(action) == []

    def test_valid_reverse_split_ratio(self):
        action = {"action_type": "REVERSE_SPLIT", "ratio": "1:8"}
        assert validate_arithmetic(action) == []

    def test_ratio_with_spaces_is_invalid(self):
        action = {"action_type": "SPLIT", "ratio": "10 : 1"}
        assert validate_arithmetic(action) != []

    def test_ratio_with_slash_is_invalid(self):
        action = {"action_type": "SPLIT", "ratio": "10/1"}
        assert validate_arithmetic(action) != []

    def test_missing_ratio_for_split(self):
        action = {"action_type": "SPLIT"}
        errors = validate_arithmetic(action)
        assert any("requires ratio" in e for e in errors)

    def test_ratio_with_zero_part(self):
        action = {"action_type": "SPLIT", "ratio": "0:1"}
        assert validate_arithmetic(action) != []

    def test_ratio_with_negative_part(self):
        action = {"action_type": "REVERSE_SPLIT", "ratio": "-1:2"}
        assert validate_arithmetic(action) != []

    def test_ratio_with_non_integer_part(self):
        action = {"action_type": "SPLIT", "ratio": "a:b"}
        assert validate_arithmetic(action) != []

    def test_ratio_with_missing_denominator(self):
        action = {"action_type": "SPLIT", "ratio": "10:"}
        assert validate_arithmetic(action) != []

    def test_ratio_with_missing_numerator(self):
        action = {"action_type": "SPLIT", "ratio": ":1"}
        assert validate_arithmetic(action) != []


class TestDividendAmountValidation:
    def test_valid_cash_dividend(self):
        action = {"action_type": "DIVIDEND", "amount": 0.25}
        assert validate_arithmetic(action) == []

    def test_valid_special_dividend(self):
        action = {"action_type": "SPECIAL_DIVIDEND", "amount": 3.0}
        assert validate_arithmetic(action) == []

    def test_missing_amount_for_dividend(self):
        action = {"action_type": "DIVIDEND"}
        errors = validate_arithmetic(action)
        assert any("requires amount" in e for e in errors)

    def test_zero_amount_for_dividend(self):
        action = {"action_type": "DIVIDEND", "amount": 0}
        assert validate_arithmetic(action) != []

    def test_negative_amount_for_dividend(self):
        action = {"action_type": "SPECIAL_DIVIDEND", "amount": -0.5}
        assert validate_arithmetic(action) != []

    def test_non_numeric_amount_for_dividend(self):
        action = {"action_type": "DIVIDEND", "amount": "lots"}
        assert validate_arithmetic(action) != []


class TestNonApplicableActionTypes:
    def test_symbol_change_ignored(self):
        action = {"action_type": "SYMBOL_CHANGE", "ratio": "invalid", "amount": -5}
        assert validate_arithmetic(action) == []

    def test_delisting_ignored(self):
        action = {"action_type": "DELISTING"}
        assert validate_arithmetic(action) == []

    def test_spinoff_ignored(self):
        action = {"action_type": "SPINOFF", "ratio": "bad:ratio"}
        assert validate_arithmetic(action) == []

    def test_unknown_action_type_ignored(self):
        action = {"action_type": "UNKNOWN_TYPE", "ratio": "1:2", "amount": 5}
        assert validate_arithmetic(action) == []