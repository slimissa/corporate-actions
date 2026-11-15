#!/usr/bin/env bash
#
# Deterministic release pipeline for Corporate Actions.
# Usage: scripts/release.sh <version>
#
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
    echo "usage: scripts/release.sh <version>" >&2
    exit 2
fi

step() { echo; echo "=== $* ==="; }
run() { "$@"; }

gate() {
    local rc=0
    "$@" || rc=$?
    if [[ "$rc" -ne 0 ]]; then
        echo "FAIL: gate failed (exit $rc): $*" >&2
        exit "$rc"
    fi
}

# --- Preconditions ---------------------------------------------------------
step "Preconditions"
git fetch origin main
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
[[ "$BRANCH" == "main" ]] || { echo "FAIL: not on main ($BRANCH)" >&2; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "FAIL: tree is dirty" >&2; exit 1; }
if git rev-parse "v$VERSION" >/dev/null 2>&1; then
    echo "FAIL: tag v$VERSION already exists locally" >&2; exit 1
fi
echo "  preconditions OK"

# --- Version sites ---------------------------------------------------------
step "Version sites"
if [[ "$(cat VERSION)" == "$VERSION" ]]; then
    echo "FAIL: VERSION is already $VERSION" >&2; exit 1
fi
echo "$VERSION" > VERSION

python3 - <<PY
import json, re
from pathlib import Path
v = "$VERSION"

# actions.json
p = Path("actions.json")
d = json.loads(p.read_text())
d["meta"]["version"] = v
p.write_text(json.dumps(d, indent=2) + "\n")

# wrappers/python/pyproject.toml
p = Path("wrappers/python/pyproject.toml")
p.write_text(re.sub(r'^version\s*=\s*"[^"]+"', f'version = "{v}"', p.read_text(), count=1, flags=re.M))

# __init__.py
p = Path("wrappers/python/corporate_actions_registry/__init__.py")
p.write_text(re.sub(r'^__version__\s*=\s*"[^"]+"', f'__version__ = "{v}"', p.read_text(), count=1, flags=re.M))

# package.json
p = Path("wrappers/javascript/package.json")
d = json.loads(p.read_text())
d["version"] = v
p.write_text(json.dumps(d, indent=2) + "\n")

# Cargo.toml
p = Path("wrappers/rust/Cargo.toml")
p.write_text(re.sub(r'^version\s*=\s*"[^"]+"', f'version = "{v}"', p.read_text(), count=1, flags=re.M))

# README.md badge
p = Path("README.md")
p.write_text(re.sub(r'badge/registry-[0-9]+\.[0-9]+\.[0-9]+-', f'badge/registry-{v}-', p.read_text()))
PY

# CHANGELOG.md must already have the [1.3.0] section
grep -q "## \[$VERSION\]" CHANGELOG.md || { echo "FAIL: CHANGELOG.md missing [$VERSION] section" >&2; exit 1; }

# --- Regenerate -----------------------------------------------------------
step "Regenerate"
run python3 tools/update_facts.py
run bash scripts/sync_counts.sh

# --- Gate -----------------------------------------------------------------
step "Gates"
gate python3 tools/check_version_consistency.py
gate python3 tools/check_release_claims.py "$VERSION"
gate python3 tools/validate.py --actions actions.json --schema schema.json --no-strict-isin
gate python3 tools/check_snapshot_freshness.py
gate python3 tools/check_mojibake.py
gate python3 -m pytest tests/ -q -m "not network"

# --- Commit, push ---------------------------------------------------------
step "Commit and push"
git add -A
git commit -m "Release v$VERSION"
git push origin main

# --- Poll CI --------------------------------------------------------------
step "Waiting for CI"
sleep 15 # Give GitHub Actions time to start
RUN_ID=$(gh run list --branch main --limit 1 --json databaseId --jq '.[0].databaseId')
if [[ -n "$RUN_ID" ]]; then
    gh run watch "$RUN_ID" --exit-status || { echo "FAIL: CI failed" >&2; exit 1; }
else
    echo "WARN: Could not find CI run. Proceeding..."
fi

# --- Tag ------------------------------------------------------------------
step "Tag v$VERSION"
TAG_MSG="$(python3 - <<PY
import re
text = open("CHANGELOG.md").read()
m = re.search(r"## \[$VERSION\][^\n]*\n(.*?)(?=\n## |\Z)", text, re.S)
print((m.group(1).strip() if m else "")[:4000])
PY
)"
[[ -n "$TAG_MSG" ]] || { echo "FAIL: CHANGELOG body empty" >&2; exit 1; }

git tag -a "v$VERSION" -m "Release v$VERSION" -m "$TAG_MSG"
git push origin "v$VERSION"
echo "Released v$VERSION."
