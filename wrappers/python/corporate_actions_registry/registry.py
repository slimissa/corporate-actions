"""
Main registry class for the Corporate Actions Registry.

Loads actions.json and provides fast lookup methods for actions by
ISIN, action ID, action type, ticker, and date range. The class is
dependency-free and uses the data models from .models for typed access.

Typical usage:
    from corporate_actions_registry import CorporateActionsRegistry

    registry = CorporateActionsRegistry("actions.json")
    aapl_actions = registry.by_isin("US0378331005")
    splits = registry.by_action_type("SPLIT")
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List, Optional

from .models import Action, RegistryMeta


# ---------------------------------------------------------------------------
# Exported constants (wrapper contract section 4.9)
# ---------------------------------------------------------------------------

DEFAULT_DATE_FIELD = "ex_date"

VALID_DATE_FIELDS = (
    "announcement",
    "ex_date",
    "record_date",
    "effective_date",
)


# ---------------------------------------------------------------------------
# Ticker index: module-level cache keyed by resolved path
#
# A single dict keyed by path means a caller who passes an explicit
# identifiers_path gets a fresh index for that path, and a caller who
# relies on the environment gets the index for whichever path the
# environment resolves to. Paths are resolved to absolute form before
# use so two equivalent paths hit the same cache slot.
# ---------------------------------------------------------------------------

_TICKER_INDEX_CACHE: Dict[str, Dict[tuple, str]] = {}


def _resolve_identifiers_path(explicit: Optional[str]) -> str:
    """Return an absolute path to identifiers.json.

    Priority:
      1. Explicit argument
      2. $CORP_ACTIONS_IDENTIFIERS_PATH
      3. $LAS_DATA_HOME/identifiers.json

    Raises RuntimeError when none is available. See the wrapper contract
    section 4.8 for the message format.
    """
    if explicit:
        return os.path.abspath(explicit)

    env_path = os.environ.get("CORP_ACTIONS_IDENTIFIERS_PATH")
    if env_path:
        return os.path.abspath(env_path)

    las_home = os.environ.get("LAS_DATA_HOME")
    if las_home:
        return os.path.abspath(os.path.join(las_home, "identifiers.json"))

    raise RuntimeError(
        "Cannot resolve ticker: neither CORP_ACTIONS_IDENTIFIERS_PATH "
        "nor LAS_DATA_HOME is set, and no identifiers_path was provided."
    )


def _build_ticker_index(path: str) -> Dict[tuple, str]:
    """Load identifiers.json and return {(TICKER, EXCHANGE): ISIN}.

    The result is cached per absolute path. A missing file raises
    RuntimeError naming the two environment variables that would fix it.
    """
    abs_path = os.path.abspath(path)
    cached = _TICKER_INDEX_CACHE.get(abs_path)
    if cached is not None:
        return cached

    try:
        with open(abs_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Cannot resolve ticker: {abs_path} not found. "
            f"Set CORP_ACTIONS_IDENTIFIERS_PATH or LAS_DATA_HOME."
        ) from e

    instruments = data.get("instruments") or []
    index: Dict[tuple, str] = {}
    for inst in instruments:
        if not isinstance(inst, dict):
            continue
        t = inst.get("ticker")
        x = inst.get("exchange")
        i = inst.get("isin")
        if t and x and i:
            index[(str(t).upper(), str(x).upper())] = str(i)

    _TICKER_INDEX_CACHE[abs_path] = index
    return index


def reset_ticker_cache() -> None:
    """Clear the per-path ticker index cache. For tests."""
    _TICKER_INDEX_CACHE.clear()


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
        """Initialize the registry from a file path or a pre-loaded dict.

        Either `actions_path` or `actions_data` must be provided. If both
        are provided, `actions_data` takes precedence.

        Structural validation happens here, before any index is built:

        - The document must be an object with an `actions` array.
        - Every entry in `actions` must be a JSON object.
        - Every entry must carry at least one of `isin` or `action_id`.
        - No two entries may share a non-empty `action_id`.

        Args:
            actions_path: Path to actions.json.
            actions_data: Already loaded JSON data as a dict.

        Raises:
            FileNotFoundError: If actions_path does not exist.
            ValueError: If the JSON is invalid or structurally wrong.
        """
        if actions_data is not None:
            raw_data = actions_data
        elif actions_path is not None:
            with open(actions_path, "r", encoding="utf-8-sig") as f:
                raw_data = json.load(f)
        else:
            raise ValueError(
                "Either actions_path or actions_data must be provided."
            )

        if not isinstance(raw_data, dict) or "actions" not in raw_data:
            raise ValueError(
                "Invalid actions data: expected dict with 'actions' key."
            )

        raw_actions = raw_data["actions"]
        if not isinstance(raw_actions, list):
            raise ValueError(
                "Invalid actions data: 'actions' must be a list, got "
                f"{type(raw_actions).__name__}"
            )

        # Per-item structural validation, single pass.
        seen_ids: Dict[str, int] = {}
        for i, item in enumerate(raw_actions):
            if not isinstance(item, dict):
                raise ValueError(
                    f"Invalid actions data: action at index {i} is not "
                    f"an object, got {type(item).__name__}"
                )

            aid = item.get("action_id")
            if aid:
                if aid in seen_ids:
                    raise ValueError(
                        f"duplicate action_id at index {i}: {aid!r} "
                        f"(first seen at index {seen_ids[aid]})"
                    )
                seen_ids[aid] = i

            if not item.get("isin") and not aid:
                raise ValueError(
                    f"action at index {i} has neither 'isin' nor 'action_id'"
                )

        self.meta = RegistryMeta.from_dict(raw_data.get("meta"))
        self.actions: List[Action] = [
            Action.from_dict(item) for item in raw_actions
        ]

        self._build_indexes()

    def _build_indexes(self) -> None:
        """Build in-memory indexes for fast lookups."""
        self._index_by_isin: Dict[str, List[Action]] = {}
        self._index_by_type: Dict[str, List[Action]] = {}
        self._index_by_id: Dict[str, Action] = {}

        for action in self.actions:
            if action.action_id:
                # Per-section 5.5 the loader already guarantees no
                # duplicates reach this point.
                self._index_by_id[action.action_id] = action

            if action.isin:
                self._index_by_isin.setdefault(action.isin, []).append(action)

            if action.action_type:
                self._index_by_type.setdefault(action.action_type, []).append(action)

    # ------------------------------------------------------------------
    # Lookup methods
    # ------------------------------------------------------------------

    def by_isin(self, isin: str) -> List[Action]:
        """Return all actions for a given ISIN.

        Args:
            isin: The ISIN of the instrument (e.g., 'US0378331005').

        Returns:
            List of Action objects, possibly empty. A fresh deep copy.
        """
        return [copy.deepcopy(a) for a in self._index_by_isin.get(isin, [])]

    def by_action_id(self, action_id: str) -> Optional[Action]:
        """Return the single action with this action_id, or None.

        The returned object is a deep copy: mutating it does not affect
        the registry's internal state.
        """
        action = self._index_by_id.get(action_id)
        if action is None:
            return None
        return copy.deepcopy(action)

    def by_action_type(self, action_type: str) -> List[Action]:
        """Return all actions of a given type (e.g., 'SPLIT', 'DIVIDEND').

        Args:
            action_type: The action type string.

        Returns:
            List of Action objects, possibly empty. A fresh deep copy.
        """
        return [copy.deepcopy(a) for a in self._index_by_type.get(action_type, [])]

    def by_date_range(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        date_field: str = DEFAULT_DATE_FIELD,
    ) -> List[Action]:
        """Return actions whose `date_field` falls in [start_date, end_date].

        Bounds are inclusive. Pass None (or omit) for an open bound.
        Actions lacking `date_field` are skipped silently.

        Raises ValueError if `date_field` is not one of the four valid
        names. Results are sorted by the requested field, then by
        action_id. See the wrapper contract section 4.4.

        The returned list is a fresh deep copy.
        """
        if date_field not in VALID_DATE_FIELDS:
            raise ValueError(
                f"invalid date_field {date_field!r}; "
                f"expected one of {sorted(VALID_DATE_FIELDS)}"
            )

        result: List[Action] = []
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

    def by_ticker(
        self,
        ticker: str,
        exchange: str,
        identifiers_path: Optional[str] = None,
    ) -> List[Action]:
        """Return all actions for a ticker on an exchange.

        Resolves (ticker, exchange) -> ISIN using the Asset Identifiers
        registry, then returns the same list as `by_isin(isin)`.

        Path resolution, in order, when `identifiers_path` is None or
        empty:

          1. $CORP_ACTIONS_IDENTIFIERS_PATH
          2. $LAS_DATA_HOME/identifiers.json

        Ticker and exchange are uppercased before lookup. An unknown
        (ticker, exchange) pair returns an empty list, not an error.
        A missing identifiers file raises RuntimeError naming the two
        environment variables that would fix it.

        See the wrapper contract section 4.8.
        """
        path = _resolve_identifiers_path(identifiers_path)
        index = _build_ticker_index(path)

        key = (str(ticker).upper(), str(exchange).upper())
        isin = index.get(key)
        if isin is None:
            return []
        return self.by_isin(isin)

    def all_action_types(self) -> List[str]:
        """Return a sorted list of unique action types in the registry."""
        return sorted(self._index_by_type.keys())

    def count(self) -> int:
        """Return total number of actions."""
        return len(self.actions)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the entire registry back to a dictionary.

        Returns:
            Dict with 'meta' and 'actions' keys.
        """
        return {
            "meta": self.meta.to_dict(),
            "actions": [action.to_dict() for action in self.actions],
        }

    def save(self, path: str) -> None:
        """Save the registry to a JSON file.

        Args:
            path: Destination file path.
        """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Dunder methods
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        """Return number of actions."""
        return len(self.actions)

    def __repr__(self) -> str:
        return f"<CorporateActionsRegistry actions={len(self.actions)}>"