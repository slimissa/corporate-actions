#!/usr/bin/env python3
"""
Corporate Actions Registry Validator

Validates actions.json against:
- JSON Schema (schema.json)
- Temporal rules per action type
- Arithmetic rules (split ratios, dividend amounts)
- Cross-references with Asset Identifiers, ISO 4217, Exchange Calendar
- Uniqueness of action IDs
- Coverage threshold
- Provenance completeness
- MERGER actions are rejected (placeholder in v1.0.0)

Cross-references with Asset Identifiers:
  - Reads from $LAS_DATA_HOME/identifiers.json by default.
  - Can be overridden with --identifiers or CORP_ACTIONS_IDENTIFIERS_PATH.
  - Remote HTTP(S) URLs are NOT supported. Local files only.

By default, missing ISINs are warnings, not errors, so the registry can
be validated against a partial Asset Identifiers subset. Use --strict-isin
to enforce hard errors when the subset is complete.
Exit codes:
  0 - all validations passed
  1 - validation errors found
  2 - usage error or missing local file (actions.json, schema.json)
  3 - external registry loading failure
"""

import json
import os
import sys
import re
from typing import Dict, List, Set, Any

try:
    import jsonschema
    from jsonschema import validate as schema_validate
except ImportError:
    print("Error: jsonschema is required. Install with: pip install jsonschema", file=sys.stderr)
    sys.exit(2)

# Default paths (can be overridden by env vars or CLI args)
DEFAULT_ACTIONS_PATH = "actions.json"
DEFAULT_SCHEMA_PATH = "schema.json"
DEFAULT_IDENTIFIERS_PATH = "../asset-identifiers/identifiers.json"
DEFAULT_ISO4217_PATH = "../iso4217/iso4217.json"
DEFAULT_EXCHANGE_CALENDAR_PATH = "../exchange-calendar/calendar.json"

# Environment variable overrides
ENV_ACTIONS = "CORP_ACTIONS_ACTIONS_PATH"
ENV_SCHEMA = "CORP_ACTIONS_SCHEMA_PATH"
ENV_IDENTIFIERS = "CORP_ACTIONS_IDENTIFIERS_PATH"
ENV_LAS_DATA_HOME = "LAS_DATA_HOME"
ENV_ISO4217 = "CORP_ACTIONS_ISO4217_PATH"
ENV_EXCHANGE_CAL = "CORP_ACTIONS_EXCHANGE_CALENDAR_PATH"
ENV_MIN_ACTIONS = "CORP_ACTIONS_MIN_ACTIONS"

# Minimum number of actions required (set via env or default)
DEFAULT_MIN_ACTIONS = 1

# Valid action types (MERGER placeholder not allowed in v1.0.0)
VALID_ACTION_TYPES = [
    "SPLIT",
    "REVERSE_SPLIT",
    "DIVIDEND",
    "SPECIAL_DIVIDEND",
    "SYMBOL_CHANGE",
    "SPINOFF",
    "DELISTING",
    "MERGER"
]

# Action types allowed in current version
ALLOWED_ACTION_TYPES = [
    "SPLIT",
    "REVERSE_SPLIT",
    "DIVIDEND",
    "SPECIAL_DIVIDEND",
    "SYMBOL_CHANGE",
    "SPINOFF",
    "DELISTING"
]


class RegistryLoadError(Exception):
    """Raised when an external registry cannot be loaded or parsed."""
    pass

def resolve_default_identifiers_path() -> str:
    """
    Determine the default path to identifiers.json.
    Priority:
      1. LAS_DATA_HOME environment variable → $LAS_DATA_HOME/identifiers.json
      2. Fallback to the legacy relative path (../asset-identifiers/identifiers.json)
    """
    las_data_home = os.environ.get(ENV_LAS_DATA_HOME)
    if las_data_home:
        candidate = os.path.join(las_data_home, "identifiers.json")
        return candidate
    return DEFAULT_IDENTIFIERS_PATH

def load_json_file(path: str) -> Dict[str, Any]:
    """Load a JSON file; raise exception on missing or invalid file."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {path}: {e}")


def load_identifiers_registry(path: str) -> Set[str]:
    """
    Load Asset Identifiers registry and return set of all ISINs.
    Handles common structures: { "instruments": [...] } or { "identifiers": [...] }
    """
    try:
        data = load_json_file(path)
    except Exception as e:
        raise RegistryLoadError(f"Failed to load Asset Identifiers registry: {e}")

    isins = set()
    # Try common keys
    for key in ("instruments", "identifiers", "securities"):
        if key in data and isinstance(data[key], list):
            for inst in data[key]:
                if isinstance(inst, dict) and "isin" in inst and inst["isin"]:
                    isins.add(inst["isin"])
            break
    else:
        # Fallback: find first list of dicts with "isin"
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict) and "isin" in value[0]:
                for item in value:
                    if "isin" in item:
                        isins.add(item["isin"])
                break

    if not isins:
        print("Warning: No ISINs found in Asset Identifiers registry", file=sys.stderr)
    return isins

def load_iso4217_registry(path: str) -> Set[str]:
    """
    Load ISO 4217 registry and return set of active currency codes.
    According to the ISO 4217 registry structure:
      {
        "currencies": {
          "active":   [ { "code": "USD", ... }, ... ],
          "withdrawn": [ { "code": "DEM", ... }, ... ]
        },
        "non_iso": { ... }
      }
    We only want the active codes.
    """
    data = load_json_file(path)
    try:
        active_list = data["currencies"]["active"]
    except (KeyError, TypeError):
        raise RegistryLoadError("ISO 4217 registry missing 'currencies.active'")

    if not isinstance(active_list, list):
        raise RegistryLoadError("ISO 4217 'currencies.active' must be a list")

    currencies = set()
    for entry in active_list:
        if isinstance(entry, dict):
            code = entry.get("code")
            if code:
                currencies.add(code)
    return currencies

def load_exchange_calendar_registry(path: str) -> Set[str]:
    """
    Load Exchange Calendar registry and return set of exchange MICs.
    Handles structures: { "exchanges": [...] } with "mic" or "code" fields.
    """
    try:
        data = load_json_file(path)
    except Exception as e:
        raise RegistryLoadError(f"Failed to load Exchange Calendar registry: {e}")

    mics = set()
    exchange_list = None
    if "exchanges" in data and isinstance(data["exchanges"], list):
        exchange_list = data["exchanges"]
    else:
        # Fallback: first list of dicts with "mic" or "code"
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                if "mic" in value[0] or "code" in value[0]:
                    exchange_list = value
                    break

    if not exchange_list:
        raise RegistryLoadError("No exchange list found in Exchange Calendar registry")

    for exch in exchange_list:
        if isinstance(exch, dict):
            mic = exch.get("mic") or exch.get("code")
            if mic:
                mics.add(mic)
    return mics


def validate_schema(action: Dict[str, Any], action_schema: Dict[str, Any]) -> List[str]:
    """Validate a single action against the action sub-schema."""
    errors = []
    try:
        schema_validate(action, action_schema)
    except jsonschema.ValidationError as e:
        errors.append(f"Schema error: {e.message} (path: {'/'.join(map(str, e.absolute_path))})")
    return errors


def validate_temporal(action: Dict[str, Any]) -> List[str]:
    """
    Validate date ordering based on action type.
    Rules:
      - SPLIT / REVERSE_SPLIT:
          announcement ≤ ex_date
          ex_date = effective_date (usually)
          record_date ≤ ex_date
      - DIVIDEND / SPECIAL_DIVIDEND:
          announcement ≤ ex_date
          ex_date < record_date
          record_date ≤ effective_date
      - SYMBOL_CHANGE:
          announcement ≤ effective_date
      - SPINOFF:
          announcement ≤ ex_date
          ex_date = effective_date
      - DELISTING:
          only effective_date; no ex_date or record_date
      - MERGER: placeholder (will not be checked further)
    """
    errors = []
    action_type = action["action_type"]
    dates = action.get("dates") or {}

    announcement = dates.get("announcement")
    ex_date = dates.get("ex_date")
    record_date = dates.get("record_date")
    effective_date = dates.get("effective_date")

    # Basic checks (schema ensures announcement and effective_date exist)
    if not announcement:
        errors.append("Missing announcement date")
    if not effective_date:
        errors.append("Missing effective date")

    if announcement and effective_date and announcement > effective_date:
        errors.append(f"Announcement date {announcement} is after effective date {effective_date}")

    # Type-specific rules
    if action_type in ["SPLIT", "REVERSE_SPLIT"]:
        if ex_date:
            if announcement and announcement > ex_date:
                errors.append(f"Announcement ({announcement}) after ex_date ({ex_date})")
            if effective_date and ex_date != effective_date:
                errors.append(f"ex_date ({ex_date}) must equal effective_date ({effective_date})")
        if record_date and ex_date and record_date > ex_date:
            errors.append(f"record_date ({record_date}) after ex_date ({ex_date})")

    elif action_type in ["DIVIDEND", "SPECIAL_DIVIDEND"]:
        if ex_date:
            if announcement and announcement > ex_date:
                errors.append(f"Announcement ({announcement}) after ex_date ({ex_date})")
        if ex_date and record_date and ex_date >= record_date:
            errors.append(f"ex_date ({ex_date}) must be before record_date ({record_date})")
        if record_date and effective_date and record_date > effective_date:
            errors.append(f"record_date ({record_date}) after effective_date ({effective_date})")

    elif action_type == "SYMBOL_CHANGE":
        # No extra checks beyond announcement ≤ effective_date
        pass

    elif action_type == "SPINOFF":
        if ex_date:
            if announcement and announcement > ex_date:
                errors.append(f"Announcement ({announcement}) after ex_date ({ex_date})")
            if effective_date and ex_date != effective_date:
                errors.append(f"ex_date ({ex_date}) must equal effective_date ({effective_date})")

    elif action_type == "DELISTING":
        if ex_date:
            errors.append("DELISTING should not have ex_date")
        if record_date:
            errors.append("DELISTING should not have record_date")

    elif action_type == "MERGER":
        # Placeholder; no additional checks
        pass

    return errors

def validate_uniqueness(actions):
    seen = set()
    errors = []
    for action in actions:
        action_id = action.get("action_id")
        if action_id is not None:
            if action_id in seen:
                errors.append(f"Duplicate action_id: {action_id}")
            else:
                seen.add(action_id)
    return errors

def validate_arithmetic(action: Dict[str, Any]) -> List[str]:
    """
    Validate arithmetic rules:
    - SPLIT / REVERSE_SPLIT: ratio must be in form N:M and N>0, M>0
    - DIVIDEND / SPECIAL_DIVIDEND: amount must be >0
    """
    errors = []
    action_type = action["action_type"]
    if action_type in ["SPLIT", "REVERSE_SPLIT"]:
        ratio = action.get("ratio")
        if not ratio:
            errors.append(f"{action_type} requires ratio")
        else:
            # Strict format: digits colon digits, no spaces or extra chars
            if not isinstance(ratio, str) or not re.fullmatch(r"\d+:\d+", ratio):
                errors.append(f"Invalid ratio format: {ratio}")
            else:
                parts = ratio.split(":")
                try:
                    num, den = int(parts[0]), int(parts[1])
                    if num <= 0 or den <= 0:
                        errors.append(f"Ratio parts must be positive integers: {ratio}")
                except ValueError:
                    errors.append(f"Ratio parts must be integers: {ratio}")
    elif action_type in ["DIVIDEND", "SPECIAL_DIVIDEND"]:
        amount = action.get("amount")
        if amount is None:
            errors.append(f"{action_type} requires amount")
        elif not isinstance(amount, (int, float)):
            errors.append(f"{action_type} amount must be a number: {amount}")
        elif amount <= 0:
            errors.append(f"{action_type} amount must be positive: {amount}")
    return errors


def validate_cross_reference(
    action: Dict[str, Any],
    isin_set: Set[str],
    currency_set: Set[str],
    mic_set: Set[str],
    strict_isin: bool = False,
    isin_warnings: List[str] = None,
) -> List[str]:
    """
    Validate that referenced ISINs, currencies, and MICs exist in the
    respective registries.

    If strict_isin is False (default), missing ISINs are appended to
    isin_warnings (if provided) instead of returned as errors.
    """
    errors = []
    isin = action.get("isin")
    if isin and isin not in isin_set:
        msg = f"ISIN not found in Asset Identifiers registry: {isin}"
        if strict_isin or isin_warnings is None:
            # Strict mode, or caller did not opt into warnings → treat as error.
            errors.append(msg)
        else:
            # Non-strict mode with warnings list → append as warning.
            isin_warnings.append(msg)

    currency = action.get("currency")
    if currency and currency not in currency_set:
        errors.append(f"Currency not an active ISO 4217 code: {currency}")

    exchange = action.get("exchange")
    if exchange and exchange not in mic_set:
        errors.append(f"Exchange MIC not found in Exchange Calendar registry: {exchange}")

    return errors


def validate_provenance(action: Dict[str, Any]) -> List[str]:
    """Validate that provenance.source_url exists and is a valid HTTP(S) URL."""
    errors = []
    provenance = action.get("provenance", {})
    if "source_url" not in provenance or not provenance["source_url"]:
        errors.append("provenance.source_url is required")
    else:
        url = provenance["source_url"]
        if not url.startswith(("http://", "https://")):
            errors.append(f"source_url must be HTTP(S): {url}")
    return errors


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Validate Corporate Actions Registry")
    parser.add_argument("--actions", help="Path to actions.json", default=None)
    parser.add_argument("--schema", help="Path to schema.json", default=None)
    parser.add_argument("--identifiers", help="Path to identifiers.json", default=None)
    parser.add_argument("--iso4217", help="Path to iso4217.json", default=None)
    parser.add_argument("--exchange-calendar", help="Path to calendar.json", default=None)
    parser.add_argument("--min-actions", type=int, help="Minimum number of actions required", default=None)
    parser.add_argument("--strict-isin", action="store_true", help="Treat missing ISINs as errors instead of warnings",)
    args = parser.parse_args()

    # Resolve paths: CLI args > env vars > defaults
    actions_path = args.actions or os.environ.get(ENV_ACTIONS, DEFAULT_ACTIONS_PATH)
    schema_path = args.schema or os.environ.get(ENV_SCHEMA, DEFAULT_SCHEMA_PATH)
    # Resolution order:
    #   1. --identifiers CLI arg
    #   2. CORP_ACTIONS_IDENTIFIERS_PATH env var
    #   3. $LAS_DATA_HOME/identifiers.json (if LAS_DATA_HOME is set)
    #   4. Legacy relative default
    identifiers_path = (
    args.identifiers
    or os.environ.get(ENV_IDENTIFIERS)
    or resolve_default_identifiers_path()
    )
    iso4217_path = args.iso4217 or os.environ.get(ENV_ISO4217, DEFAULT_ISO4217_PATH)
    exch_cal_path = args.exchange_calendar or os.environ.get(ENV_EXCHANGE_CAL, DEFAULT_EXCHANGE_CALENDAR_PATH)

    min_actions = args.min_actions
    if min_actions is None:
        min_actions_str = os.environ.get(ENV_MIN_ACTIONS)
        if min_actions_str:
            try:
                min_actions = int(min_actions_str)
            except ValueError:
                print(f"Invalid MIN_ACTIONS env value: {min_actions_str}", file=sys.stderr)
                sys.exit(2)
        else:
            min_actions = DEFAULT_MIN_ACTIONS

    # Load local files (actions and schema)
    try:
        actions_data = load_json_file(actions_path)
    except Exception as e:
        print(f"Error loading actions.json: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        schema_data = load_json_file(schema_path)
    except Exception as e:
        print(f"Error loading schema.json: {e}", file=sys.stderr)
        sys.exit(2)

    # Extract action sub-schema
    try:
        action_schema = schema_data["properties"]["actions"]["items"]
    except (KeyError, TypeError):
        print("Error: schema.json does not contain a valid action item schema", file=sys.stderr)
        sys.exit(2)

    # Load external registries (exit code 3 on failure)
    try:
        print("Loading Asset Identifiers registry...")
        isin_set = load_identifiers_registry(identifiers_path)
        print(f"  Loaded {len(isin_set)} ISINs")

        print("Loading ISO 4217 registry...")
        currency_set = load_iso4217_registry(iso4217_path)
        print(f"  Loaded {len(currency_set)} active currencies")

        print("Loading Exchange Calendar registry...")
        mic_set = load_exchange_calendar_registry(exch_cal_path)
        print(f"  Loaded {len(mic_set)} exchange MICs")
    except RegistryLoadError as e:
        print(f"Error loading external registry: {e}", file=sys.stderr)
        sys.exit(3)

    # Extract actions list
    actions = actions_data.get("actions")
    if not isinstance(actions, list):
        print("Error: 'actions' key missing or not a list in actions.json", file=sys.stderr)
        sys.exit(1)

    total_actions = len(actions)
    print(f"\nValidating {total_actions} actions...")

    all_errors = []
    all_warnings = []

    for idx, action in enumerate(actions, start=1):
        action_id = action.get("action_id", f"<missing action_id at index {idx}>")

        # 0. Check if action type is allowed in this version
        action_type = action.get("action_type")
        if action_type == "MERGER":
            all_errors.append(f"Action {action_id}: MERGER is not allowed in v1.0.0")

        # 1. Schema validation
        schema_errors = validate_schema(action, action_schema)
        if schema_errors:
            all_errors.extend([f"Action {action_id}: {e}" for e in schema_errors])

        # 2. Temporal validation
        temporal_errors = validate_temporal(action)
        if temporal_errors:
            all_errors.extend([f"Action {action_id}: temporal: {e}" for e in temporal_errors])

        # 3. Arithmetic validation
        arith_errors = validate_arithmetic(action)
        if arith_errors:
            all_errors.extend([f"Action {action_id}: arithmetic: {e}" for e in arith_errors])

        # 4. Cross-reference validation
        cross_errors = validate_cross_reference(action, isin_set,currency_set, mic_set, strict_isin=args.strict_isin, isin_warnings=all_warnings,)
        if cross_errors:
            all_errors.extend([f"Action {action_id}: cross-reference: {e}" for e in cross_errors])

        # 5. Provenance validation
        prov_errors = validate_provenance(action)
        if prov_errors:
            all_errors.extend([f"Action {action_id}: provenance: {e}" for e in prov_errors])

    # 6. Uniqueness validation (across all actions)
    uniqueness_errors = validate_uniqueness(actions)
    if uniqueness_errors:
        all_errors.extend(uniqueness_errors)

    # 7. Coverage check
    if total_actions < min_actions:
        all_errors.append(f"Coverage: only {total_actions} actions found, minimum required is {min_actions}")

    # Warnings
    if all_warnings:
        print(f"\nWarnings ({len(all_warnings)}):")
        for w in all_warnings:
            print(f"  - {w}")

    # Report
    if all_errors:
        print("\nValidation FAILED with the following errors:")
        for err in all_errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        valid_isin_count = sum(1 for a in actions if a.get("isin") and a.get("isin") in isin_set)
        missing_isin_count = len(all_warnings)
        print(f"\nOK: {total_actions} actions validated successfully.")
        print(f"Cross-reference: {valid_isin_count} ISINs validated, {missing_isin_count} missing (warnings)")
        print("All layers passed: schema, temporal, arithmetic, cross-reference, uniqueness, provenance, coverage")
        sys.exit(0)


if __name__ == "__main__":
    main()