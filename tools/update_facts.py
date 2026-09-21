#!/usr/bin/env python3
"""
Regenerate docs/facts.json from the code, data, and test collectors.

Usage:
    python3 tools/update_facts.py           # write docs/facts.json
    python3 tools/update_facts.py --check   # exit 1 if it would change

The tool reads:
  - actions.json                (action count, instrument count, type counts)
  - tools/validate.py           (DEFAULT_MIN_ACTIONS)
  - README.md                   (sibling versions, since they're pinned there)
  - pytest / go test / cargo / npm collectors (test counts)

Fields that cannot be derived (sec_edgar_status, nasdaq_status,
historical_depth_start) are preserved from the existing facts.json.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FACTS_PATH = REPO_ROOT / "docs" / "facts.json"


def load_existing() -> dict:
    if FACTS_PATH.is_file():
        return json.loads(FACTS_PATH.read_text(encoding="utf-8"))
    return {}


def action_facts() -> dict:
    data = json.loads((REPO_ROOT / "actions.json").read_text(encoding="utf-8"))
    actions = data["actions"]
    from collections import Counter
    return {
        "action_count": len(actions),
        "instrument_count": len({a["isin"] for a in actions if a.get("isin")}),
        "action_type_counts": dict(Counter(a["action_type"] for a in actions)),
        "instruments": sorted({a["isin"] for a in actions if a.get("isin")}),
    }


def validator_facts() -> dict:
    text = (REPO_ROOT / "tools" / "validate.py").read_text(encoding="utf-8")
    m = re.search(r"DEFAULT_MIN_ACTIONS\s*=\s*(\d+)", text)
    return {"min_actions_code": int(m.group(1)) if m else 100}


def sibling_versions() -> dict:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    out = {}
    m = re.search(r"ISO 4217.*?v(\d+\.\d+\.\d+)", readme)
    if m: out["iso4217"] = f"v{m.group(1)}"
    m = re.search(r"Exchange Calendar.*?v(\d+\.\d+\.\d+)", readme)
    if m: out["exchange_calendar"] = f"v{m.group(1)}"
    m = re.search(r"Asset Identifiers.*?schema (\d+\.\d+\.\d+)", readme)
    if m: out["asset_identifiers_schema"] = m.group(1)
    return {"sibling_versions": out}


def count_root_tests() -> dict:
    r = subprocess.run(
        ["python3", "-m", "pytest", "tests/", "--collect-only", "-q",
         "-m", "not network"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    m = re.search(r"(\d+)/(\d+) tests collected", r.stdout)
    if not m:
        raise RuntimeError(f"cannot parse pytest output:\n{r.stdout[-500:]}")
    return {
        "root_test_count": int(m.group(1)),
        "root_test_collected_total": int(m.group(2)),
        "root_test_network_deselected": int(m.group(2)) - int(m.group(1)),
    }


def count_wrapper_tests() -> dict:
    py = subprocess.run(
        ["python3", "-m", "pytest", "tests", "--collect-only", "-q"],
        capture_output=True, text=True,
        cwd=str(REPO_ROOT / "wrappers" / "python"),
    )
    py_n = int(re.search(r"(\d+) tests collected", py.stdout).group(1))

    js = subprocess.run(
        ["node", "--test", "test/test_wrapper.js"],
        capture_output=True, text=True,
        cwd=str(REPO_ROOT / "wrappers" / "javascript"),
    )
    js_n = int(re.search(r"^# pass (\d+)", js.stdout, re.M).group(1))

    go = subprocess.run(
        ["go", "test", "./registry", "-v"],
        capture_output=True, text=True,
        cwd=str(REPO_ROOT / "wrappers" / "go"),
    )
    go_n = len(re.findall(r"^--- PASS", go.stdout, re.M))

    rust = subprocess.run(
        ["cargo", "test"],
        capture_output=True, text=True,
        cwd=str(REPO_ROOT / "wrappers" / "rust"),
    )
    rust_counts = [int(m.group(1)) for m in
                   re.finditer(r"(\d+) passed", rust.stdout)]
    return {
        "wrapper_test_counts": {
            "python": py_n,
            "javascript": js_n,
            "go": go_n,
            "rust": sum(rust_counts) - 1 if rust_counts else 0,
            "rust_doctests": 1,
        }
    }


def build_facts() -> dict:
    existing = load_existing()
    new = {}
    new.update(action_facts())
    new.update(validator_facts())
    new.update(sibling_versions())
    new.update(count_root_tests())
    new.update(count_wrapper_tests())

    # Preserve hand-maintained fields
    for key in ("populated_types", "reserved_types", "historical_depth_start",
                "currencies", "root_test_skipped", "min_actions_docs",
                "min_actions_roadmap_target", "sec_edgar_status",
                "sec_edgar_scope", "nasdaq_status", "format_date_enforcement",
                "state_file_timestamp_example", "webhook_timestamp_format"):
        if key in existing:
            new[key] = existing[key]

    # Stable key order
    ordered = {}
    for key in ["action_count", "instrument_count", "instruments",
                "action_type_counts", "populated_types", "reserved_types",
                "historical_depth_start", "currencies",
                "root_test_count", "root_test_skipped",
                "root_test_network_deselected", "root_test_collected_total",
                "wrapper_test_counts", "sibling_versions",
                "min_actions_code", "min_actions_docs",
                "min_actions_roadmap_target",
                "sec_edgar_status", "sec_edgar_scope", "nasdaq_status",
                "format_date_enforcement", "state_file_timestamp_example",
                "webhook_timestamp_format"]:
        if key in new:
            ordered[key] = new[key]
    return ordered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if facts.json would change")
    args = parser.parse_args()

    new = build_facts()
    payload = json.dumps(new, indent=2) + "\n"

    if args.check:
        if not FACTS_PATH.is_file():
            print("docs/facts.json missing", file=sys.stderr)
            return 1
        current = FACTS_PATH.read_text(encoding="utf-8")
        if current != payload:
            print("docs/facts.json is stale; regenerate with "
                  "python3 tools/update_facts.py", file=sys.stderr)
            return 1
        print("docs/facts.json is current.")
        return 0

    FACTS_PATH.write_text(payload, encoding="utf-8")
    print(f"Wrote {FACTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())