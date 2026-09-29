"""
Cross-check tools.validate.load_iso4217_registry against the real
ISO 4217 registry file, when present on this machine.

The loader is normally exercised against a synthetic fixture
(tests/fixtures/iso4217.json) that covers only a subset of the real
document. This test runs it against the real v1.7.x file to catch
differences in structure, additional fields, or classification
layers the fixture does not exercise.

Skips cleanly when the sibling registry is not checked out. The skip
reason names every path the test looked at.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

from tools.validate import load_iso4217_registry


# ---------------------------------------------------------------------------
# Locate the real registry
# ---------------------------------------------------------------------------

CANDIDATE_PATHS = [
    Path.home() / "Documents" / "iso4217 registry" / "iso4217.json",
    Path.home() / "Documents" / "iso4217" / "iso4217.json",
]


def _find_real_registry() -> Optional[Path]:
    for candidate in CANDIDATE_PATHS:
        if candidate.is_file():
            return candidate
    return None


REAL_PATH = _find_real_registry()

pytestmark = pytest.mark.skipif(
    REAL_PATH is None,
    reason=(
        "real iso4217.json not found; looked at: "
        + ", ".join(str(p) for p in CANDIDATE_PATHS)
    ),
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_path() -> Path:
    assert REAL_PATH is not None
    return REAL_PATH


@pytest.fixture(scope="module")
def real_doc(real_path: Path) -> dict:
    return json.loads(real_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def active_codes(real_path: Path) -> set:
    return load_iso4217_registry(str(real_path))


# ---------------------------------------------------------------------------
# Loader behaviour
# ---------------------------------------------------------------------------

class TestLoaderOnRealFile:

    def test_loads_without_error(self, real_path: Path) -> None:
        codes = load_iso4217_registry(str(real_path))
        assert isinstance(codes, set)

    def test_returns_non_empty(self, active_codes: set) -> None:
        assert len(active_codes) > 0

    def test_returns_at_least_150(self, active_codes: set) -> None:
        # tools/validate.py enforces MIN_ACTIVE_CURRENCIES = 150
        assert len(active_codes) >= 150

    def test_returns_at_most_300(self, active_codes: set) -> None:
        # Sanity upper bound. Current count is 167; leave headroom for
        # future ISO amendments without being unbounded.
        assert len(active_codes) <= 300


# ---------------------------------------------------------------------------
# Shape of the returned set
# ---------------------------------------------------------------------------

class TestSetShape:

    def test_all_codes_are_strings(self, active_codes: set) -> None:
        for code in active_codes:
            assert isinstance(code, str), f"non-string code: {code!r}"

    def test_all_codes_are_three_letters(self, active_codes: set) -> None:
        for code in active_codes:
            assert len(code) == 3, f"non-three-letter code: {code!r}"
            assert code.isalpha(), f"non-alpha code: {code!r}"

    def test_all_codes_are_uppercase(self, active_codes: set) -> None:
        for code in active_codes:
            assert code == code.upper(), f"lowercase code: {code!r}"

    def test_no_whitespace_in_codes(self, active_codes: set) -> None:
        for code in active_codes:
            assert code == code.strip(), f"whitespace in code: {code!r}"


# ---------------------------------------------------------------------------
# Required active currencies
# ---------------------------------------------------------------------------

# Currencies that any complete ISO 4217 active registry must contain.
# All are still-active codes as of the 2024-2026 amendment window.
REQUIRED_ACTIVE = {
    # Majors
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD",
    "CNY", "HKD", "SGD", "KRW", "INR",
    # Other G20 members
    "BRL", "MXN", "ARS", "ZAR", "TRY", "RUB", "SAR", "IDR",
    # Widely traded minor
    "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "ILS", "THB",
    # Fund codes that are technically active ISO 4217 codes
    "CLF", "USN",
}


class TestRequiredActiveCurrencies:

    @pytest.mark.parametrize("code", sorted(REQUIRED_ACTIVE))
    def test_code_present(self, active_codes: set, code: str) -> None:
        assert code in active_codes, f"{code} missing from real registry"


# ---------------------------------------------------------------------------
# Withdrawn codes are NOT in the loader's active set
# ---------------------------------------------------------------------------

# A sample of currencies ISO 4217 has formally withdrawn. None may
# appear in the set returned by the loader.
WITHDRAWN_SAMPLE = [
    "DEM",  # German Mark
    "FRF",  # French Franc
    "ITL",  # Italian Lira
    "ESP",  # Spanish Peseta
    "NLG",  # Dutch Guilder
    "ATS",  # Austrian Schilling
    "IEP",  # Irish Pound
    "PTE",  # Portuguese Escudo
    "FIM",  # Finnish Markka
    "GRD",  # Greek Drachma
    "BEF",  # Belgian Franc
    "LUF",  # Luxembourg Franc
]


class TestWithdrawnNotInActive:

    @pytest.mark.parametrize("code", WITHDRAWN_SAMPLE)
    def test_withdrawn_code_absent(self, active_codes: set, code: str) -> None:
        assert code not in active_codes, (
            f"{code} is a withdrawn ISO 4217 code; it must not appear "
            f"in the loader's active set"
        )


# ---------------------------------------------------------------------------
# Fixture is a subset of the real registry
# ---------------------------------------------------------------------------

class TestFixtureIsSubsetOfReal:

    @pytest.fixture(scope="class")
    def fixture_codes(self) -> set:
        fixture = Path(__file__).resolve().parent / "fixtures" / "iso4217.json"
        if not fixture.is_file():
            pytest.skip("tests/fixtures/iso4217.json not present")
        data = json.loads(fixture.read_text(encoding="utf-8"))
        active = data.get("currencies", {}).get("active", [])
        return {entry.get("code") for entry in active if entry.get("code")}

    def test_no_fixture_code_missing_from_real(
        self, fixture_codes: set, active_codes: set,
    ) -> None:
        missing = fixture_codes - active_codes
        assert not missing, (
            f"fixture codes not present in the real registry: {sorted(missing)}"
        )


# ---------------------------------------------------------------------------
# Parse of the real document (not just the loader)
# ---------------------------------------------------------------------------

class TestRealDocumentShape:

    def test_document_is_object(self, real_doc: dict) -> None:
        assert isinstance(real_doc, dict)

    def test_has_currencies_key(self, real_doc: dict) -> None:
        assert "currencies" in real_doc

    def test_currencies_has_active_and_withdrawn(self, real_doc: dict) -> None:
        curr = real_doc["currencies"]
        assert "active" in curr
        assert "withdrawn" in curr
        assert isinstance(curr["active"], list)
        assert isinstance(curr["withdrawn"], list)

    def test_active_count_matches_loader(
        self, real_doc: dict, active_codes: set,
    ) -> None:
        declared = len(real_doc["currencies"]["active"])
        assert declared == len(active_codes), (
            f"document declares {declared} active entries; "
            f"loader returned {len(active_codes)}"
        )

    def test_withdrawn_count_is_positive(self, real_doc: dict) -> None:
        assert len(real_doc["currencies"]["withdrawn"]) > 0

    def test_meta_block_present(self, real_doc: dict) -> None:
        assert "meta" in real_doc

    def test_meta_has_version(self, real_doc: dict) -> None:
        assert "version" in real_doc["meta"]
        assert isinstance(real_doc["meta"]["version"], str)


# ---------------------------------------------------------------------------
# Every active entry has a code; no duplicates
# ---------------------------------------------------------------------------

class TestActiveEntriesWellFormed:

    def test_no_entry_missing_code(self, real_doc: dict) -> None:
        for i, entry in enumerate(real_doc["currencies"]["active"]):
            assert "code" in entry, f"active[{i}] missing 'code'"
            assert entry["code"], f"active[{i}] has empty 'code'"

    def test_no_duplicate_active_codes(self, real_doc: dict) -> None:
        codes = [e["code"] for e in real_doc["currencies"]["active"]]
        assert len(codes) == len(set(codes)), "duplicate codes in active"

    def test_no_duplicate_withdrawn_codes(self, real_doc: dict) -> None:
        codes = [e["code"] for e in real_doc["currencies"]["withdrawn"]]
        assert len(codes) == len(set(codes)), "duplicate codes in withdrawn"