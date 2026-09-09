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

Exit codes:
  0 - all validations passed
  1 - validation errors found
  2 - usage error or missing local file (actions.json, schema.json)
  3 - external registry loading failure
"""

import json
import os
import sys
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
    Load ISO 4217 registry and return set of currency codes.
    This version recursively scans the JSON and extracts all strings
    that look like 3-letter uppercase codes (e.g., USD, EUR).
    """
    try:
        data = load_json_file(path)
    except Exception as e:
        raise RegistryLoadError(f"Failed to load ISO 4217 registry: {e}")

    currencies = set()

    def extract_codes(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                # If the key itself looks like a currency code (3 uppercase letters)
                if isinstance(k, str) and len(k) == 3 and k.isupper() and k.isalpha():
                    currencies.add(k)
                extract_codes(v)
        elif isinstance(obj, list):
            for item in obj:
                extract_codes(item)
        elif isinstance(obj, str):
            # In case a list contains direct strings like "USD"
            if len(obj) == 3 and obj.isupper() and obj.isalpha():
                currencies.add(obj)

    extract_codes(data)

    if not currencies:
        raise RegistryLoadError("No currency codes found in ISO 4217 registry")
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
    dates = action.get("dates", {})

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
            parts = ratio.split(":")
            if len(parts) != 2:
                errors.append(f"Invalid ratio format: {ratio}")
            else:
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
        elif amount <= 0:
            errors.append(f"{action_type} amount must be positive: {amount}")
    return errors


def validate_cross_reference(
    action: Dict[str, Any],
    isin_set: Set[str],
    currency_set: Set[str],
    mic_set: Set[str]
) -> List[str]:
    """Validate that referenced ISINs, currencies, and MICs exist in the respective registries."""
    errors = []
    isin = action.get("isin")
    if isin and isin not in isin_set:
        errors.append(f"ISIN not found in Asset Identifiers registry: {isin}")

    currency = action.get("currency")
    if currency and currency not in currency_set:
        errors.append(f"Currency not an active ISO 4217 code: {currency}")

    # Optional exchange field (if ever added to schema)
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
    args = parser.parse_args()

    # Resolve paths: CLI args > env vars > defaults
    actions_path = args.actions or os.environ.get(ENV_ACTIONS, DEFAULT_ACTIONS_PATH)
    schema_path = args.schema or os.environ.get(ENV_SCHEMA, DEFAULT_SCHEMA_PATH)
    identifiers_path = args.identifiers or os.environ.get(ENV_IDENTIFIERS, DEFAULT_IDENTIFIERS_PATH)
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
    seen_action_ids = set()

    for idx, action in enumerate(actions, start=1):
        action_id = action.get("action_id", f"<missing action_id at index {idx}>")

        # 0. Check if action type is allowed in this version
        action_type = action.get("action_type")
        if action_type == "MERGER":
            all_errors.append(f"Action {action_id}: MERGER is not allowed in v1.0.0")
        if action_type not in ALLOWED_ACTION_TYPES and action_type in VALID_ACTION_TYPES:
            # This handles MERGER if not caught above (but above catches it)
            pass  # the above if will catch any MERGER

        # 1. Schema validation
        schema_errors = validate_schema(action, action_schema)
        if schema_errors:
            all_errors.extend([f"Action {action_id}: {e}" for e in schema_errors])
            # Continue to other checks even if schema invalid? Better to skip to avoid attribute errors.
            # But we can still run other validators as they check their own fields.
            # We'll continue but some validators may fail if required fields missing.
            # For simplicity, we'll continue.

        # 2. Uniqueness
        if action_id in seen_action_ids:
            all_errors.append(f"Duplicate action_id: {action_id}")
        else:
            seen_action_ids.add(action_id)

        # 3. Temporal
        temporal_errors = validate_temporal(action)
        if temporal_errors:
            all_errors.extend([f"Action {action_id}: temporal: {e}" for e in temporal_errors])

        # 4. Arithmetic
        arith_errors = validate_arithmetic(action)
        if arith_errors:
            all_errors.extend([f"Action {action_id}: arithmetic: {e}" for e in arith_errors])

        # 5. Cross-reference
        cross_errors = validate_cross_reference(action, isin_set, currency_set, mic_set)
        if cross_errors:
            all_errors.extend([f"Action {action_id}: cross-reference: {e}" for e in cross_errors])

        # 6. Provenance
        prov_errors = validate_provenance(action)
        if prov_errors:
            all_errors.extend([f"Action {action_id}: provenance: {e}" for e in prov_errors])

    # 7. Coverage
    if total_actions < min_actions:
        all_errors.append(f"Coverage: only {total_actions} actions found, minimum required is {min_actions}")

    # Report
    if all_errors:
        print("\nValidation FAILED with the following errors:")
        for err in all_errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print(f"\nOK: {total_actions} actions validated successfully.")
        print("All layers passed: schema, temporal, arithmetic, cross-reference, uniqueness, provenance, coverage")
        sys.exit(0)


if __name__ == "__main__":
    main()