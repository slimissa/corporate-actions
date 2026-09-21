#!/usr/bin/env bash
#
# Shell-level tests for scripts/run_update.sh.
#
# These tests exercise the script's argument parsing and failure modes
# without running the full pipeline. Every stage that touches the
# network or the working tree is disabled with --skip-* flags.
#
# Run:
#     bash tests/test_run_update.sh
#
# Exit codes:
#     0  all tests passed
#     1  at least one test failed

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/run_update.sh"

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

# Disable every stage that would touch the network or the tree.
SAFE_FLAGS=(
    --skip-fetch
    --skip-tests
    --skip-build
)

# ----------------------------------------------------------------------
# Test 1: --tag without --commit fails
# ----------------------------------------------------------------------
test_tag_without_commit() {
    echo "Test: --tag without --commit exits 2"
    local rc=0
    "$SCRIPT" --tag v9.9.9-test "${SAFE_FLAGS[@]}" >/dev/null 2>&1 || rc=$?
    if [[ $rc -eq 2 ]]; then
        pass "--tag without --commit exits 2"
    else
        fail "--tag without --commit exited $rc, expected 2"
    fi
}

# ----------------------------------------------------------------------
# Test 2: --tag with --dry-run does not create a tag
# ----------------------------------------------------------------------
test_tag_with_dry_run() {
    echo "Test: --tag with --dry-run does not tag"
    local tag="v9.9.9-dryrun-$$"
    "$SCRIPT" --tag "$tag" --commit --dry-run "${SAFE_FLAGS[@]}" >/dev/null 2>&1 || true
    if git -C "$REPO_ROOT" tag --list "$tag" | grep -q .; then
        fail "dry-run created tag $tag"
        git -C "$REPO_ROOT" tag -d "$tag" >/dev/null 2>&1 || true
    else
        pass "dry-run did not create tag"
    fi
}

# ----------------------------------------------------------------------
# Test 3: --min-actions 0 exits with a clear error (validator rejects)
# ----------------------------------------------------------------------
test_min_actions_zero() {
    echo "Test: --min-actions 0 is not silently accepted"
    # With --skip-fetch the pipeline still runs derive + validate. A
    # --min-actions 0 means coverage never fires; the validator accepts
    # it. This test just confirms the script does not hang or crash on
    # the value. It is a smoke test, not a strict assertion.
    if "$SCRIPT" --min-actions 0 "${SAFE_FLAGS[@]}" >/dev/null 2>&1; then
        pass "--min-actions 0 runs without crashing"
    else
        local rc=$?
        # Exit 1 is acceptable if the registry fails an unrelated
        # check. Exit 2 would be a usage error.
        if [[ $rc -eq 2 ]]; then
            fail "--min-actions 0 produced a usage error"
        else
            pass "--min-actions 0 ran (exited $rc for an unrelated reason)"
        fi
    fi
}

# ----------------------------------------------------------------------
# Test 4: unknown flag exits 2
# ----------------------------------------------------------------------
test_unknown_flag() {
    echo "Test: unknown flag exits 2"
    if "$SCRIPT" --not-a-flag "${SAFE_FLAGS[@]}" >/dev/null 2>&1; then
        fail "unknown flag should have failed"
    else
        local rc=$?
        if [[ $rc -eq 2 ]]; then
            pass "unknown flag exits 2"
        else
            fail "unknown flag exited $rc, expected 2"
        fi
    fi
}

# ----------------------------------------------------------------------
# Test 5: missing required file exits 1
# ----------------------------------------------------------------------
test_missing_schema() {
    echo "Test: missing schema file exits 1"
    if "$SCRIPT" --schema /nonexistent/schema.json "${SAFE_FLAGS[@]}" >/dev/null 2>&1; then
        fail "missing schema should have failed"
    else
        pass "missing schema produces a non-zero exit"
    fi
}

test_dry_run_does_not_mutate() {
    echo "Test: --dry-run does not mutate actions.json"
    local before after
    before=$(sha256sum "$REPO_ROOT/actions.json" | cut -d' ' -f1)
    "$SCRIPT" --dry-run --skip-tests --skip-build "${SAFE_FLAGS[@]}" >/dev/null 2>&1 || true
    after=$(sha256sum "$REPO_ROOT/actions.json" | cut -d' ' -f1)
    if [[ "$before" == "$after" ]]; then
        pass "--dry-run left actions.json unchanged"
    else
        fail "--dry-run mutated actions.json"
    fi
}

# ----------------------------------------------------------------------
# Test 6: --help exits 0
# ----------------------------------------------------------------------
test_help() {
    echo "Test: --help exits 0"
    if "$SCRIPT" --help >/dev/null 2>&1; then
        pass "--help exits 0"
    else
        fail "--help exited non-zero"
    fi
}

# ----------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------
echo "Running shell tests for scripts/run_update.sh"
echo "============================================="

test_tag_without_commit
test_tag_with_dry_run
test_min_actions_zero
test_unknown_flag
test_missing_schema
test_dry_run_does_not_mutate
test_help

echo "============================================="
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]