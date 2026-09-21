"""Tests for examples/backtest_adjustment.py.

The script historically applied the registry's split multiplier to
prices that yfinance had already split-adjusted, inflating the NVDA
Jan-Jul 2024 return from ~+157% to ~+2465% and labeling the wrong
number CORRECT. These tests pin the corrected behavior:

  - compute_price_return and compute_total_return are unit-tested.
  - The source file contains no references to the removed functions
    and no misleading labels (CORRECT, NOTE, Split-adjusted).
  - The CLI produces the two-return output on a live fetch (marked
    `network`, skipped in CI with `-m "not network"`).

The CLI is invoked with `--isin US67066G1040` so the tests do not
require the private Asset Identifiers registry.
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
pytest.importorskip("yfinance", reason="requires yfinance")

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "examples" / "backtest_adjustment.py"


# ---------------------------------------------------------------------------
# Import the module under test
#
# The script is in examples/, not on sys.path. Add it, then import by name.
# ---------------------------------------------------------------------------
sys.path.insert(0, str(REPO_ROOT / "examples"))
import backtest_adjustment as ba  # noqa: E402


# ---------------------------------------------------------------------------
# Fake action objects
# ---------------------------------------------------------------------------

class FakeDates:
    def __init__(self, ex_date=None):
        self.ex_date = ex_date


class FakeAction:
    """Minimal duck-typed Action: only the fields compute_total_return reads."""
    def __init__(self, action_type, ex_date=None, amount=None, ratio=None):
        self.action_type = action_type
        self.dates = FakeDates(ex_date)
        self.amount = amount
        self.ratio = ratio


# ---------------------------------------------------------------------------
# compute_price_return
# ---------------------------------------------------------------------------

class TestComputePriceReturn:

    def test_simple_gain(self):
        assert ba.compute_price_return(100.0, 150.0) == pytest.approx(50.0)

    def test_simple_loss(self):
        assert ba.compute_price_return(100.0, 80.0) == pytest.approx(-20.0)

    def test_flat(self):
        assert ba.compute_price_return(100.0, 100.0) == pytest.approx(0.0)

    def test_double(self):
        assert ba.compute_price_return(50.0, 100.0) == pytest.approx(100.0)

    def test_nvda_2024_jan_jul(self):
        # 48.168 -> 123.54, the values yfinance returns for NVDA.
        ret = ba.compute_price_return(48.168, 123.54)
        assert 155 < ret < 158

    def test_zero_first_price_raises(self):
        # Division by zero. Documented behavior is ZeroDivisionError; if
        # the function later guards against it, update this test.
        with pytest.raises(ZeroDivisionError):
            ba.compute_price_return(0.0, 100.0)


# ---------------------------------------------------------------------------
# compute_total_return
# ---------------------------------------------------------------------------

class TestComputeTotalReturn:

    def test_no_actions_equals_price_return(self):
        ret = ba.compute_total_return(
            100.0, 150.0, [],
            date(2024, 1, 1), date(2024, 12, 31),
        )
        assert ret == pytest.approx(50.0)

    def test_single_dividend_in_range(self):
        actions = [FakeAction("DIVIDEND", "2024-06-15", 1.00)]
        ret = ba.compute_total_return(
            100.0, 150.0, actions,
            date(2024, 1, 1), date(2024, 12, 31),
        )
        # (150 + 1) / 100 - 1 = 51%
        assert ret == pytest.approx(51.0)

    def test_special_dividend_counted(self):
        actions = [FakeAction("SPECIAL_DIVIDEND", "2024-06-15", 2.00)]
        ret = ba.compute_total_return(
            100.0, 150.0, actions,
            date(2024, 1, 1), date(2024, 12, 31),
        )
        assert ret == pytest.approx(52.0)

    def test_multiple_dividends_sum(self):
        actions = [
            FakeAction("DIVIDEND", "2024-03-15", 0.50),
            FakeAction("DIVIDEND", "2024-06-15", 0.50),
            FakeAction("SPECIAL_DIVIDEND", "2024-09-15", 1.00),
        ]
        ret = ba.compute_total_return(
            100.0, 150.0, actions,
            date(2024, 1, 1), date(2024, 12, 31),
        )
        # (150 + 2) / 100 - 1 = 52%
        assert ret == pytest.approx(52.0)

    def test_dividend_outside_range_ignored(self):
        actions = [FakeAction("DIVIDEND", "2023-06-15", 5.00)]
        ret = ba.compute_total_return(
            100.0, 150.0, actions,
            date(2024, 1, 1), date(2024, 12, 31),
        )
        assert ret == pytest.approx(50.0)

    def test_dividend_on_start_bound_included(self):
        actions = [FakeAction("DIVIDEND", "2024-01-01", 1.00)]
        ret = ba.compute_total_return(
            100.0, 150.0, actions,
            date(2024, 1, 1), date(2024, 12, 31),
        )
        assert ret == pytest.approx(51.0)

    def test_dividend_on_end_bound_included(self):
        actions = [FakeAction("DIVIDEND", "2024-12-31", 1.00)]
        ret = ba.compute_total_return(
            100.0, 150.0, actions,
            date(2024, 1, 1), date(2024, 12, 31),
        )
        assert ret == pytest.approx(51.0)

    def test_split_ignored(self):
        actions = [FakeAction("SPLIT", "2024-06-15", None, ratio="10:1")]
        ret = ba.compute_total_return(
            100.0, 150.0, actions,
            date(2024, 1, 1), date(2024, 12, 31),
        )
        assert ret == pytest.approx(50.0)

    def test_symbol_change_ignored(self):
        actions = [FakeAction("SYMBOL_CHANGE", "2024-06-15")]
        ret = ba.compute_total_return(
            100.0, 150.0, actions,
            date(2024, 1, 1), date(2024, 12, 31),
        )
        assert ret == pytest.approx(50.0)

    def test_action_missing_ex_date_ignored(self):
        actions = [FakeAction("DIVIDEND", ex_date=None, amount=1.00)]
        ret = ba.compute_total_return(
            100.0, 150.0, actions,
            date(2024, 1, 1), date(2024, 12, 31),
        )
        assert ret == pytest.approx(50.0)

    def test_action_missing_dates_object_ignored(self):
        class NoDates:
            action_type = "DIVIDEND"
            dates = None
            amount = 1.00
        ret = ba.compute_total_return(
            100.0, 150.0, [NoDates()],
            date(2024, 1, 1), date(2024, 12, 31),
        )
        assert ret == pytest.approx(50.0)

    def test_zero_amount_ignored(self):
        actions = [FakeAction("DIVIDEND", "2024-06-15", 0.0)]
        ret = ba.compute_total_return(
            100.0, 150.0, actions,
            date(2024, 1, 1), date(2024, 12, 31),
        )
        assert ret == pytest.approx(50.0)

    def test_none_amount_ignored(self):
        actions = [FakeAction("DIVIDEND", "2024-06-15", None)]
        ret = ba.compute_total_return(
            100.0, 150.0, actions,
            date(2024, 1, 1), date(2024, 12, 31),
        )
        assert ret == pytest.approx(50.0)

    def test_malformed_ex_date_ignored(self):
        actions = [FakeAction("DIVIDEND", "not-a-date", 1.00)]
        ret = ba.compute_total_return(
            100.0, 150.0, actions,
            date(2024, 1, 1), date(2024, 12, 31),
        )
        assert ret == pytest.approx(50.0)

    def test_nvda_2024_jan_jul_matches_price_return_plus_cents(self):
        # Two small dividends in the window, total 0.014 per share.
        actions = [
            FakeAction("DIVIDEND", "2024-03-12", 0.004),
            FakeAction("DIVIDEND", "2024-06-11", 0.010),
        ]
        price = ba.compute_price_return(48.168, 123.54)
        total = ba.compute_total_return(
            48.168, 123.54, actions,
            date(2024, 1, 2), date(2024, 7, 1),
        )
        assert total > price
        assert total - price < 0.1


# ---------------------------------------------------------------------------
# in_range
# ---------------------------------------------------------------------------

class TestInRange:

    def test_in_range(self):
        assert ba.in_range("2024-06-15", date(2024, 1, 1), date(2024, 12, 31))

    def test_start_bound_inclusive(self):
        assert ba.in_range("2024-01-01", date(2024, 1, 1), date(2024, 12, 31))

    def test_end_bound_inclusive(self):
        assert ba.in_range("2024-12-31", date(2024, 1, 1), date(2024, 12, 31))

    def test_before_range(self):
        assert not ba.in_range("2023-12-31", date(2024, 1, 1), date(2024, 12, 31))

    def test_after_range(self):
        assert not ba.in_range("2025-01-01", date(2024, 1, 1), date(2024, 12, 31))

    def test_empty_string_returns_false(self):
        assert not ba.in_range("", date(2024, 1, 1), date(2024, 12, 31))

    def test_none_returns_false(self):
        assert not ba.in_range(None, date(2024, 1, 1), date(2024, 12, 31))

    def test_malformed_returns_false(self):
        assert not ba.in_range("2024-13-99", date(2024, 1, 1), date(2024, 12, 31))


# ---------------------------------------------------------------------------
# dedupe_actions
# ---------------------------------------------------------------------------

class TestDedupeActions:

    def test_empty(self):
        assert ba.dedupe_actions([]) == []

    def test_single(self):
        a = FakeAction("DIVIDEND", "2024-06-15", 0.25)
        assert ba.dedupe_actions([a]) == [a]

    def test_distinct_actions_kept(self):
        actions = [
            FakeAction("DIVIDEND", "2024-06-15", 0.25),
            FakeAction("DIVIDEND", "2024-09-15", 0.25),
        ]
        assert len(ba.dedupe_actions(actions)) == 2

    def test_same_key_dedupes(self):
        actions = [
            FakeAction("DIVIDEND", "2024-06-15", 0.25),
            FakeAction("DIVIDEND", "2024-06-15", 0.25),
        ]
        assert len(ba.dedupe_actions(actions)) == 1

    def test_different_amount_not_deduped(self):
        actions = [
            FakeAction("DIVIDEND", "2024-06-15", 0.25),
            FakeAction("DIVIDEND", "2024-06-15", 0.26),
        ]
        assert len(ba.dedupe_actions(actions)) == 2

    def test_action_without_ex_date_kept(self):
        a = FakeAction("SYMBOL_CHANGE", ex_date=None)
        assert ba.dedupe_actions([a]) == [a]

    def test_missing_dates_object_kept(self):
        class NoDates:
            action_type = "SPLIT"
            dates = None
            ratio = "10:1"
            amount = None
        assert len(ba.dedupe_actions([NoDates()])) == 1


# ---------------------------------------------------------------------------
# to_date
# ---------------------------------------------------------------------------

class TestToDate:

    def test_valid(self):
        assert ba.to_date("2024-06-10") == date(2024, 6, 10)

    def test_leap_day(self):
        assert ba.to_date("2024-02-29") == date(2024, 2, 29)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            ba.to_date("not-a-date")

    def test_wrong_format_raises(self):
        with pytest.raises(ValueError):
            ba.to_date("06/10/2024")


# ---------------------------------------------------------------------------
# find_actions_file
# ---------------------------------------------------------------------------

class TestFindActionsFile:

    def test_cli_path_wins(self, tmp_path):
        f = tmp_path / "custom.json"
        f.write_text("{}", encoding="utf-8")
        assert ba.find_actions_file(str(f)) == f

    def test_missing_cli_path_exits_2(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            ba.find_actions_file(str(tmp_path / "nope.json"))
        assert exc.value.code == 2

    def test_cwd_file_found(self, tmp_path, monkeypatch):
        f = tmp_path / "actions.json"
        f.write_text("{}", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert ba.find_actions_file(None) == f


# ---------------------------------------------------------------------------
# resolve_isin
# ---------------------------------------------------------------------------

class TestResolveIsin:

    def test_explicit_isin_short_circuits(self):
        # No registry access needed because the explicit ISIN is returned
        # before any lookup.
        assert ba.resolve_isin("NVDA", "XNAS", "US67066G1040") == "US67066G1040"

    def test_explicit_isin_ignores_ticker(self):
        assert ba.resolve_isin("ANYTHING", "ANYEX", "US0378331005") == "US0378331005"


# ---------------------------------------------------------------------------
# Source-level guards: the removed functions and labels must stay removed
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def example_source():
    """The example's source text, read once per module."""
    return EXAMPLE.read_text(encoding="utf-8")


class TestSourceGuards:
    """Static checks that the old code is gone for good.

    These guard against a future paste that reintroduces the double-
    adjustment path or the misleading labels. They run without network
    or the wrapper.
    """

    @pytest.mark.parametrize("forbidden", [
        "compute_naive_return",
        "adjust_prices_for_actions",
        "compute_split_adjusted_return",
        "Split-adjusted price return",
        "Raw price return",
        "CORRECT",
    ])
    def test_removed_identifier_absent(self, example_source, forbidden):
        assert forbidden not in example_source, (
            f"{forbidden!r} reappeared in backtest_adjustment.py"
        )

    def test_closing_note_absent(self, example_source):
        # The NOTE contradicted the code and has been removed.
        assert "Use a vendor with unadjusted prices" not in example_source

    def test_price_return_label_present(self, example_source):
        assert "Price return:" in example_source

    def test_total_return_label_present(self, example_source):
        assert "Total return (price + dividends):" in example_source


# ---------------------------------------------------------------------------
# CLI end-to-end (network)
# ---------------------------------------------------------------------------

def _run_cli(*args):
    return subprocess.run(
        [sys.executable, str(EXAMPLE), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


@pytest.mark.network
class TestCliEndToEnd:

    def test_nvda_price_return_in_expected_range(self):
        result = _run_cli(
            "--ticker", "NVDA",
            "--isin", "US67066G1040",
            "--start", "2024-01-02",
            "--end", "2024-07-01",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        m = re.search(r"Price return:\s+([+-]?\d+\.\d+)%", result.stdout)
        assert m, f"no price return in output:\n{result.stdout}"
        pct = float(m.group(1))
        assert 150 < pct < 165, f"unexpected price return: {pct}%"

    def test_output_does_not_contain_removed_labels(self):
        result = _run_cli(
            "--ticker", "NVDA",
            "--isin", "US67066G1040",
            "--start", "2024-01-02",
            "--end", "2024-07-01",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        for forbidden in (
            "Split-adjusted price return",
            "Raw price return",
            "CORRECT",
            "Use a vendor with unadjusted prices",
        ):
            assert forbidden not in result.stdout, (
                f"{forbidden!r} appears in output:\n{result.stdout}"
            )

    def test_total_return_is_close_to_price_return(self):
        # NVDA paid two small dividends in the window; total must exceed
        # price return but by less than 1 percentage point.
        result = _run_cli(
            "--ticker", "NVDA",
            "--isin", "US67066G1040",
            "--start", "2024-01-02",
            "--end", "2024-07-01",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        price_m = re.search(r"Price return:\s+([+-]?\d+\.\d+)%", result.stdout)
        total_m = re.search(r"Total return[^:]*:\s+([+-]?\d+\.\d+)%", result.stdout)
        assert price_m and total_m, result.stdout
        price = float(price_m.group(1))
        total = float(total_m.group(1))
        assert total >= price
        assert total - price < 1.0

    def test_start_after_end_exits_2(self):
        result = _run_cli(
            "--ticker", "NVDA",
            "--isin", "US67066G1040",
            "--start", "2024-07-01",
            "--end", "2024-01-02",
        )
        assert result.returncode == 2
        assert "start must be before end" in result.stderr.lower()

    def test_missing_actions_file_exits_2(self):
        result = _run_cli(
            "--ticker", "NVDA",
            "--isin", "US67066G1040",
            "--start", "2024-01-02",
            "--end", "2024-07-01",
            "--actions", "/nonexistent/actions.json",
        )
        assert result.returncode == 2
        assert "not found" in result.stderr.lower()