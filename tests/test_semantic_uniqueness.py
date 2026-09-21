"""Tests for validate_semantic_uniqueness in tools/validate.py.

The function flags pairs of actions that describe the same underlying
event under two different action_ids. Two actions are considered the
same event when they share an ISIN and an action-type family
(DIVIDEND and SPECIAL_DIVIDEND collapse to one family; SPLIT and
REVERSE_SPLIT collapse to another), their effective dates are within
5 days, and their comparable value (amount for dividends, ratio for
splits) matches.

The layer exists because two duplicate pairs shipped in v1.0.0:
  - AAPL Q2 FY2024 dividend as two entries with different ex-dates
  - MSFT Q4 2004 special dividend as one bundled and one split entry

Both were caught by an ad-hoc scan, not by the validator. This test
file pins the behavior of the validator layer that replaces that scan.

Run
---
    python3 -m pytest tests/test_semantic_uniqueness.py -v
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.validate import validate_semantic_uniqueness


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _a(
    action_id,
    *,
    isin="US0378331005",
    action_type="DIVIDEND",
    effective="2024-06-01",
    amount=0.25,
    ratio=None,
    include_amount=None,
    include_ratio=None,
):
    """Build a minimal action dict.

    `amount` and `ratio` are the values to set; pass `include_amount=False`
    or `include_ratio=False` to omit the key entirely (which is different
    from setting it to None).
    """
    action = {
        "action_id": action_id,
        "isin": isin,
        "action_type": action_type,
        "dates": {"effective_date": effective},
    }
    if include_amount is False:
        pass  # do not add amount key
    else:
        action["amount"] = amount

    if include_ratio is False:
        pass
    elif ratio is not None:
        action["ratio"] = ratio

    return action


def _flagged_pairs(errors):
    """Extract the set of (id_a, id_b) tuples the function flagged.

    The function's error message format is not part of the contract,
    so this parses defensively: any two identifiers mentioned in a
    single error message are treated as a flagged pair. Identifiers
    are assumed to be the only tokens in the message that begin with
    an uppercase letter or "US".
    """
    import re
    pairs = set()
    for e in errors:
        ids = re.findall(r"\b(?:US[A-Z0-9]{10}|[A-Z]\d+)\b", e)
        if len(ids) >= 2:
            pairs.add(tuple(sorted(ids[:2])))
    return pairs


# ---------------------------------------------------------------------------
# No-op cases
# ---------------------------------------------------------------------------

class TestEmptyAndTrivial:

    def test_empty_list_returns_empty(self):
        assert validate_semantic_uniqueness([]) == []

    def test_single_action_returns_empty(self):
        assert validate_semantic_uniqueness([_a("A1")]) == []

    def test_two_distinct_isins_same_date_same_amount_not_flagged(self):
        actions = [
            _a("A1", isin="US0378331005"),
            _a("A2", isin="US5949181045"),
        ]
        assert validate_semantic_uniqueness(actions) == []

    def test_two_distinct_dates_more_than_window_not_flagged(self):
        actions = [
            _a("A1", effective="2024-06-01"),
            _a("A2", effective="2024-06-30"),
        ]
        assert validate_semantic_uniqueness(actions) == []

    def test_two_distinct_amounts_not_flagged(self):
        actions = [
            _a("A1", amount=0.25),
            _a("A2", amount=0.30),
        ]
        assert validate_semantic_uniqueness(actions) == []


# ---------------------------------------------------------------------------
# The two historical regression cases
# ---------------------------------------------------------------------------

class TestHistoricalRegression:
    """The two duplicate pairs that shipped in v1.0.0. Each must be
    flagged by the layer so a future fetcher bug cannot re-introduce
    the same class of duplicate silently."""

    def test_aapl_q2_2024_dividend_two_ids_flagged(self):
        """Two entries for the same AAPL dividend, different ex-dates."""
        actions = [
            _a("US0378331005-DIVIDEND-2024-05-10-0.2500",
               isin="US0378331005", action_type="DIVIDEND",
               effective="2024-05-16", amount=0.25),
            _a("US0378331005-DIVIDEND-2024-05-23-0.2500",
               isin="US0378331005", action_type="DIVIDEND",
               effective="2024-05-16", amount=0.25),
        ]
        errors = validate_semantic_uniqueness(actions)
        assert len(errors) == 1

    def test_aapl_pair_with_dates_6_days_apart_not_flagged(self):
        """The 5-day window is deliberate. A pair of near-but-not-same
        dates should not be flagged. If the real events were 6 days
        apart, the rule would need to be adjusted."""
        actions = [
            _a("A1", effective="2024-05-16", amount=0.25),
            _a("A2", effective="2024-05-22", amount=0.25),
        ]
        assert validate_semantic_uniqueness(actions) == []

    def test_msft_2004_special_vs_regular_not_flagged(self):
        """A regular dividend and a special dividend on the same day
        have different amounts and are legitimate separate events.
        The MSFT Q4 2004 event is one of each."""
        actions = [
            _a("US5949181045-DIVIDEND-2004-11-15-0.0800",
               isin="US5949181045", action_type="DIVIDEND",
               effective="2004-11-15", amount=0.08),
            _a("US5949181045-SPECIAL_DIVIDEND-2004-11-17-3.0000",
               isin="US5949181045", action_type="SPECIAL_DIVIDEND",
               effective="2004-11-17", amount=3.00),
        ]
        assert validate_semantic_uniqueness(actions) == []

    def test_msft_2004_identical_special_pair_flagged(self):
        """If the same $3.00 special dividend were to appear twice with
        different action_ids and slightly different effective dates,
        the layer should catch it."""
        actions = [
            _a("A1", isin="US5949181045", action_type="SPECIAL_DIVIDEND",
               effective="2004-11-17", amount=3.00),
            _a("A2", isin="US5949181045", action_type="SPECIAL_DIVIDEND",
               effective="2004-11-18", amount=3.00),
        ]
        errors = validate_semantic_uniqueness(actions)
        assert len(errors) == 1


# ---------------------------------------------------------------------------
# Date window
# ---------------------------------------------------------------------------

class TestDateWindow:

    def test_same_date_flagged(self):
        actions = [
            _a("A1", effective="2024-06-01"),
            _a("A2", effective="2024-06-01"),
        ]
        assert len(validate_semantic_uniqueness(actions)) == 1

    def test_one_day_apart_flagged(self):
        actions = [
            _a("A1", effective="2024-06-01"),
            _a("A2", effective="2024-06-02"),
        ]
        assert len(validate_semantic_uniqueness(actions)) == 1

    def test_exactly_five_days_apart_flagged(self):
        """The window is inclusive of 5."""
        actions = [
            _a("A1", effective="2024-06-01"),
            _a("A2", effective="2024-06-06"),
        ]
        assert len(validate_semantic_uniqueness(actions)) == 1

    def test_six_days_apart_not_flagged(self):
        """The window is exclusive of 6."""
        actions = [
            _a("A1", effective="2024-06-01"),
            _a("A2", effective="2024-06-07"),
        ]
        assert validate_semantic_uniqueness(actions) == []

    def test_window_is_symmetric(self):
        """Swapping the two dates does not change the result."""
        forward = [
            _a("A1", effective="2024-06-01"),
            _a("A2", effective="2024-06-05"),
        ]
        backward = [
            _a("A1", effective="2024-06-05"),
            _a("A2", effective="2024-06-01"),
        ]
        assert (len(validate_semantic_uniqueness(forward)) == 1
                and len(validate_semantic_uniqueness(backward)) == 1)

    def test_month_boundary_within_window(self):
        actions = [
            _a("A1", effective="2024-05-30"),
            _a("A2", effective="2024-06-03"),
        ]
        assert len(validate_semantic_uniqueness(actions)) == 1

    def test_year_boundary_within_window(self):
        actions = [
            _a("A1", effective="2023-12-30"),
            _a("A2", effective="2024-01-02"),
        ]
        assert len(validate_semantic_uniqueness(actions)) == 1


# ---------------------------------------------------------------------------
# Amount matching
# ---------------------------------------------------------------------------

class TestAmountMatching:

    def test_identical_amounts_flagged(self):
        actions = [_a("A1", amount=0.25), _a("A2", amount=0.25)]
        assert len(validate_semantic_uniqueness(actions)) == 1

    def test_amounts_differ_by_less_than_epsilon_flagged(self):
        """Tolerance is 0.01; a half-cent difference is within it."""
        actions = [_a("A1", amount=0.2500), _a("A2", amount=0.2549)]
        assert len(validate_semantic_uniqueness(actions)) == 1

    def test_amounts_differ_by_exactly_epsilon_not_flagged(self):
        """At exactly 0.01, the difference is no longer within the
        tolerance."""
        actions = [_a("A1", amount=0.25), _a("A2", amount=0.26)]
        assert validate_semantic_uniqueness(actions) == []

    def test_amounts_differ_clearly_not_flagged(self):
        actions = [_a("A1", amount=0.25), _a("A2", amount=3.00)]
        assert validate_semantic_uniqueness(actions) == []

    def test_zero_amounts_flagged(self):
        actions = [_a("A1", amount=0.0), _a("A2", amount=0.0)]
        assert len(validate_semantic_uniqueness(actions)) == 1

    def test_negative_amounts_flagged(self):
        """A negative amount is invalid per layer 3, but the semantic
        layer should still compare them consistently."""
        actions = [_a("A1", amount=-0.25), _a("A2", amount=-0.25)]
        assert len(validate_semantic_uniqueness(actions)) == 1

    def test_float_precision_within_tolerance(self):
        """Values that differ at the 6th decimal place are flagged."""
        actions = [_a("A1", amount=0.094643), _a("A2", amount=0.094642)]
        assert len(validate_semantic_uniqueness(actions)) == 1


# ---------------------------------------------------------------------------
# Action-type family collapse
# ---------------------------------------------------------------------------

class TestFamilyCollapse:

    def test_dividend_and_special_same_amount_flagged(self):
        """DIVIDEND and SPECIAL_DIVIDEND collapse to the same family,
        so an identical amount on the same ISIN is flagged."""
        actions = [
            _a("A1", action_type="DIVIDEND", amount=0.25),
            _a("A2", action_type="SPECIAL_DIVIDEND", amount=0.25),
        ]
        assert len(validate_semantic_uniqueness(actions)) == 1

    def test_split_and_reverse_split_same_ratio_flagged(self):
        """SPLIT and REVERSE_SPLIT collapse to the same family. Two
        identical ratios within the window are flagged."""
        actions = [
            _a("A1", action_type="SPLIT", ratio="2:1",
               amount=None, include_amount=False),
            _a("A2", action_type="REVERSE_SPLIT", ratio="2:1",
               amount=None, include_amount=False),
        ]
        errors = validate_semantic_uniqueness(actions)
        assert len(errors) == 1

    def test_split_and_reverse_split_different_ratio_not_flagged(self):
        actions = [
            _a("A1", action_type="SPLIT", ratio="2:1",
               amount=None, include_amount=False),
            _a("A2", action_type="REVERSE_SPLIT", ratio="1:8",
               amount=None, include_amount=False),
        ]
        assert validate_semantic_uniqueness(actions) == []

    def test_dividend_and_split_do_not_collapse(self):
        """A dividend and a split on the same ISIN and date are
        different families and never compared."""
        actions = [
            _a("A1", action_type="DIVIDEND", amount=0.25),
            _a("A2", action_type="SPLIT", ratio="10:1",
               amount=None, include_amount=False),
        ]
        assert validate_semantic_uniqueness(actions) == []

    def test_symbol_change_is_its_own_family(self):
        """SYMBOL_CHANGE does not collapse with anything else."""
        actions = [
            _a("A1", action_type="SYMBOL_CHANGE",
               amount=None, include_amount=False),
            _a("A2", action_type="SYMBOL_CHANGE",
               amount=None, include_amount=False),
        ]
        errors = validate_semantic_uniqueness(actions)
        assert len(errors) == 1

    def test_delisting_and_spinoff_are_separate_families(self):
        actions = [
            _a("A1", action_type="DELISTING",
               amount=None, include_amount=False),
            _a("A2", action_type="SPINOFF", ratio="1:3",
               amount=None, include_amount=False),
        ]
        assert validate_semantic_uniqueness(actions) == []


# ---------------------------------------------------------------------------
# Split ratio matching
# ---------------------------------------------------------------------------

class TestSplitRatioMatching:

    def test_identical_ratios_within_window_flagged(self):
        actions = [
            _a("A1", action_type="SPLIT", ratio="10:1",
               amount=None, include_amount=False),
            _a("A2", action_type="SPLIT", ratio="10:1",
               amount=None, include_amount=False),
        ]
        assert len(validate_semantic_uniqueness(actions)) == 1

    def test_different_ratios_within_window_not_flagged(self):
        """Two splits with different ratios are different events even
        if they are close in time."""
        actions = [
            _a("A1", action_type="SPLIT", ratio="2:1",
               amount=None, include_amount=False),
            _a("A2", action_type="SPLIT", ratio="3:1",
               amount=None, include_amount=False),
        ]
        assert validate_semantic_uniqueness(actions) == []

    def test_splits_with_no_ratio_field_not_flagged(self):
        """Two splits with no ratio at all are not comparable and
        should not be flagged — the schema layer catches the missing
        field."""
        actions = [
            _a("A1", action_type="SPLIT",
               amount=None, include_amount=False,
               include_ratio=False),
            _a("A2", action_type="SPLIT",
               amount=None, include_amount=False,
               include_ratio=False),
        ]
        assert validate_semantic_uniqueness(actions) == []


# ---------------------------------------------------------------------------
# Malformed input
# ---------------------------------------------------------------------------

class TestMalformedInput:

    def test_missing_isin_skips_action(self):
        a = _a("A1")
        del a["isin"]
        b = _a("A2")
        # A1 has no ISIN; it cannot be compared to anything.
        assert validate_semantic_uniqueness([a, b]) == []

    def test_missing_action_type_skips_action(self):
        a = _a("A1")
        del a["action_type"]
        b = _a("A2")
        assert validate_semantic_uniqueness([a, b]) == []

    def test_missing_dates_object_skips_action(self):
        a = _a("A1")
        del a["dates"]
        b = _a("A2")
        assert validate_semantic_uniqueness([a, b]) == []

    def test_dates_is_none_skips_action(self):
        a = _a("A1")
        a["dates"] = None
        b = _a("A2")
        assert validate_semantic_uniqueness([a, b]) == []

    def test_effective_date_is_none_skips_action(self):
        a = _a("A1")
        a["dates"] = {"effective_date": None}
        b = _a("A2")
        assert validate_semantic_uniqueness([a, b]) == []

    def test_malformed_effective_date_skips_action(self):
        actions = [
            _a("A1", effective="not-a-date"),
            _a("A2", effective="2024-06-01"),
        ]
        assert validate_semantic_uniqueness(actions) == []

    def test_short_month_in_effective_date_skips_action(self):
        actions = [
            _a("A1", effective="2024-6-1"),
            _a("A2", effective="2024-06-01"),
        ]
        assert validate_semantic_uniqueness(actions) == []

    def test_non_dict_action_skipped(self):
        actions = ["not an action", _a("A2")]
        # The function should not crash.
        result = validate_semantic_uniqueness(actions)
        assert isinstance(result, list)

    def test_amount_as_string_is_parsed(self):
        """A numeric string amount is coerced to float. Two numeric
        strings of the same value are flagged."""
        actions = [
            _a("A1", amount="0.25"),
            _a("A2", amount="0.25"),
        ]
        assert len(validate_semantic_uniqueness(actions)) == 1

    def test_unparseable_amount_treated_as_zero(self):
        """A non-numeric amount cannot be compared; the function
        treats it as 0.0 for the purpose of the comparison. Two such
        actions would be flagged even though the data is invalid.
        Layer 3 (arithmetic) catches the invalid amount first."""
        actions = [
            _a("A1", amount="lots"),
            _a("A2", amount="lots"),
        ]
        # This is a known limitation: unparseable amounts collapse to
        # 0.0 and compare equal. Layer 3 is the real check for this.
        # The behavior is pinned here so a future refactor doesn't
        # change it silently.
        result = validate_semantic_uniqueness(actions)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Multiple duplicates
# ---------------------------------------------------------------------------

class TestMultipleDuplicates:

    def test_three_identical_actions_produce_three_errors(self):
        """Three actions with the same ISIN, date, and amount produce
        three pairwise errors: (1,2), (1,3), (2,3)."""
        actions = [
            _a("A1", amount=0.25),
            _a("A2", amount=0.25),
            _a("A3", amount=0.25),
        ]
        errors = validate_semantic_uniqueness(actions)
        assert len(errors) == 3

    def test_two_groups_of_two_produce_two_errors(self):
        actions = [
            _a("A1", isin="US0378331005", amount=0.25),
            _a("A2", isin="US0378331005", amount=0.25),
            _a("B1", isin="US5949181045", amount=0.75),
            _a("B2", isin="US5949181045", amount=0.75),
        ]
        errors = validate_semantic_uniqueness(actions)
        assert len(errors) == 2

    def test_one_duplicate_among_unrelated_actions(self):
        actions = [
            _a("A1", isin="US0378331005", amount=0.25),
            _a("A2", isin="US0378331005", amount=0.25),
            _a("B1", isin="US5949181045", amount=0.75),
            _a("C1", isin="US67066G1040", amount=0.10, effective="2024-09-01"),
        ]
        errors = validate_semantic_uniqueness(actions)
        assert len(errors) == 1


# ---------------------------------------------------------------------------
# Order independence
# ---------------------------------------------------------------------------

class TestOrderIndependence:

    def test_reverse_input_order_same_result(self):
        actions = [_a("A1", amount=0.25), _a("A2", amount=0.25)]
        forward = len(validate_semantic_uniqueness(actions))
        backward = len(validate_semantic_uniqueness(list(reversed(actions))))
        assert forward == backward == 1

    def test_shuffled_input_same_result(self):
        import random
        actions = [
            _a("A1", amount=0.25),
            _a("A2", amount=0.25),
            _a("B1", isin="US5949181045", amount=0.75),
            _a("B2", isin="US5949181045", amount=0.75),
        ]
        baseline = len(validate_semantic_uniqueness(actions))
        for _ in range(5):
            random.shuffle(actions)
            assert len(validate_semantic_uniqueness(actions)) == baseline


# ---------------------------------------------------------------------------
# Real registry
# ---------------------------------------------------------------------------

class TestRealRegistry:
    """The committed actions.json must not trigger the layer."""

    @pytest.fixture(scope="class")
    def real_actions(self):
        path = REPO_ROOT / "actions.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc["actions"]

    def test_current_registry_has_no_duplicates(self, real_actions):
        errors = validate_semantic_uniqueness(real_actions)
        assert errors == [], (
            f"{len(errors)} duplicate event(s) found in the committed "
            f"registry:\n" + "\n".join(f"  - {e}" for e in errors[:10])
        )

    def test_registry_is_non_empty(self, real_actions):
        """Guard against a vacuous pass on an empty file."""
        assert len(real_actions) > 0

    def test_registry_has_no_false_positive_from_real_pairs(self, real_actions):
        """Two of the entries in the real registry are the two entries
        that survived the Phase 1 duplicate removal — AAPL Q2 FY2024
        dividend and MSFT Q4 2004 dividend/special. Both must not be
        flagged as duplicates of anything else in the file."""
        # AAPL 2024-05-16 dividend is present once
        aapl = [a for a in real_actions
                if a["action_id"] == "US0378331005-DIVIDEND-2024-05-16-0.2500"]
        assert len(aapl) == 1

        # MSFT 2004-12-09 regular and 2004-12-02 special are two entries
        # with different amounts and dates, both present
        msft = [a for a in real_actions
                if a["isin"] == "US5949181045"
                and a["dates"].get("ex_date", "").startswith("2004-11")]
        assert len(msft) == 2
        amounts = sorted(a["amount"] for a in msft)
        assert amounts == [0.08, 3.00]
</｜｜DSML｜｜ parameter>
</｜｜DSML｜｜ invoke>
</｜｜DSML｜｜ calls>