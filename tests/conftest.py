"""Shared pytest fixtures and factories.

`make_split_action`, `make_dividend_action`, and `make_symbol_change_action`
build canonical actions that satisfy every validation layer: schema,
temporal, arithmetic, provenance, redistribution, and coverage.

Why this exists: when `redistribution` became required, seven test files
had hand-built actions that failed. A shared factory means that class of
failure happens once, not per-file. Every future schema or validator
change updates one factory, not N files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def make_split_action(**overrides) -> dict:
    """A valid SPLIT action. Every field needed by every layer."""
    action = {
        "isin": "US67066G1040",
        "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
        "action_type": "SPLIT",
        "ratio": "10:1",
        "redistribution": "secondary-source",
        "dates": {
            "announcement": "2024-05-22",
            "ex_date": "2024-06-10",
            "record_date": "2024-06-07",
            "effective_date": "2024-06-10",
        },
        "status": "COMPLETED",
        "provenance": {
            "source": "Yahoo Finance (yfinance)",
            "source_url": "https://finance.yahoo.com/quote/NVDA/history",
        },
        "impact": {
            "price_multiplier": 0.1,
            "share_multiplier": 10.0,
            "cash_adjustment": 0.0,
        },
    }
    action.update(overrides)
    return action


def make_dividend_action(**overrides) -> dict:
    """A valid DIVIDEND action."""
    action = {
        "isin": "US0378331005",
        "action_id": "US0378331005-DIVIDEND-2024-05-23-0.2500",
        "action_type": "DIVIDEND",
        "amount": 0.25,
        "currency": "USD",
        "redistribution": "secondary-source",
        "dates": {
            "announcement": "2024-05-02",
            "ex_date": "2024-05-16",
            "record_date": "2024-05-17",
            "effective_date": "2024-05-23",
        },
        "status": "COMPLETED",
        "provenance": {
            "source": "Yahoo Finance (yfinance)",
            "source_url": "https://finance.yahoo.com/quote/AAPL/history",
        },
        "impact": {
            "price_multiplier": 1.0,
            "share_multiplier": 1.0,
            "cash_adjustment": 0.25,
        },
    }
    action.update(overrides)
    return action


def make_symbol_change_action(**overrides) -> dict:
    """A valid SYMBOL_CHANGE action."""
    action = {
        "isin": "US30303M1027",
        "action_id": "US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL",
        "action_type": "SYMBOL_CHANGE",
        "redistribution": "facts-only",
        "dates": {
            "announcement": "2022-06-09",
            "effective_date": "2022-06-09",
        },
        "status": "COMPLETED",
        "provenance": {
            "source": "Meta Platforms press release",
            "source_url": "https://about.fb.com/news/2022/06/facebook-is-now-meta/",
        },
        "impact": {
            "price_multiplier": 1.0,
            "share_multiplier": 1.0,
            "cash_adjustment": 0.0,
        },
    }
    action.update(overrides)
    return action


@pytest.fixture
def valid_split():
    return make_split_action()


@pytest.fixture
def valid_dividend():
    return make_dividend_action()


@pytest.fixture
def valid_symbol_change():
    return make_symbol_change_action()