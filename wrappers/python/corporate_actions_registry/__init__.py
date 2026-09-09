"""
Corporate Actions Registry Python Wrapper

This package provides a clean, idiomatic Python interface to the
Corporate Actions Registry (actions.json). It exposes a single main
class, `CorporateActionsRegistry`, which loads the JSON file and offers
fast lookup methods.

Example:
    from corporate_actions_registry import CorporateActionsRegistry

    registry = CorporateActionsRegistry("actions.json")
    actions = registry.by_isin("US0378331005")
    for action in actions:
        print(action["action_type"], action["dates"]["ex_date"])

The wrapper is designed to be lightweight, dependency-free, and to
mirror the API style of the other QuantOS registry wrappers
(iso4217-registry, exchange-calendar-registry, asset-identifiers-registry).
"""

from .registry import CorporateActionsRegistry

__version__ = "1.0.0"
__all__ = ["CorporateActionsRegistry"]