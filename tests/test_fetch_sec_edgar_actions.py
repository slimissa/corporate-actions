"""
Tests for tools/fetch_sec_edgar_actions.py.

The fetcher is network-bound, so most tests exercise the pure helpers
directly. The integration tests replace SECClient with a fake that
returns synthetic submissions and filing texts, so no network is
required and no real SEC data is used.

Coverage targets
----------------
- load_instruments: field filtering, CIK normalisation, CIK=0 rejection,
  BOM tolerance, missing/invalid file handling.
- parse_date: month table lookup, calendar validity.
- extract_effective_date: prose patterns, missing date.
- extract_new_symbol: strong and weak pattern matches, blocklist
  rejection of common English words, digit and length filters.
- is_symbol_change, is_delisting: trigger detection.
- _filing_url: CIK and accession normalisation.
- build_symbol_change, build_delisting: action shape and ID format.
- _warn_about_archive_files: warning emission.
- main: exit codes 0, 1, 2, 3; both-actions-from-one-filing; min-date
  and cik-limit filtering; BOM tolerance; output file structure.

Run
---
    python -m pytest tests/test_fetch_sec_edgar_actions.py -v
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import tools.fetch_sec_edgar_actions as mod
from tools.fetch_sec_edgar_actions import (
    COMMON_ENGLISH_WORDS,
    _filing_url,
    _warn_about_archive_files,
    build_delisting,
    build_symbol_change,
    extract_effective_date,
    extract_new_symbol,
    is_delisting,
    is_symbol_change,
    load_instruments,
    main,
    parse_date,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_identifiers(tmp_path, instruments, *, bom=False):
    """Write an identifiers.json and return its path."""
    path = tmp_path / "identifiers.json"
    payload = json.dumps({"instruments": instruments}, indent=2)
    data = payload.encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    path.write_bytes(data)
    return path


def _run_main(monkeypatch, argv):
    """Invoke main() with a specific argv and return its exit code."""
    monkeypatch.setattr(sys, "argv", ["fetch_sec_edgar_actions.py"] + argv)
    return main()


# A fake SECClient for integration tests. It returns synthetic
# submissions and filing texts, so no network request is made.

class FakeSECClient:
    def __init__(self, submissions=None, texts=None):
        self.submissions = submissions or {}
        self.texts = texts or {}
        self.get_submissions_calls = []
        self.get_filing_text_calls = []

    def get_submissions(self, cik):
        self.get_submissions_calls.append(cik)
        return self.submissions.get(cik)

    def get_filing_text(self, cik, accession):
        self.get_filing_text_calls.append(accession)
        return self.texts.get(accession)


def _fake_submissions(forms, accessions, docs, dates, files=None):
    """Build a submissions dict in the shape data.sec.gov returns."""
    filings = {
        "recent": {
            "form": forms,
            "accessionNumber": accessions,
            "primaryDocument": docs,
            "filingDate": dates,
        },
    }
    if files is not None:
        filings["files"] = files
    return {"filings": filings}


@pytest.fixture
def patch_client(monkeypatch):
    """Return a helper that installs a fake SECClient."""
    def _install(fake):
        monkeypatch.setattr(mod, "SECClient", lambda *a, **kw: fake)
        return fake
    return _install


# ---------------------------------------------------------------------------
# load_instruments
# ---------------------------------------------------------------------------

class TestLoadInstruments:

    def test_single_valid_instrument(self, tmp_path):
        path = _write_identifiers(tmp_path, [
            {"isin": "US0378331005", "ticker": "AAPL", "cik": "320193"},
        ])
        result = load_instruments(str(path))
        assert result == [("US0378331005", "AAPL", "0000320193")]

    def test_cik_is_zero_padded_to_ten_digits(self, tmp_path):
        path = _write_identifiers(tmp_path, [
            {"isin": "US0378331005", "ticker": "AAPL", "cik": "320193"},
        ])
        assert load_instruments(str(path))[0][2] == "0000320193"

    def test_cik_already_ten_digits_unchanged(self, tmp_path):
        path = _write_identifiers(tmp_path, [
            {"isin": "US0378331005", "ticker": "AAPL", "cik": "0000320193"},
        ])
        assert load_instruments(str(path))[0][2] == "0000320193"

    def test_cik_integer_is_accepted(self, tmp_path):
        path = _write_identifiers(tmp_path, [
            {"isin": "US0378331005", "ticker": "AAPL", "cik": 320193},
        ])
        assert load_instruments(str(path))[0][2] == "0000320193"

    def test_ticker_uppercased(self, tmp_path):
        path = _write_identifiers(tmp_path, [
            {"isin": "US0378331005", "ticker": "aapl", "cik": "320193"},
        ])
        assert load_instruments(str(path))[0][1] == "AAPL"

    def test_cik_zero_rejected(self, tmp_path):
        path = _write_identifiers(tmp_path, [
            {"isin": "US0378331005", "ticker": "AAPL", "cik": "0"},
            {"isin": "US0378331005", "ticker": "AAPL", "cik": 0},
            {"isin": "US0378331005", "ticker": "AAPL", "cik": "0000000000"},
        ])
        assert load_instruments(str(path)) == []

    def test_entry_missing_isin_skipped(self, tmp_path):
        path = _write_identifiers(tmp_path, [
            {"ticker": "AAPL", "cik": "320193"},
            {"isin": "US0378331005", "ticker": "AAPL", "cik": "320193"},
        ])
        result = load_instruments(str(path))
        assert len(result) == 1
        assert result[0][1] == "AAPL"

    def test_entry_missing_ticker_skipped(self, tmp_path):
        path = _write_identifiers(tmp_path, [
            {"isin": "US0378331005", "cik": "320193"},
        ])
        assert load_instruments(str(path)) == []

    def test_entry_missing_cik_skipped(self, tmp_path):
        path = _write_identifiers(tmp_path, [
            {"isin": "US0378331005", "ticker": "AAPL"},
        ])
        assert load_instruments(str(path)) == []

    def test_entry_missing_all_skipped(self, tmp_path):
        path = _write_identifiers(tmp_path, [
            {"name": "no identifiers"},
        ])
        assert load_instruments(str(path)) == []

    def test_missing_file_exits_2(self, tmp_path):
        with pytest.raises(SystemExit) as exc_info:
            load_instruments(str(tmp_path / "nope.json"))
        assert exc_info.value.code == 2

    def test_invalid_json_exits_2(self, tmp_path):
        path = tmp_path / "identifiers.json"
        path.write_text("{ not valid json", encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            load_instruments(str(path))
        assert exc_info.value.code == 2

    def test_bom_prefixed_file_loads(self, tmp_path):
        path = _write_identifiers(
            tmp_path,
            [{"isin": "US0378331005", "ticker": "AAPL", "cik": "320193"}],
            bom=True,
        )
        assert load_instruments(str(path)) == [
            ("US0378331005", "AAPL", "0000320193"),
        ]

    def test_identifiers_key_works_as_fallback(self, tmp_path):
        path = tmp_path / "identifiers.json"
        path.write_text(json.dumps({
            "identifiers": [
                {"isin": "US0378331005", "ticker": "AAPL", "cik": "320193"},
            ],
        }), encoding="utf-8")
        assert load_instruments(str(path)) == [
            ("US0378331005", "AAPL", "0000320193"),
        ]

    def test_empty_instruments_returns_empty_list(self, tmp_path):
        path = _write_identifiers(tmp_path, [])
        assert load_instruments(str(path)) == []


# ---------------------------------------------------------------------------
# parse_date
# ---------------------------------------------------------------------------

class TestParseDate:

    def test_full_month_name(self):
        assert parse_date("January", "15", "2024") == "2024-01-15"

    def test_lowercase_month(self):
        assert parse_date("january", "15", "2024") == "2024-01-15"

    def test_abbreviated_month(self):
        assert parse_date("Jan", "15", "2024") == "2024-01-15"

    def test_unknown_month_returns_none(self):
        assert parse_date("Smarch", "15", "2024") is None

    def test_invalid_day_returns_none(self):
        assert parse_date("February", "30", "2024") is None

    def test_invalid_month_number_returns_none(self):
        assert parse_date("January", "32", "2024") is None

    def test_invalid_year_returns_none(self):
        assert parse_date("January", "15", "abc") is None

    def test_leap_day_valid_in_leap_year(self):
        assert parse_date("February", "29", "2024") == "2024-02-29"

    def test_leap_day_invalid_in_non_leap_year(self):
        assert parse_date("February", "29", "2023") is None

    def test_all_abbreviations_map(self):
        cases = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
            "nov": 11, "dec": 12,
        }
        for abbr, month in cases.items():
            assert parse_date(abbr, "1", "2024") == f"2024-{month:02d}-01"


# ---------------------------------------------------------------------------
# extract_effective_date
# ---------------------------------------------------------------------------

class TestExtractEffectiveDate:

    def test_effective_as_of(self):
        text = "The delisting is effective as of January 15, 2024."
        assert extract_effective_date(text) == "2024-01-15"

    def test_effective_on(self):
        text = "The change is effective on March 3, 2023."
        assert extract_effective_date(text) == "2023-03-03"

    def test_effective_without_preposition(self):
        text = "Effective June 10, 2022, the Company will trade under META."
        assert extract_effective_date(text) == "2022-06-10"

    def test_on_date(self):
        text = "The Company expects on April 5, 2025 to complete the merger."
        assert extract_effective_date(text) == "2025-04-05"

    def test_as_of_with_or_about(self):
        text = "as of or about July 20, 2021"
        assert extract_effective_date(text) == "2021-07-20"

    def test_abbreviated_month_in_prose(self):
        text = "effective on Sept 30, 2024"
        assert extract_effective_date(text) == "2024-09-30"

    def test_no_date_returns_none(self):
        assert extract_effective_date("no dates in this text at all") is None

    def test_empty_string_returns_none(self):
        assert extract_effective_date("") is None

    def test_first_date_wins_when_multiple(self):
        text = (
            "effective January 1, 2024 and again on February 1, 2024"
        )
        assert extract_effective_date(text) == "2024-01-01"

    def test_invalid_date_skipped_for_next_pattern(self):
        text = "effective February 30, 2023 and on March 1, 2023"
        # Feb 30 is invalid, so the pattern returns None for that match,
        # and the function continues to the next pattern.
        assert extract_effective_date(text) == "2023-03-01"


# ---------------------------------------------------------------------------
# extract_new_symbol
# ---------------------------------------------------------------------------

class TestExtractNewSymbol:

    def test_will_begin_trading_under_symbol(self):
        text = (
            "The Company will begin trading under the symbol META on "
            "June 9, 2022."
        )
        assert extract_new_symbol(text) == "META"

    def test_will_trade_under_new_symbol(self):
        text = "The shares will trade under the new symbol ABCD."
        assert extract_new_symbol(text) == "ABCD"

    def test_changes_its_symbol_to(self):
        text = "The Company changes its symbol to XYZW."
        assert extract_new_symbol(text) == "XYZW"

    def test_changing_its_ticker_symbol(self):
        text = "The issuer is changing its ticker symbol to ABC."
        assert extract_new_symbol(text) == "ABC"

    def test_new_symbol_will_be(self):
        text = "The new symbol will be WXYZ."
        assert extract_new_symbol(text) == "WXYZ"

    def test_trading_symbol_will_change_to(self):
        text = "The trading symbol will change to NIO."
        assert extract_new_symbol(text) == "NIO"

    def test_no_match_returns_none(self):
        assert extract_new_symbol("This filing has no symbol change.") is None

    def test_empty_string_returns_none(self):
        assert extract_new_symbol("") is None

    @pytest.mark.parametrize("trap", [
        "The new symbol is US.",
        "It will be up from here.",
        "The answer is IT.",
        "The new symbol will be AS.",
        "The new symbol is ONE.",
        "The new symbol will be SOME.",
    ])
    def test_common_english_words_rejected(self, trap):
        """The weak patterns capture any uppercase 1-6 letter word, so
        the blocklist filters common English."""
        assert extract_new_symbol(trap) is None

    def test_symbol_with_digit_is_not_captured(self):
        # The pattern only allows [A-Z], so anything with a digit cannot
        # match at all.
        text = "The new symbol will be AB1."
        assert extract_new_symbol(text) is None

    def test_symbol_too_long_not_captured(self):
        # Patterns cap at {1,6}, so 7+ letter strings do not match.
        text = "The new symbol will be ABCDEFGH."
        assert extract_new_symbol(text) is None

    def test_first_valid_match_wins(self):
        text = (
            "The new symbol will be US. "
            "The Company will begin trading under the symbol META."
        )
        assert extract_new_symbol(text) == "META"

    def test_strong_pattern_takes_priority_when_order_preserved(self):
        text = (
            "The Company will begin trading under the symbol META. "
            "The new symbol is US."
        )
        assert extract_new_symbol(text) == "META"

    def test_quoted_symbol_matched(self):
        text = 'The trading symbol will change to "GOOG".'
        assert extract_new_symbol(text) == "GOOG"

    def test_blocklist_is_frozenset_and_non_empty(self):
        assert isinstance(COMMON_ENGLISH_WORDS, frozenset)
        assert len(COMMON_ENGLISH_WORDS) > 50

    def test_blocklist_does_not_contain_real_tickers(self):
        # Sanity check: the blocklist must not accidentally reject real
        # tickers. If a ticker is ever added to it, this test fails.
        for ticker in ("AAPL", "MSFT", "NVDA", "META", "GOOG", "AMZN"):
            assert ticker not in COMMON_ENGLISH_WORDS


# ---------------------------------------------------------------------------
# is_symbol_change / is_delisting
# ---------------------------------------------------------------------------

class TestIsSymbolChange:

    @pytest.mark.parametrize("text", [
        "will begin trading under the symbol META",
        "will trade under the new symbol ABCD",
        "changes its symbol to XYZ",
        "changing its ticker symbol to ABC",
        "the new symbol will be WXYZ",
        "the trading symbol will change to NIO",
    ])
    def test_positive(self, text):
        assert is_symbol_change(text) is True

    @pytest.mark.parametrize("text", [
        "this filing has no symbol change",
        "",
        "shares outstanding: 1,000,000",
    ])
    def test_negative(self, text):
        assert is_symbol_change(text) is False


class TestIsDelisting:

    @pytest.mark.parametrize("text", [
        "will be delisted from the NYSE",
        "will be voluntarily delisted from Nasdaq",
        "delisting from the New York Stock Exchange",
        "delisted from the Nasdaq Market",
        "intends to delist",
        "intends to voluntarily delist",
    ])
    def test_positive(self, text):
        assert is_delisting(text) is True

    @pytest.mark.parametrize("text", [
        "this filing has no mention",
        "",
        "the delisting date was previously announced",
    ])
    def test_negative(self, text):
        assert is_delisting(text) is False


# ---------------------------------------------------------------------------
# _filing_url
# ---------------------------------------------------------------------------

class TestFilingUrl:

    def test_strips_leading_zeros_from_cik(self):
        url = _filing_url("0000320193", "0001234567-24-000001", "doc.htm")
        assert "/edgar/data/320193/" in url

    def test_strips_dashes_from_accession(self):
        url = _filing_url("0000320193", "0001234567-24-000001", "doc.htm")
        assert "/000123456724000001/" in url

    def test_includes_primary_doc(self):
        url = _filing_url("0000320193", "0001234567-24-000001", "doc.htm")
        assert url.endswith("/doc.htm")

    def test_full_url_shape(self):
        url = _filing_url("0000320193", "0001234567-24-000001", "doc.htm")
        assert url == (
            "https://www.sec.gov/Archives/edgar/data/"
            "320193/000123456724000001/doc.htm"
        )

    def test_cik_of_zero_handled(self):
        # A pathological input: the lstrip("0") returns empty, so the
        # fallback "0" is used.
        url = _filing_url("0000000000", "0001-24-000001", "d.htm")
        assert "/edgar/data/0/" in url


# ---------------------------------------------------------------------------
# build_symbol_change
# ---------------------------------------------------------------------------

class TestBuildSymbolChange:

    def _build(self, text="will begin trading under the symbol META"):
        return build_symbol_change(
            isin="US30303M1027",
            current_ticker="FB",
            cik="0001326801",
            filing_date="2022-06-01",
            accession="0001326801-22-000011",
            primary_doc="doc.htm",
            text=text,
        )

    def test_returns_action_dict(self):
        action = self._build()
        assert isinstance(action, dict)
        assert action["isin"] == "US30303M1027"
        assert action["action_type"] == "SYMBOL_CHANGE"

    def test_action_id_format(self):
        action = self._build()
        # Falls back to filing_date when no effective date in text.
        assert action["action_id"] == "US30303M1027-SYMBOL_CHANGE-2022-06-01-SYMBOL"

    def test_effective_date_from_text(self):
        action = self._build(
            "effective June 9, 2022, the company will begin trading "
            "under the symbol META"
        )
        assert action["dates"]["effective_date"] == "2022-06-09"

    def test_effective_date_falls_back_to_filing_date(self):
        action = self._build("will begin trading under the symbol META")
        assert action["dates"]["effective_date"] == "2022-06-01"

    def test_announcement_date_is_filing_date(self):
        action = self._build()
        assert action["dates"]["announcement"] == "2022-06-01"

    def test_impact_is_neutral(self):
        action = self._build()
        assert action["impact"] == {
            "price_multiplier": 1.0,
            "share_multiplier": 1.0,
            "cash_adjustment": 0.0,
        }

    def test_provenance_source(self):
        action = self._build()
        assert action["provenance"]["source"] == "SEC EDGAR"
        assert action["provenance"]["source_url"].startswith(
            "https://www.sec.gov/Archives/edgar/data/"
        )

    def test_status_is_completed(self):
        assert self._build()["status"] == "COMPLETED"

    def test_returns_none_when_no_new_symbol(self):
        assert self._build("no symbol change in this text") is None

    def test_returns_none_when_new_equals_current(self):
        # current_ticker is FB, text says "symbol is FB": no real change.
        action = self._build("the new symbol is FB")
        assert action is None


# ---------------------------------------------------------------------------
# build_delisting
# ---------------------------------------------------------------------------

class TestBuildDelisting:

    def _build(self, text="will be delisted from the NYSE"):
        return build_delisting(
            isin="US90184L1026",
            cik="0001418091",
            filing_date="2022-10-27",
            accession="0001418091-22-000010",
            primary_doc="delist.htm",
            text=text,
        )

    def test_returns_action_dict(self):
        action = self._build()
        assert isinstance(action, dict)
        assert action["isin"] == "US90184L1026"
        assert action["action_type"] == "DELISTING"

    def test_action_id_format(self):
        action = self._build()
        assert action["action_id"] == "US90184L1026-DELISTING-2022-10-27-DELISTED"

    def test_effective_date_from_text(self):
        action = self._build("effective October 28, 2022")
        assert action["dates"]["effective_date"] == "2022-10-28"
        assert action["action_id"].endswith("-2022-10-28-DELISTED")

    def test_effective_date_falls_back_to_filing_date(self):
        action = self._build("will be delisted from the NYSE")
        assert action["dates"]["effective_date"] == "2022-10-27"

    def test_announcement_date_is_filing_date(self):
        assert self._build()["dates"]["announcement"] == "2022-10-27"

    def test_impact_is_neutral(self):
        assert self._build()["impact"] == {
            "price_multiplier": 1.0,
            "share_multiplier": 1.0,
            "cash_adjustment": 0.0,
        }

    def test_provenance_source(self):
        action = self._build()
        assert action["provenance"]["source"] == "SEC EDGAR"
        assert action["provenance"]["source_url"].endswith("/delist.htm")

    def test_status_is_completed(self):
        assert self._build()["status"] == "COMPLETED"


# ---------------------------------------------------------------------------
# _warn_about_archive_files
# ---------------------------------------------------------------------------

class TestWarnAboutArchiveFiles:

    def test_no_warning_when_files_absent(self, capsys):
        _warn_about_archive_files("AAPL", {"filings": {}})
        assert capsys.readouterr().err == ""

    def test_no_warning_when_files_empty(self, capsys):
        _warn_about_archive_files("AAPL", {"filings": {"files": []}})
        assert capsys.readouterr().err == ""

    def test_no_warning_when_files_none(self, capsys):
        _warn_about_archive_files("AAPL", {"filings": {"files": None}})
        assert capsys.readouterr().err == ""

    def test_warning_when_files_non_empty(self, capsys):
        _warn_about_archive_files("AAPL", {"filings": {"files": [1]}})
        err = capsys.readouterr().err
        assert "AAPL" in err
        assert "1 archive file" in err
        assert "recent ~1000" in err

    def test_warning_includes_file_count(self, capsys):
        _warn_about_archive_files("NVDA", {"filings": {"files": [1, 2, 3]}})
        err = capsys.readouterr().err
        assert "NVDA" in err
        assert "3 archive file" in err

    def test_no_warning_when_submissions_empty(self, capsys):
        _warn_about_archive_files("AAPL", {})
        assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# main — integration via fake SECClient
# ---------------------------------------------------------------------------

class TestMainIntegration:

    def test_empty_instruments_exits_3(self, tmp_path, monkeypatch, patch_client):
        path = _write_identifiers(tmp_path, [])
        patch_client(FakeSECClient())
        code = _run_main(monkeypatch, [
            "--identifiers", str(path),
            "--output", str(tmp_path / "out.json"),
        ])
        assert code == 3

    def test_all_fetches_fail_exits_3(self, tmp_path, monkeypatch, patch_client):
        path = _write_identifiers(tmp_path, [
            {"isin": "US0378331005", "ticker": "AAPL", "cik": "320193"},
        ])
        # No submissions registered, so get_submissions returns None.
        patch_client(FakeSECClient())
        code = _run_main(monkeypatch, [
            "--identifiers", str(path),
            "--output", str(tmp_path / "out.json"),
        ])
        assert code == 3

    def test_partial_failure_exits_1(self, tmp_path, monkeypatch, patch_client):
        path = _write_identifiers(tmp_path, [
            {"isin": "US0378331005", "ticker": "AAPL", "cik": "320193"},
            {"isin": "US5949181045", "ticker": "MSFT", "cik": "789019"},
        ])
        fake = FakeSECClient(submissions={
            "0000320193": _fake_submissions(
                forms=[], accessions=[], docs=[], dates=[],
            ),
        })
        patch_client(fake)
        code = _run_main(monkeypatch, [
            "--identifiers", str(path),
            "--output", str(tmp_path / "out.json"),
        ])
        assert code == 1

    def test_successful_run_exits_0(self, tmp_path, monkeypatch, patch_client):
        path = _write_identifiers(tmp_path, [
            {"isin": "US0378331005", "ticker": "AAPL", "cik": "320193"},
        ])
        fake = FakeSECClient(submissions={
            "0000320193": _fake_submissions(
                forms=[], accessions=[], docs=[], dates=[],
            ),
        })
        patch_client(fake)
        code = _run_main(monkeypatch, [
            "--identifiers", str(path),
            "--output", str(tmp_path / "out.json"),
        ])
        assert code == 0

    def test_symbol_change_is_extracted(self, tmp_path, monkeypatch, patch_client):
        path = _write_identifiers(tmp_path, [
            {"isin": "US30303M1027", "ticker": "FB", "cik": "1326801"},
        ])
        fake = FakeSECClient(
            submissions={
                "0001326801": _fake_submissions(
                    forms=["8-K"],
                    accessions=["0001326801-22-000011"],
                    docs=["doc.htm"],
                    dates=["2022-06-01"],
                ),
            },
            texts={
                "0001326801-22-000011":
                    "The Company will begin trading under the symbol META",
            },
        )
        patch_client(fake)
        out = tmp_path / "out.json"
        code = _run_main(monkeypatch, [
            "--identifiers", str(path),
            "--output", str(out),
        ])
        assert code == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["actions"]) == 1
        assert data["actions"][0]["action_type"] == "SYMBOL_CHANGE"

    def test_delisting_is_extracted(self, tmp_path, monkeypatch, patch_client):
        path = _write_identifiers(tmp_path, [
            {"isin": "US90184L1026", "ticker": "TWTR", "cik": "1418091"},
        ])
        fake = FakeSECClient(
            submissions={
                "0001418091": _fake_submissions(
                    forms=["8-K"],
                    accessions=["0001418091-22-000010"],
                    docs=["delist.htm"],
                    dates=["2022-10-27"],
                ),
            },
            texts={
                "0001418091-22-000010":
                    "will be delisted from the NYSE effective October 28, 2022",
            },
        )
        patch_client(fake)
        out = tmp_path / "out.json"
        code = _run_main(monkeypatch, [
            "--identifiers", str(path),
            "--output", str(out),
        ])
        assert code == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["actions"]) == 1
        assert data["actions"][0]["action_type"] == "DELISTING"

    def test_both_actions_from_one_filing(self, tmp_path, monkeypatch, patch_client):
        """Regression: the old code had a `continue` after a symbol
        change that skipped the delisting check."""
        path = _write_identifiers(tmp_path, [
            {"isin": "US30303M1027", "ticker": "FB", "cik": "1326801"},
        ])
        fake = FakeSECClient(
            submissions={
                "0001326801": _fake_submissions(
                    forms=["8-K"],
                    accessions=["0001326801-22-000011"],
                    docs=["doc.htm"],
                    dates=["2022-06-01"],
                ),
            },
            texts={
                "0001326801-22-000011":
                    "The Company will begin trading under the symbol META "
                    "and will be delisted from the NYSE.",
            },
        )
        patch_client(fake)
        out = tmp_path / "out.json"
        code = _run_main(monkeypatch, [
            "--identifiers", str(path),
            "--output", str(out),
        ])
        assert code == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        types = sorted(a["action_type"] for a in data["actions"])
        assert types == ["DELISTING", "SYMBOL_CHANGE"]

    def test_archive_warning_emitted(self, tmp_path, monkeypatch, patch_client, capsys):
        path = _write_identifiers(tmp_path, [
            {"isin": "US0378331005", "ticker": "AAPL", "cik": "320193"},
        ])
        fake = FakeSECClient(submissions={
            "0000320193": _fake_submissions(
                forms=[], accessions=[], docs=[], dates=[],
                files=["CIK0000320193-submissions-001.json"],
            ),
        })
        patch_client(fake)
        _run_main(monkeypatch, [
            "--identifiers", str(path),
            "--output", str(tmp_path / "out.json"),
        ])
        err = capsys.readouterr().err
        assert "AAPL" in err
        assert "archive file" in err

    def test_min_date_filters_old_filings(self, tmp_path, monkeypatch, patch_client):
        path = _write_identifiers(tmp_path, [
            {"isin": "US30303M1027", "ticker": "FB", "cik": "1326801"},
        ])
        fake = FakeSECClient(
            submissions={
                "0001326801": _fake_submissions(
                    forms=["8-K", "8-K"],
                    accessions=["old-acc", "new-acc"],
                    docs=["old.htm", "new.htm"],
                    dates=["2018-01-01", "2022-06-01"],
                ),
            },
            texts={
                "old-acc": "will begin trading under the symbol ABC",
                "new-acc": "will begin trading under the symbol META",
            },
        )
        patch_client(fake)
        out = tmp_path / "out.json"
        _run_main(monkeypatch, [
            "--identifiers", str(path),
            "--output", str(out),
            "--min-date", "2020-01-01",
        ])
        data = json.loads(out.read_text(encoding="utf-8"))
        # Only the 2022 filing is within range.
        assert len(data["actions"]) == 1
        # The 2022 filing is the one extracted; its ID uses the canonical
        # -SYMBOL discriminator (the new ticker is not encoded in the ID).
        assert data["actions"][0]["action_id"] == (
            "US30303M1027-SYMBOL_CHANGE-2022-06-01-SYMBOL"
        )
        # And the old accession was never fetched.
        assert "old-acc" not in fake.get_filing_text_calls

    def test_cik_limit(self, tmp_path, monkeypatch, patch_client):
        path = _write_identifiers(tmp_path, [
            {"isin": "US0378331005", "ticker": "AAPL", "cik": "320193"},
            {"isin": "US5949181045", "ticker": "MSFT", "cik": "789019"},
            {"isin": "US67066G1040", "ticker": "NVDA", "cik": "1045810"},
        ])
        fake = FakeSECClient()
        patch_client(fake)
        _run_main(monkeypatch, [
            "--identifiers", str(path),
            "--output", str(tmp_path / "out.json"),
            "--cik-limit", "2",
        ])
        assert len(fake.get_submissions_calls) == 2

    def test_non_8k_forms_are_ignored(self, tmp_path, monkeypatch, patch_client):
        path = _write_identifiers(tmp_path, [
            {"isin": "US30303M1027", "ticker": "FB", "cik": "1326801"},
        ])
        fake = FakeSECClient(
            submissions={
                "0001326801": _fake_submissions(
                    forms=["10-K", "10-Q", "8-K"],
                    accessions=["a", "b", "c"],
                    docs=["10k.htm", "10q.htm", "8k.htm"],
                    dates=["2024-01-01", "2024-04-01", "2024-06-01"],
                ),
            },
            texts={
                "a": "will begin trading under the symbol XXX",
                "b": "will begin trading under the symbol YYY",
                "c": "will begin trading under the symbol META",
            },
        )
        patch_client(fake)
        out = tmp_path / "out.json"
        _run_main(monkeypatch, [
            "--identifiers", str(path),
            "--output", str(out),
        ])
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["actions"]) == 1
        # Only the 8-K filing yielded an action; its ID uses the
        # canonical -SYMBOL discriminator.
        assert data["actions"][0]["action_id"] == (
            "US30303M1027-SYMBOL_CHANGE-2024-06-01-SYMBOL"
        )

    def test_output_is_valid_json_with_expected_shape(self, tmp_path, monkeypatch, patch_client):
        path = _write_identifiers(tmp_path, [
            {"isin": "US0378331005", "ticker": "AAPL", "cik": "320193"},
        ])
        fake = FakeSECClient(submissions={
            "0000320193": _fake_submissions(
                forms=[], accessions=[], docs=[], dates=[],
            ),
        })
        patch_client(fake)
        out = tmp_path / "out.json"
        _run_main(monkeypatch, [
            "--identifiers", str(path),
            "--output", str(out),
        ])
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "meta" in data
        assert "actions" in data
        assert isinstance(data["actions"], list)
        assert data["meta"]["source"] == "SEC EDGAR"
        assert data["meta"]["generated_at"].endswith("Z")

    def test_duplicate_action_ids_are_deduplicated(self, tmp_path, monkeypatch, patch_client):
        """Two filings producing the same action_id must yield one entry."""
        path = _write_identifiers(tmp_path, [
            {"isin": "US30303M1027", "ticker": "FB", "cik": "1326801"},
        ])
        fake = FakeSECClient(
            submissions={
                "0001326801": _fake_submissions(
                    forms=["8-K", "8-K"],
                    accessions=["a", "b"],
                    docs=["doc1.htm", "doc2.htm"],
                    dates=["2022-06-01", "2022-06-01"],
                ),
            },
            texts={
                "a": "will begin trading under the symbol META",
                "b": "will begin trading under the symbol META",
            },
        )
        patch_client(fake)
        out = tmp_path / "out.json"
        _run_main(monkeypatch, [
            "--identifiers", str(path),
            "--output", str(out),
        ])
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["actions"]) == 1

    def test_missing_primary_doc_is_skipped(self, tmp_path, monkeypatch, patch_client):
        path = _write_identifiers(tmp_path, [
            {"isin": "US30303M1027", "ticker": "FB", "cik": "1326801"},
        ])
        fake = FakeSECClient(
            submissions={
                "0001326801": _fake_submissions(
                    forms=["8-K"],
                    accessions=["acc"],
                    docs=[""],  # empty primary document
                    dates=["2022-06-01"],
                ),
            },
            texts={"acc": "will begin trading under the symbol META"},
        )
        patch_client(fake)
        out = tmp_path / "out.json"
        code = _run_main(monkeypatch, [
            "--identifiers", str(path),
            "--output", str(out),
        ])
        assert code == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["actions"] == []
        # The filing text was never even requested.
        assert fake.get_filing_text_calls == []

    def test_actions_are_sorted_by_effective_date(self, tmp_path, monkeypatch, patch_client):
        path = _write_identifiers(tmp_path, [
            {"isin": "US30303M1027", "ticker": "FB", "cik": "1326801"},
        ])
        fake = FakeSECClient(
            submissions={
                "0001326801": _fake_submissions(
                    forms=["8-K", "8-K"],
                    accessions=["late", "early"],
                    docs=["late.htm", "early.htm"],
                    dates=["2024-06-01", "2024-01-01"],
                ),
            },
            texts={
                "late": "effective June 1, 2024, will begin trading "
                        "under the symbol META",
                "early": "effective January 1, 2024, will begin trading "
                         "under the symbol XYZW",
            },
        )
        patch_client(fake)
        out = tmp_path / "out.json"
        _run_main(monkeypatch, [
            "--identifiers", str(path),
            "--output", str(out),
        ])
        data = json.loads(out.read_text(encoding="utf-8"))
        dates = [a["dates"]["effective_date"] for a in data["actions"]]
        assert dates == sorted(dates)