"""
Main registry class for the Corporate Actions Registry.

Loads actions.json and provides fast lookup methods for actions by
ISIN, action ID, action type, and date range. The class is dependency-free
and uses the data models from .models for typed access.

Typical usage:
    from corporate_actions_registry import CorporateActionsRegistry

    registry = CorporateActionsRegistry("actions.json")
    aapl_actions = registry.by_isin("US0378331005")
    splits = registry.by_action_type("SPLIT")
"""

import json
import os
from typing import Any, Dict, List, Optional, Union
import copy

from .models import Action, RegistryMeta


class CorporateActionsRegistry:
    """
    A convenient interface to the Corporate Actions Registry data.

    The registry is loaded once into memory and then queried repeatedly
    without re-reading the file.

    Attributes:
        actions (List[Action]): List of all actions, parsed into Action objects.
        meta (RegistryMeta): Metadata about the registry file.
        _index_by_isin (Dict[str, List[Action]]): Precomputed index by ISIN.
        _index_by_type (Dict[str, List[Action]]): Precomputed index by action_type.
        _index_by_id (Dict[str, Action]): Precomputed index by action_id.
    """

    def __init__(
        self,
        actions_path: Optional[str] = None,
        actions_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize the registry from a file path or a pre-loaded dict.

        Either `actions_path` or `actions_data` must be provided.
        If both are provided, `actions_data` takes precedence.

        Args:
            actions_path: Path to actions.json.
            actions_data: Already loaded JSON data as a dict.

        Raises:
            FileNotFoundError: If actions_path does not exist.
            ValueError: If the JSON is invalid or missing required keys.
        """
        if actions_data is not None:
            raw_data = actions_data
        elif actions_path is not None:
            with open(actions_path, "r", encoding="utf-8-sig") as f:
                raw_data = json.load(f)
        else:
            raise ValueError("Either actions_path or actions_data must be provided.")

        if not isinstance(raw_data, dict) or "actions" not in raw_data:
            raise ValueError("Invalid actions data: expected dict with 'actions' key.")

        if not isinstance(raw_data["actions"], list):
            raise ValueError(
                "Invalid actions data: 'actions' must be a list, got "
                f"{type(raw_data['actions']).__name__}"
            )

        for i, item in enumerate(raw_data["actions"]):
            if not isinstance(item, dict):
                raise ValueError(
                    f"Invalid actions data: action at index {i} is not "
                    f"an object, got {type(item).__name__}"
                )

        self.meta = RegistryMeta.from_dict(raw_data.get("meta"))
        self.actions: List[Action] = [
            Action.from_dict(item) for item in raw_data["actions"]
        ]

        self._build_indexes()

    def _build_indexes(self) -> None:
        """Build in-memory indexes for fast lookups."""
        self._index_by_isin: Dict[str, List[Action]] = {}
        self._index_by_type: Dict[str, List[Action]] = {}
        self._index_by_id: Dict[str, Action] = {}

        for action in self.actions:
            if action.action_id:
                self._index_by_id[action.action_id] = action

            if action.isin:
                self._index_by_isin.setdefault(action.isin, []).append(action)

            if action.action_type:
                self._index_by_type.setdefault(action.action_type, []).append(action)

    # ------------------------------------------------------------------
    # Lookup methods
    # ------------------------------------------------------------------
    def by_isin(self, isin: str) -> List[Action]:
        """
        Return all actions for a given ISIN.

        Args:
            isin: The ISIN of the instrument (e.g., 'US0378331005').

        Returns:
            List of Action objects, possibly empty.
        """
        return [copy.deepcopy(a) for a in self._index_by_isin.get(isin, [])]
    
    def by_action_id(self, action_id: str) -> Optional[Action]:
        action = self._index_by_id.get(action_id)
        if action is None:
            return None
        # Return a copy so a caller cannot mutate the registry's internal
        # state by editing the returned object.
        return [copy.deepcopy(a) for a in self._index_by_type.get(action_type, [])]
    
    def by_action_type(self, action_type: str) -> List[Action]:
        """
        Return all actions of a given type (e.g., 'SPLIT', 'DIVIDEND').

        Args:
            action_type: The action type string.

        Returns:
            List of Action objects, possibly empty.
        """
        return list(self._index_by_type.get(action_type, []))

    _VALID_DATE_FIELDS = ("announcement", "ex_date", "record_date", "effective_date")

    def by_date_range(self, start_date=None, end_date=None, date_field="ex_date"):
        """Return actions whose `date_field` falls in [start_date, end_date].

        Bounds are inclusive. Pass None (or omit) for an open bound.
        Actions lacking `date_field` are skipped silently.

        Raises ValueError if `date_field` is not one of the four valid names.
        Results are sorted by the requested field, then by action_id.
        """
        if date_field not in self._VALID_DATE_FIELDS:
            raise ValueError(
                f"invalid date_field {date_field!r}; "
                f"expected one of {sorted(self._VALID_DATE_FIELDS)}"
            )
        result = []
        for action in self.actions:
            value = getattr(action.dates, date_field, None)
            if value is None:
                continue
            if start_date and value < start_date:
                continue
            if end_date and value > end_date:
                continue
            result.append(action)
        result.sort(key=lambda a: (
            getattr(a.dates, date_field, "") or "",
            a.action_id or "",
        ))
        return [copy.deepcopy(a) for a in result]
    
    def all_action_types(self) -> List[str]:
        """Return a sorted list of unique action types in the registry."""
        return sorted(self._index_by_type.keys())

    def count(self) -> int:
        """Return total number of actions."""
        return len(self.actions)

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the entire registry back to a dictionary.

        Returns:
            Dict with 'meta' and 'actions' keys.
        """
        return {
            "meta": self.meta.to_dict(),
            "actions": [action.to_dict() for action in self.actions],
        }

    def save(self, path: str) -> None:
        """
        Save the registry to a JSON file.

        Args:
            path: Destination file path.
        """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    def __len__(self) -> int:
        """Return number of actions."""
        return len(self.actions)

    def __repr__(self) -> str:
        return f"<CorporateActionsRegistry actions={len(self.actions)}>"