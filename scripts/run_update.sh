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
#   --fetch-source SOURCE       Data source (default: yahoo).
#                               Valid: yahoo, sec.
#                               'nasdaq' was removed in v1.0.1.
#   --ticker-limit N            Limit fetcher to first N tickers
#   --min-actions N             Minimum number of actions required (default: 100)
#   --skip-fetch                Do not run any fetcher
#   --skip-tests                Do not run test suites
#   --skip-build                Do not run build.py
#   --dry-run                   Show what would happen; do not commit or tag
#   --commit                    Commit changes after success
#   --tag VERSION               Tag the release after success (requires --commit)
#   --webhook-url URL           Send notification to webhook on change
#   --verbose                   Print verbose output
#   --tests                     Override --dry-run: run tests anyway
#   --build                     Override --dry-run: build anyway
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
# Helper functions
#
# Defined before any caller. The cross-flag validation block below uses
# both log() and error_exit(); if these were declared later in the file,
# Bash would exit 127 ("command not found") rather than 2.
# ----------------------------------------------------------------------
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

error_exit() {
    echo "ERROR: $*" >&2
    exit 1
}

usage_error() {
    echo "ERROR: $*" >&2
    exit 2
}

run_cmd() {
    if $VERBOSE; then
        "$@"
        return $?
    fi
    local tmp rc
    tmp="$(mktemp)"
    "$@" > "$tmp" 2>&1 && rc=0 || rc=$?
    if [[ $rc -eq 0 ]]; then
        rm -f "$tmp"
        return 0
    fi
    echo "--- command failed (exit $rc): $*" >&2
    cat "$tmp" >&2
    rm -f "$tmp"
    return $rc
}

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
MIN_ACTIONS="100"
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
            grep '^#' "$0" | sed 's/^# //'
            exit 0 ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2 ;;
    esac
done

# ----------------------------------------------------------------------
# Cross-flag validation
# ----------------------------------------------------------------------
if [[ -n "$TAG_VERSION" && "$DO_COMMIT" != "true" ]]; then
    usage_error "--tag requires --commit"
fi

if [[ -n "$TAG_VERSION" && "$DRY_RUN" == "true" ]]; then
    log "DRY RUN: would tag $TAG_VERSION (skipped)."
    TAG_VERSION=""
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
    case "$FETCH_SOURCE" in
        yahoo)
            log "Fetching actions from Yahoo Finance..."
            FETCH_SCRIPT="$REPO_ROOT/tools/fetch_yahoo_actions.py"
            FETCH_OUTPUT="$REPO_ROOT/fetched_actions.json"
            LIMIT_FLAG="--ticker-limit"
            ;;
        sec)
            log "Fetching actions from SEC EDGAR..."
            FETCH_SCRIPT="$REPO_ROOT/tools/fetch_sec_edgar_actions.py"
            FETCH_OUTPUT="$REPO_ROOT/sec_actions.json"
            LIMIT_FLAG="--cik-limit"
            ;;
        nasdaq)
            usage_error "The Nasdaq fetcher was removed in v1.0.1.
  Use --fetch-source yahoo instead."
            ;;
        *)
            usage_error "Unknown fetch source: $FETCH_SOURCE (valid: yahoo, sec)"
            ;;
    esac

    [[ -f "$FETCH_SCRIPT" ]] || error_exit "Fetcher not found: $FETCH_SCRIPT"
    ARGS=("$FETCH_SCRIPT" --identifiers "$IDENTIFIERS_PATH" --output "$FETCH_OUTPUT")
    [[ -n "$TICKER_LIMIT" ]] && ARGS+=("$LIMIT_FLAG" "$TICKER_LIMIT")
    if $VERBOSE; then ARGS+=(--verbose); fi
    run_cmd python3 "${ARGS[@]}"

    if [[ -f "$FETCH_OUTPUT" ]]; then
        if $DRY_RUN; then
            log "DRY RUN: would merge $FETCH_OUTPUT into $ACTIONS_PATH."
        else
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
    if amount is None:
        amount_val = 0.0
    else:
        try:
            amount_val = float(amount)
        except (TypeError, ValueError):
            # Refuse rather than silently dedup on a sentinel. A
            # non-numeric amount is a data error and should surface
            # loudly, not turn into a different key.
            raise SystemExit(
                f"Error: action {action.get('action_id', '?')} has "
                f"non-numeric amount {amount!r}"
            )
    return (
        action.get("isin", ""),
        action.get("action_type", ""),
        dates.get("ex_date", ""),
        ratio,
        round(amount_val, 4),
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
    current.setdefault("meta", {})["updated_at"] = (
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
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
        fi
    fi

    else
        log "No fetched actions file produced; skipping merge."
    fi
fi

# ----------------------------------------------------------------------
# Derive impacts
# ----------------------------------------------------------------------
if $DRY_RUN; then
    log "DRY RUN: would derive impact multipliers (skipped)."
else
    log "Deriving impact multipliers..."
    run_cmd python3 "$REPO_ROOT/tools/derive_impacts.py" --actions "$ACTIONS_PATH"
fi

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
        if [[ -n "$TAG_VERSION" ]]; then
            error_exit "Refusing to tag $TAG_VERSION: no changes were committed."
        fi
    else
        git commit -m "Automated registry update"
        if [[ -n "$TAG_VERSION" ]]; then
            log "Tagging release $TAG_VERSION"
            if git rev-parse "$TAG_VERSION" >/dev/null 2>&1; then
                log "Deleting stale local tag $TAG_VERSION"
                git tag -d "$TAG_VERSION"
            fi
            git tag "$TAG_VERSION"
            git push origin "$TAG_VERSION"
        fi
    fi

    git push origin main
    if $DO_COMMIT && $SKIP_TESTS; then
        usage_error "--commit requires tests to run. Remove --skip-tests or drop --commit."
    fi  
elif $DO_COMMIT && $DRY_RUN; then
    log "DRY RUN: would commit and push changes (skipped)."
fi

log "Update pipeline completed successfully."
exit 0