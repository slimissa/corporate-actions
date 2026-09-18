"""
Tests for the ticker → ISIN index functions in tools/validate.py.

Covers:

  - ``build_ticker_isin_index()`` — pure transformation
  - ``load_ticker_isin_index()`` — file loading, structure variations,
    env var precedence, error handling
  - Integration with the real Asset Identifiers registry, when available

Tests use ``tmp_path`` and ``monkeypatch`` from pytest. No external
dependencies beyond ``pytest``.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.validate import (
    build_ticker_isin_index,
    load_ticker_isin_index,
    RegistryLoadError,
)


# ----------------------------------------------------------------------
# Helpers and fixtures
# ----------------------------------------------------------------------

def make_instrument(
    ticker=None,
    exchange=None,
    isin=None,
    **extras,
) -> Dict[str, Any]:
    """
    Build an instrument dict with only the keys that are provided.
    Passing ``None`` for a field omits the key entirely, which mirrors
    how real registries sometimes have entries that are missing fields.
    """
    inst: Dict[str, Any] = {}
    if ticker is not None:
        inst["ticker"] = ticker
    if exchange is not None:
        inst["exchange"] = exchange
    if isin is not None:
        inst["isin"] = isin
    inst.update(extras)
    return inst


def write_registry(
    tmp_path: Path,
    data: Dict[str, Any],
    name: str = "identifiers.json",
) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


@pytest.fixture
def clean_env(monkeypatch):
    """Remove identifier-related environment variables for hermetic tests."""
    for var in ("CORP_ACTIONS_IDENTIFIERS_PATH", "LAS_DATA_HOME"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def real_registry_path():
    """
    Return the path to the real Asset Identifiers registry, or skip the
    test if it is not available. Reads ``$LAS_DATA_HOME/identifiers.json``.
    """
    las_home = os.environ.get("LAS_DATA_HOME")
    if not las_home:
        pytest.skip("LAS_DATA_HOME not set")
    candidate = os.path.join(las_home, "identifiers.json")
    if not os.path.isfile(candidate):
        pytest.skip(f"Real registry not found at {candidate}")
    return candidate


# ----------------------------------------------------------------------
# build_ticker_isin_index — pure transformation
# ----------------------------------------------------------------------

class TestBuildTickerIsinIndex:
    def test_empty_list_returns_empty_dict(self):
        assert build_ticker_isin_index([]) == {}

    def test_single_instrument(self):
        instruments = [make_instrument("AAPL", "XNAS", "US0378331005")]
        idx = build_ticker_isin_index(instruments)
        assert idx == {("AAPL", "XNAS"): "US0378331005"}

    def test_multiple_instruments(self):
        instruments = [
            make_instrument("AAPL", "XNAS", "US0378331005"),
            make_instrument("MSFT", "XNAS", "US5949181045"),
            make_instrument("JPM", "XNYS", "US46647PAK91"),
        ]
        idx = build_ticker_isin_index(instruments)
        assert len(idx) == 3
        assert idx[("AAPL", "XNAS")] == "US0378331005"
        assert idx[("MSFT", "XNAS")] == "US5949181045"
        assert idx[("JPM", "XNYS")] == "US46647PAK91"

    def test_missing_ticker_skipped(self):
        instruments = [
            make_instrument(None, "XNAS", "US0378331005"),
            make_instrument("MSFT", "XNAS", "US5949181045"),
        ]
        idx = build_ticker_isin_index(instruments)
        assert idx == {("MSFT", "XNAS"): "US5949181045"}

    def test_missing_exchange_skipped(self):
        instruments = [
            make_instrument("AAPL", None, "US0378331005"),
            make_instrument("MSFT", "XNAS", "US5949181045"),
        ]
        idx = build_ticker_isin_index(instruments)
        assert idx == {("MSFT", "XNAS"): "US5949181045"}

    def test_missing_isin_skipped(self):
        instruments = [
            make_instrument("AAPL", "XNAS", None),
            make_instrument("MSFT", "XNAS", "US5949181045"),
        ]
        idx = build_ticker_isin_index(instruments)
        assert idx == {("MSFT", "XNAS"): "US5949181045"}

    def test_all_fields_missing_skipped(self):
        instruments = [make_instrument(), make_instrument("AAPL", "XNAS", "US0378331005")]
        idx = build_ticker_isin_index(instruments)
        assert idx == {("AAPL", "XNAS"): "US0378331005"}

    def test_empty_string_ticker_skipped(self):
        instruments = [make_instrument("", "XNAS", "US0378331005")]
        assert build_ticker_isin_index(instruments) == {}

    def test_empty_string_exchange_skipped(self):
        instruments = [make_instrument("AAPL", "", "US0378331005")]
        assert build_ticker_isin_index(instruments) == {}

    def test_empty_string_isin_skipped(self):
        instruments = [make_instrument("AAPL", "XNAS", "")]
        assert build_ticker_isin_index(instruments) == {}

    def test_case_insensitive_normalization(self):
        instruments = [
            make_instrument("aapl", "xnas", "US0378331005"),
            make_instrument("MSFT", "xNYS", "US5949181045"),
        ]
        idx = build_ticker_isin_index(instruments)
        assert ("AAPL", "XNAS") in idx
        assert ("MSFT", "XNYS") in idx
        assert ("aapl", "xnas") not in idx
        assert ("Msft", "Xnys") not in idx

    def test_multi_exchange_disambiguation(self):
        """PRU is Prudential Financial (XNYS) and Prudential plc (XLON)."""
        instruments = [
            make_instrument("PRU", "XNYS", "US7443201022"),
            make_instrument("PRU", "XLON", "GB0007099541"),
        ]
        idx = build_ticker_isin_index(instruments)
        assert len(idx) == 2
        assert idx[("PRU", "XNYS")] == "US7443201022"
        assert idx[("PRU", "XLON")] == "GB0007099541"

    def test_multi_class_same_exchange(self):
        """GOOG and GOOGL are distinct entries on the same exchange."""
        instruments = [
            make_instrument("GOOG", "XNAS", "US02079K1079"),
            make_instrument("GOOGL", "XNAS", "US02079K3059"),
        ]
        idx = build_ticker_isin_index(instruments)
        assert len(idx) == 2
        assert idx[("GOOG", "XNAS")] == "US02079K1079"
        assert idx[("GOOGL", "XNAS")] == "US02079K3059"

    def test_duplicate_key_last_wins(self):
        instruments = [
            make_instrument("AAPL", "XNAS", "US0378331005"),
            make_instrument("AAPL", "XNAS", "US0000000000"),
        ]
        idx = build_ticker_isin_index(instruments)
        assert idx == {("AAPL", "XNAS"): "US0000000000"}

    def test_duplicate_key_raises(self):
        instruments = [
            make_instrument("AAPL", "XNAS", "US0378331005"),
            make_instrument("AAPL", "XNAS", "US0000000000"),
        ]
        with pytest.raises(ValueError, match="duplicate"):
            build_ticker_isin_index(instruments)


    def test_identical_duplicate_is_allowed(self):
        """Two entries with the same key and same ISIN are not a collision."""
        instruments = [
            make_instrument("AAPL", "XNAS", "US0378331005"),
            make_instrument("AAPL", "XNAS", "US0378331005"),
        ]
        idx = build_ticker_isin_index(instruments)
        assert idx == {("AAPL", "XNAS"): "US0378331005"}
    
    def test_extra_fields_ignored(self):
        instruments = [
            make_instrument(
                "AAPL",
                "XNAS",
                "US0378331005",
                name="Apple Inc.",
                currency="USD",
                cik="0000320193",
                figi="BBG000B9XRY4",
            ),
        ]
        idx = build_ticker_isin_index(instruments)
        assert idx == {("AAPL", "XNAS"): "US0378331005"}

    def test_whitespace_not_stripped(self):
        """The implementation does not strip whitespace on input."""
        instruments = [make_instrument(" AAPL ", "XNAS", "US0378331005")]
        idx = build_ticker_isin_index(instruments)
        assert (" AAPL ", "XNAS") in idx
        assert ("AAPL", "XNAS") not in idx

    def test_key_is_tuple_of_str(self):
        instruments = [make_instrument("AAPL", "XNAS", "US0378331005")]
        idx = build_ticker_isin_index(instruments)
        for key in idx:
            assert isinstance(key, tuple)
            assert len(key) == 2
            assert isinstance(key[0], str)
            assert isinstance(key[1], str)


# ----------------------------------------------------------------------
# load_ticker_isin_index — file loading
# ----------------------------------------------------------------------

class TestLoadTickerIsinIndex:
    def test_explicit_path(self, tmp_path, clean_env):
        path = write_registry(tmp_path, {
            "instruments": [
                make_instrument("AAPL", "XNAS", "US0378331005"),
                make_instrument("MSFT", "XNAS", "US5949181045"),
            ],
        })
        idx = load_ticker_isin_index(path)
        assert len(idx) == 2
        assert idx[("AAPL", "XNAS")] == "US0378331005"
        assert idx[("MSFT", "XNAS")] == "US5949181045"

    def test_instruments_key(self, tmp_path, clean_env):
        path = write_registry(tmp_path, {
            "instruments": [make_instrument("AAPL", "XNAS", "US0378331005")],
        })
        idx = load_ticker_isin_index(path)
        assert idx == {("AAPL", "XNAS"): "US0378331005"}

    def test_identifiers_key(self, tmp_path, clean_env):
        path = write_registry(tmp_path, {
            "identifiers": [make_instrument("AAPL", "XNAS", "US0378331005")],
        })
        idx = load_ticker_isin_index(path)
        assert idx == {("AAPL", "XNAS"): "US0378331005"}

    def test_securities_key(self, tmp_path, clean_env):
        path = write_registry(tmp_path, {
            "securities": [make_instrument("AAPL", "XNAS", "US0378331005")],
        })
        idx = load_ticker_isin_index(path)
        assert idx == {("AAPL", "XNAS"): "US0378331005"}

    def test_fallback_to_first_list_with_ticker(self, tmp_path, clean_env):
        path = write_registry(tmp_path, {
            "meta": {"version": "1.0.0"},
            "custom_key": [make_instrument("AAPL", "XNAS", "US0378331005")],
        })
        idx = load_ticker_isin_index(path)
        assert idx == {("AAPL", "XNAS"): "US0378331005"}

    def test_metadata_ignored(self, tmp_path, clean_env):
        path = write_registry(tmp_path, {
            "meta": {"version": "1.0.0", "source": "test"},
            "instruments": [make_instrument("AAPL", "XNAS", "US0378331005")],
        })
        idx = load_ticker_isin_index(path)
        assert len(idx) == 1

    def test_missing_file_raises(self, tmp_path, clean_env):
        with pytest.raises(RegistryLoadError):
            load_ticker_isin_index(str(tmp_path / "nonexistent.json"))

    def test_invalid_json_raises(self, tmp_path, clean_env):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")
        with pytest.raises(RegistryLoadError):
            load_ticker_isin_index(str(path))

    def test_empty_instruments_raises(self, tmp_path, clean_env):
        path = write_registry(tmp_path, {"instruments": []})
        with pytest.raises(RegistryLoadError):
            load_ticker_isin_index(path)

    def test_no_instruments_key_raises(self, tmp_path, clean_env):
        path = write_registry(tmp_path, {"meta": {"version": "1.0.0"}})
        with pytest.raises(RegistryLoadError):
            load_ticker_isin_index(path)

    def test_all_instruments_lack_fields_still_loads(self, tmp_path, clean_env):
        """
        If every instrument is missing ticker/exchange/isin, the loader
        succeeds but produces an empty index.
        """
        path = write_registry(tmp_path, {
            "instruments": [
                {"name": "Bad Instrument 1"},
                {"name": "Bad Instrument 2"},
            ],
        })
        idx = load_ticker_isin_index(path)
        assert idx == {}

    def test_env_var_override(self, tmp_path, clean_env):
        path = write_registry(tmp_path, {
            "instruments": [make_instrument("AAPL", "XNAS", "US0378331005")],
        })
        clean_env.setenv("CORP_ACTIONS_IDENTIFIERS_PATH", path)
        idx = load_ticker_isin_index()
        assert idx == {("AAPL", "XNAS"): "US0378331005"}

    def test_env_var_takes_precedence_over_las_data_home(self, tmp_path, clean_env):
        env_path = write_registry(tmp_path, {
            "instruments": [make_instrument("ENVX", "XNAS", "US0000000001")],
        }, name="env.json")
        home_path = tmp_path / "home"
        home_path.mkdir()
        (home_path / "identifiers.json").write_text(json.dumps({
            "instruments": [make_instrument("HOME", "XNAS", "US0000000002")],
        }), encoding="utf-8")

        clean_env.setenv("CORP_ACTIONS_IDENTIFIERS_PATH", env_path)
        clean_env.setenv("LAS_DATA_HOME", str(home_path))

        idx = load_ticker_isin_index()
        assert ("ENVX", "XNAS") in idx
        assert ("HOME", "XNAS") not in idx

    def test_las_data_home_fallback(self, tmp_path, clean_env):
        home_dir = tmp_path / "data_home"
        home_dir.mkdir()
        (home_dir / "identifiers.json").write_text(json.dumps({
            "instruments": [make_instrument("AAPL", "XNAS", "US0378331005")],
        }), encoding="utf-8")
        clean_env.setenv("LAS_DATA_HOME", str(home_dir))
        idx = load_ticker_isin_index()
        assert idx == {("AAPL", "XNAS"): "US0378331005"}

    def test_explicit_path_overrides_env(self, tmp_path, clean_env):
        env_path = write_registry(tmp_path, {
            "instruments": [make_instrument("ENVX", "XNAS", "US0000000001")],
        }, name="env.json")
        explicit_path = write_registry(tmp_path, {
            "instruments": [make_instrument("EXPL", "XNAS", "US0000000002")],
        }, name="explicit.json")

        clean_env.setenv("CORP_ACTIONS_IDENTIFIERS_PATH", env_path)
        idx = load_ticker_isin_index(explicit_path)
        assert ("EXPL", "XNAS") in idx
        assert ("ENVX", "XNAS") not in idx


# ----------------------------------------------------------------------
# Integration with the real Asset Identifiers registry
# ----------------------------------------------------------------------

class TestRealRegistry:
    def test_loads_at_least_500_instruments(self, real_registry_path):
        idx = load_ticker_isin_index(real_registry_path)
        assert len(idx) >= 500, f"Expected ≥500 entries, got {len(idx)}"

    def test_known_aapl_isin(self, real_registry_path):
        idx = load_ticker_isin_index(real_registry_path)
        assert idx[("AAPL", "XNAS")] == "US0378331005"

    def test_known_msft_isin(self, real_registry_path):
        idx = load_ticker_isin_index(real_registry_path)
        assert idx[("MSFT", "XNAS")] == "US5949181045"

    def test_known_nvda_isin(self, real_registry_path):
        idx = load_ticker_isin_index(real_registry_path)
        assert idx[("NVDA", "XNAS")] == "US67066G1040"

    def test_google_dual_class(self, real_registry_path):
        idx = load_ticker_isin_index(real_registry_path)
        assert idx[("GOOG", "XNAS")] == "US02079K1079"
        assert idx[("GOOGL", "XNAS")] == "US02079K3059"

    def test_prudential_dual_listing(self, real_registry_path):
        idx = load_ticker_isin_index(real_registry_path)
        assert idx[("PRU", "XNYS")] == "US7443201022"
        assert idx[("PRU", "XLON")] == "GB0007099541"

    def test_missing_ticker_raises_keyerror(self, real_registry_path):
        idx = load_ticker_isin_index(real_registry_path)
        with pytest.raises(KeyError):
            idx[("NOTATICKER", "XNAS")]

    def test_missing_exchange_raises_keyerror(self, real_registry_path):
        idx = load_ticker_isin_index(real_registry_path)
        with pytest.raises(KeyError):
            idx[("AAPL", "NOTEXCH")]

    def test_all_keys_are_uppercase(self, real_registry_path):
        idx = load_ticker_isin_index(real_registry_path)
        for (ticker, exchange) in idx:
            assert ticker == ticker.upper(), f"Ticker not uppercase: {ticker}"
            assert exchange == exchange.upper(), f"Exchange not uppercase: {exchange}"