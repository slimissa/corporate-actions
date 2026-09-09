"""
Tests for cross-reference validation in the Corporate Actions Registry.

These tests verify that `validate_cross_reference` correctly checks:
- ISIN exists in the Asset Identifiers registry
- Currency is an active ISO 4217 code
- Exchange MIC (if provided) exists in Exchange Calendar
- Missing optional fields do not cause errors
- Multiple errors are aggregated

The function under test lives in `tools/validate.py`.
"""

import os
import sys
import pytest

# Ensure repository root is on sys.path so we can import tools.validate
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.validate import validate_cross_reference


# Fixtures for common sets
@pytest.fixture
def isin_set():
    return {"US0378331005", "US67066G1040", "US5949181045"}

@pytest.fixture
def currency_set():
    return {"USD", "EUR", "JPY"}

@pytest.fixture
def mic_set():
    return {"XNAS", "XNYS", "XLON"}


class TestISINCrossReference:
    def test_isin_found(self, isin_set, currency_set, mic_set):
        action = {"isin": "US0378331005"}
        assert validate_cross_reference(action, isin_set, currency_set, mic_set) == []

    def test_isin_not_found(self, isin_set, currency_set, mic_set):
        action = {"isin": "US9999999999"}
        errors = validate_cross_reference(action, isin_set, currency_set, mic_set)
        assert any("ISIN not found" in e for e in errors)

    def test_isin_missing(self, isin_set, currency_set, mic_set):
        action = {}
        assert validate_cross_reference(action, isin_set, currency_set, mic_set) == []

    def test_isin_none(self, isin_set, currency_set, mic_set):
        action = {"isin": None}
        assert validate_cross_reference(action, isin_set, currency_set, mic_set) == []


class TestCurrencyCrossReference:
    def test_currency_found(self, isin_set, currency_set, mic_set):
        action = {"currency": "USD"}
        assert validate_cross_reference(action, isin_set, currency_set, mic_set) == []

    def test_currency_not_found(self, isin_set, currency_set, mic_set):
        action = {"currency": "GBP"}
        errors = validate_cross_reference(action, isin_set, currency_set, mic_set)
        assert any("Currency not an active ISO 4217 code" in e for e in errors)

    def test_currency_missing(self, isin_set, currency_set, mic_set):
        action = {}
        assert validate_cross_reference(action, isin_set, currency_set, mic_set) == []

    def test_currency_none(self, isin_set, currency_set, mic_set):
        action = {"currency": None}
        assert validate_cross_reference(action, isin_set, currency_set, mic_set) == []


class TestExchangeCrossReference:
    def test_exchange_found(self, isin_set, currency_set, mic_set):
        action = {"exchange": "XNAS"}
        assert validate_cross_reference(action, isin_set, currency_set, mic_set) == []

    def test_exchange_not_found(self, isin_set, currency_set, mic_set):
        action = {"exchange": "XKRX"}
        errors = validate_cross_reference(action, isin_set, currency_set, mic_set)
        assert any("Exchange MIC not found" in e for e in errors)

    def test_exchange_missing(self, isin_set, currency_set, mic_set):
        action = {}
        assert validate_cross_reference(action, isin_set, currency_set, mic_set) == []

    def test_exchange_none(self, isin_set, currency_set, mic_set):
        action = {"exchange": None}
        assert validate_cross_reference(action, isin_set, currency_set, mic_set) == []


class TestMultipleErrors:
    def test_all_invalid(self, isin_set, currency_set, mic_set):
        action = {"isin": "US1111111111", "currency": "XYZ", "exchange": "XXXX"}
        errors = validate_cross_reference(action, isin_set, currency_set, mic_set)
        assert len(errors) == 3
        assert any("ISIN not found" in e for e in errors)
        assert any("Currency not an active ISO 4217 code" in e for e in errors)
        assert any("Exchange MIC not found" in e for e in errors)

    def test_two_invalid_one_valid(self, isin_set, currency_set, mic_set):
        action = {"isin": "US67066G1040", "currency": "XYZ", "exchange": "XNAS"}
        errors = validate_cross_reference(action, isin_set, currency_set, mic_set)
        assert len(errors) == 1
        assert any("Currency not an active ISO 4217 code" in e for e in errors)


class TestEmptySets:
    def test_empty_isin_set(self, currency_set, mic_set):
        action = {"isin": "US0378331005"}
        errors = validate_cross_reference(action, set(), currency_set, mic_set)
        assert any("ISIN not found" in e for e in errors)

    def test_empty_currency_set(self, isin_set, mic_set):
        action = {"currency": "USD"}
        errors = validate_cross_reference(action, isin_set, set(), mic_set)
        assert any("Currency not an active ISO 4217 code" in e for e in errors)

    def test_empty_mic_set(self, isin_set, currency_set):
        action = {"exchange": "XNAS"}
        errors = validate_cross_reference(action, isin_set, currency_set, set())
        assert any("Exchange MIC not found" in e for e in errors)