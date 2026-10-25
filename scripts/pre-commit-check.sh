#!/usr/bin/env bash
# Run the full verification sequence before allowing a commit.
#
# Install:
#   cp scripts/pre-commit-check.sh .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
#
# Bypass (use sparingly):
#   git commit --no-verify
#
# This is the durable fix for a class of drift that produced six
# manual fix cycles across v1.2.0–v1.2.2: a change in one file requiring
# a matching change in another, where the second change is forgotten.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# Branch guard: refuse to commit on main. Phase-4 work happens on branches.
# If you're legitimately committing to main (release commits), set:
#     LAS_ALLOW_MAIN_COMMIT=1 git commit -m "..."
BRANCH=$(git branch --show-current)
if [[ "$BRANCH" == "main" ]] && [[ "${LAS_ALLOW_MAIN_COMMIT:-0}" != "1" ]]; then
    echo "❌ pre-commit: on branch 'main'. Commits to main are release-only."
    echo "   For feature work:  git checkout -b <branch-name>"
    echo "   For release:       LAS_ALLOW_MAIN_COMMIT=1 git commit -m \"...\""
    exit 1
fi

# Skip on docs-only commits? No — docs claims numbers, those claims drift.
# Run everything.

echo "# If this fails with "docs/facts.json is stale" or "doc says X, fact says Y":
#     bash scripts/sync_counts.sh
# then git add docs/ README.md CONTRIBUTING.md and retry.

=== pre-commit: update_facts --check ==="
python3 tools/update_facts.py --check || {
    echo "❌ facts.json is stale. Run: python3 tools/update_facts.py"
    exit 1
}

echo "=== pre-commit: check_doc_facts ==="
python3 tools/check_doc_facts.py || exit 1

echo "=== pre-commit: check_sibling_versions ==="
python3 tools/check_sibling_versions.py || exit 1

echo "=== pre-commit: check_mojibake ==="
python3 tools/check_mojibake.py || exit 1

echo "=== pre-commit: ruff ==="
python3 -m ruff check tests/ tools/ examples/ scripts/ || exit 1

echo "=== pre-commit: pytest (root suite, no network) ==="
# pytest success summary is "N passed, M skipped, K deselected"
# — it does NOT contain "0 failed". Detect failures by looking for
# a nonzero failed/error count instead of assuming a literal.
RESULT=$(python3 -m pytest tests/ -q -m "not network" 2>&1)
LAST_LINE=$(echo "$RESULT" | tail -1)
echo "$LAST_LINE"
if echo "$LAST_LINE" | grep -qE "[1-9][0-9]* (failed|error)"; then
    echo "❌ pytest failed. Failed tests:"
    echo "$RESULT" | grep -E "^FAILED" | head -10
    exit 1
fi

echo "✓ pre-commit: all checks passed"
