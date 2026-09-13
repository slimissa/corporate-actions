#!/usr/bin/env bash
#
# run_update.sh – Full update pipeline for the Corporate Actions Registry.
#
# This script performs the following steps:
#   1. (Optional) Fetch new actions from Yahoo Finance.
#   2. Merge fetched actions into actions.json with fuzzy dedup.
#   3. Derive impact multipliers.
#   4. Validate actions.json against all cross-references.
#   5. Run all test suites (root tests + wrappers).
#   6. Build distribution artifacts.
#   7. (Optional) Send change notification.
#   8. (Optional) Commit and tag if everything passes.
#
# Usage:
#   scripts/run_update.sh [options]
#
# Options:
#   --identifiers PATH          Path to Asset Identifiers identifiers.json
#   --iso4217 PATH              Path to ISO 4217 iso4217.json
#   --exchange-calendar PATH    Path to Exchange Calendar calendar.json
#   --actions PATH              Path to actions.json (default: actions.json)
#   --schema PATH               Path to schema.json (default: schema.json)
#   --fetch-source SOURCE       Data source (default: yahoo). Only yahoo is
#                               currently functional. 'sec' and 'nasdaq' are
#                               reserved and will error with a clear message.
#   --ticker-limit N            Limit fetcher to first N tickers
#   --min-actions N             Minimum number of actions required (default: 1)
#   --skip-fetch                Do not run any fetcher
#   --skip-tests                Do not run test suites
#   --skip-build                Do not run build.py
#   --dry-run                   Show what would happen; do not commit or tag
#   --commit                    Commit changes after success
#   --tag VERSION               Tag the release after success (requires --commit)
#   --webhook-url URL           Send notification to webhook on change
#   --verbose                   Print verbose output
#
# Exit codes:
#   0 – success
#   1 – any step failed
#   2 – usage error

set -euo pipefail

# ----------------------------------------------------------------------
# Resolve repository root
# ----------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ----------------------------------------------------------------------
# Default paths
# ----------------------------------------------------------------------
# Default paths resolved in priority order:
#   1. $CORP_ACTIONS_* env var (handled later)
#   2. $LAS_DATA_HOME/identifiers.json (Asset Identifiers)
#   3. repo-local tests/fixtures/*.json (always available)
#   4. sibling directories (legacy layout)

# Identifiers
if [[ -n "${LAS_DATA_HOME:-}" && -f "${LAS_DATA_HOME}/identifiers.json" ]]; then
    DEFAULT_IDENTIFIERS_PATH="${LAS_DATA_HOME}/identifiers.json"
elif [[ -f "${REPO_ROOT}/tests/fixtures/identifiers.json" ]]; then
    DEFAULT_IDENTIFIERS_PATH="${REPO_ROOT}/tests/fixtures/identifiers.json"
else
    DEFAULT_IDENTIFIERS_PATH="${REPO_ROOT}/../asset-identifiers/identifiers.json"
fi

# ISO 4217
if [[ -f "${REPO_ROOT}/tests/fixtures/iso4217.json" ]]; then
    DEFAULT_ISO4217_PATH="${REPO_ROOT}/tests/fixtures/iso4217.json"
else
    DEFAULT_ISO4217_PATH="${REPO_ROOT}/../iso4217 registry/iso4217.json"
fi

# Exchange Calendar
if [[ -f "${REPO_ROOT}/tests/fixtures/exchange_calendar.json" ]]; then
    DEFAULT_EXCHANGE_CALENDAR_PATH="${REPO_ROOT}/tests/fixtures/exchange_calendar.json"
else
    DEFAULT_EXCHANGE_CALENDAR_PATH="${REPO_ROOT}/../Exchange calendar registry/exchange-calendar/calendar.json"
fi

# ----------------------------------------------------------------------
# Parse arguments
# ----------------------------------------------------------------------
IDENTIFIERS_PATH="${CORP_ACTIONS_IDENTIFIERS_PATH:-$DEFAULT_IDENTIFIERS_PATH}"
ISO4217_PATH="${CORP_ACTIONS_ISO4217_PATH:-$DEFAULT_ISO4217_PATH}"
EXCHANGE_CALENDAR_PATH="${CORP_ACTIONS_EXCHANGE_CALENDAR_PATH:-$DEFAULT_EXCHANGE_CALENDAR_PATH}"
ACTIONS_PATH="${CORP_ACTIONS_ACTIONS_PATH:-actions.json}"
SCHEMA_PATH="${CORP_ACTIONS_SCHEMA_PATH:-schema.json}"
FETCH_SOURCE="yahoo"
TICKER_LIMIT=""
MIN_ACTIONS="1"
SKIP_FETCH=false
SKIP_TESTS=false
SKIP_BUILD=false
DRY_RUN=false
DO_COMMIT=false
TAG_VERSION=""
WEBHOOK_URL=""
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --identifiers)
            IDENTIFIERS_PATH="$2"; shift 2 ;;
        --iso4217)
            ISO4217_PATH="$2"; shift 2 ;;
        --exchange-calendar)
            EXCHANGE_CALENDAR_PATH="$2"; shift 2 ;;
        --actions)
            ACTIONS_PATH="$2"; shift 2 ;;
        --schema)
            SCHEMA_PATH="$2"; shift 2 ;;
        --fetch-source)
            FETCH_SOURCE="$2"; shift 2 ;;
        --ticker-limit)
            TICKER_LIMIT="$2"; shift 2 ;;
        --min-actions)
            MIN_ACTIONS="$2"; shift 2 ;;
        --skip-fetch)
            SKIP_FETCH=true; shift ;;
        --skip-tests)
            SKIP_TESTS=true; shift ;;
        --skip-build)
            SKIP_BUILD=true; shift ;;
        --dry-run)
            DRY_RUN=true
            SKIP_TESTS=true
            SKIP_BUILD=true
            shift ;;
        --commit)
            DO_COMMIT=true; shift ;;
        --tag)
            TAG_VERSION="$2"; shift 2 ;;
        --webhook-url)
            WEBHOOK_URL="$2"; shift 2 ;;
        --verbose)
            VERBOSE=true; shift ;;
        --tests)
            SKIP_TESTS=false; shift ;;
        --build)
            SKIP_BUILD=false; shift ;;
        --help|-h)
            grep '^#' "$0" | sed 's/^# //)'
            exit 0 ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2 ;;
    esac
done

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

error_exit() {
    echo "ERROR: $*" >&2
    exit 1
}

run_cmd() {
    if $VERBOSE; then
        "$@"
    else
        "$@" > /dev/null 2>&1
    fi
}

# ----------------------------------------------------------------------
# Validate fetch source (fail fast on broken sources)
# ----------------------------------------------------------------------
if ! $SKIP_FETCH; then
    case "$FETCH_SOURCE" in
        yahoo|sec|nasdaq) ;;
        *) error_exit "Unknown fetch source: $FETCH_SOURCE (valid: yahoo, sec, nasdaq)" ;;
    esac
    if [[ "$FETCH_SOURCE" == "sec" ]]; then
        error_exit "SEC EDGAR fetcher is currently broken (endpoint returns HTTP 500).
  Track progress at https://github.com/slimissa/corporate-actions/issues
  For now, use --fetch-source yahoo."
    fi
    if [[ "$FETCH_SOURCE" == "nasdaq" ]]; then
        error_exit "Nasdaq dividends fetcher is currently broken (API times out).
  Track progress at https://github.com/slimissa/corporate-actions/issues
  For now, use --fetch-source yahoo."
    fi
fi

# ----------------------------------------------------------------------
# Validate input files exist
# ----------------------------------------------------------------------
for f in "$IDENTIFIERS_PATH" "$ISO4217_PATH" "$EXCHANGE_CALENDAR_PATH" "$SCHEMA_PATH"; do
    [[ -f "$f" ]] || error_exit "Required file not found: $f"
done
# ----------------------------------------------------------------------
# Fetch new actions (optional)
# ----------------------------------------------------------------------
if ! $SKIP_FETCH; then
    log "Fetching actions from Yahoo Finance..."
    FETCH_SCRIPT="$REPO_ROOT/tools/fetch_yahoo_actions.py"
    [[ -f "$FETCH_SCRIPT" ]] || error_exit "Fetcher not found: $FETCH_SCRIPT"
    FETCH_OUTPUT="$REPO_ROOT/fetched_actions.json"
    ARGS=("$FETCH_SCRIPT" --identifiers "$IDENTIFIERS_PATH" --output "$FETCH_OUTPUT")
    [[ -n "$TICKER_LIMIT" ]] && ARGS+=(--ticker-limit "$TICKER_LIMIT")
    if $VERBOSE; then ARGS+=(--verbose); fi
    run_cmd python3 "${ARGS[@]}"

    if [[ -f "$FETCH_OUTPUT" ]]; then
        log "Merging fetched actions into $ACTIONS_PATH (fuzzy dedup)..."
        python3 - "$REPO_ROOT" "$ACTIONS_PATH" "$FETCH_OUTPUT" "$VERBOSE" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

repo_root = Path(sys.argv[1])
actions_path = repo_root / sys.argv[2]
fetch_path = Path(sys.argv[3])
verbose = sys.argv[4].lower() == "true"


def dedup_key(action):
    """Stable identity for an action across different ID schemes."""
    dates = action.get("dates") or {}
    ratio = action.get("ratio") or ""
    amount = action.get("amount")
    return (
        action.get("isin", ""),
        action.get("action_type", ""),
        dates.get("ex_date", ""),
        ratio,
        round(float(amount), 4) if amount is not None else 0.0,
    )


with open(actions_path) as f:
    current = json.load(f)
with open(fetch_path) as f:
    fetched = json.load(f)

current_actions = current.get("actions", [])
fetched_actions = fetched.get("actions", [])

existing_keys = {dedup_key(a) for a in current_actions}
new_actions = [a for a in fetched_actions if dedup_key(a) not in existing_keys]

if new_actions:
    current["actions"].extend(new_actions)
    current.setdefault("meta", {})["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(actions_path, "w") as f:
        json.dump(current, f, indent=2)
    print(f"Added {len(new_actions)} new actions (total: {len(current['actions'])}).")
    if verbose:
        for a in new_actions[:5]:
            print(f"  + {a.get('action_id')}")
        if len(new_actions) > 5:
            print(f"  ... and {len(new_actions) - 5} more")
else:
    print("No new actions to merge.")
PY
    else
        log "No fetched actions file produced; skipping merge."
    fi
fi

# ----------------------------------------------------------------------
# Derive impacts
# ----------------------------------------------------------------------
log "Deriving impact multipliers..."
run_cmd python3 "$REPO_ROOT/tools/derive_impacts.py" --actions "$ACTIONS_PATH"

# ----------------------------------------------------------------------
# Validate actions.json
# ----------------------------------------------------------------------
log "Validating actions.json..."
run_cmd python3 "$REPO_ROOT/tools/validate.py" \
    --actions "$ACTIONS_PATH" \
    --schema "$SCHEMA_PATH" \
    --identifiers "$IDENTIFIERS_PATH" \
    --iso4217 "$ISO4217_PATH" \
    --exchange-calendar "$EXCHANGE_CALENDAR_PATH" \
    --min-actions "$MIN_ACTIONS"

# ----------------------------------------------------------------------
# Run tests (optional)
# ----------------------------------------------------------------------
if ! $SKIP_TESTS; then
    HAVE_PYTEST=false
    if python3 -c "import pytest" >/dev/null 2>&1; then
        HAVE_PYTEST=true
    fi

    if $HAVE_PYTEST; then
        log "Running root test suite..."
        run_cmd python3 -m pytest "$REPO_ROOT/tests" -v

        log "Running Python wrapper tests..."
        (cd "$REPO_ROOT/wrappers/python" && run_cmd python3 -m pytest tests -v)
    else
        log "WARNING: pytest not installed; skipping Python tests."
    fi

    log "Running JavaScript wrapper tests..."
    (cd "$REPO_ROOT/wrappers/javascript" && run_cmd npm test)

    log "Running Go wrapper tests..."
    (cd "$REPO_ROOT/wrappers/go" && run_cmd go test ./registry -v)

    log "Running Rust wrapper tests..."
    (cd "$REPO_ROOT/wrappers/rust" && run_cmd cargo test)
fi

# ----------------------------------------------------------------------
# Build distribution artifacts (optional)
# ----------------------------------------------------------------------
if ! $SKIP_BUILD; then
    log "Building distribution artifacts..."
    run_cmd python3 "$REPO_ROOT/tools/build.py" --actions "$ACTIONS_PATH" --output-dir "$REPO_ROOT/dist"
fi

# ----------------------------------------------------------------------
# Notify on change (optional)
# ----------------------------------------------------------------------
if [[ -n "$WEBHOOK_URL" ]]; then
    log "Sending change notification..."
    run_cmd python3 "$REPO_ROOT/scripts/notify_on_change.py" \
        --actions "$ACTIONS_PATH" \
        --webhook-url "$WEBHOOK_URL"
fi

# ----------------------------------------------------------------------
# Commit and tag (optional)
# ----------------------------------------------------------------------
if $DO_COMMIT && ! $DRY_RUN; then
    log "Committing changes..."
    cd "$REPO_ROOT"
    git add "$ACTIONS_PATH" 2>/dev/null || true
    if git diff --cached --quiet; then
        log "No changes to commit."
    else
        git commit -m "Automated registry update"
    fi

    if [[ -n "$TAG_VERSION" ]]; then
        log "Tagging release $TAG_VERSION"
        git tag "$TAG_VERSION"
        git push origin "$TAG_VERSION"
    fi

    git push origin main
elif $DO_COMMIT && $DRY_RUN; then
    log "DRY RUN: would commit and push changes (skipped)."
fi

log "Update pipeline completed successfully."
exit 0