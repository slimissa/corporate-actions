#!/usr/bin/env bash
# Regenerate docs/facts.json and sync every doc that restates the counts.
#
# Run this before every commit that changes actions.json or the test count.
# It is the fix for the recurring "facts says 2059, doc says 2058" drift
# that has cost this project ~6 commit cycles across v1.2.x.
#
# Usage:
#     bash scripts/sync_counts.sh
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

python3 tools/update_facts.py

python3 - <<'PYEOF'
import json, re
from pathlib import Path

facts = json.loads(Path("docs/facts.json").read_text())
root = facts["root_test_count"]
a = facts["action_count"]
w = facts["wrapper_test_counts"]

# README.md
p = Path("README.md"); t = p.read_text()
t = re.sub(r"badge/tests-\d+-success", f"badge/tests-{root}-success", t, count=1)
t = re.sub(r"(\*\*Total tests\*\*:[^\n]*\n)\d+ root", rf"\g<1>{root} root", t, count=1)
t = re.sub(r"badge/actions-\d+-green", f"badge/actions-{a}-green", t, count=1)
t = re.sub(r"\*\*Actions\*\*:\s*\d+", f"**Actions**: {a}", t, count=1)
for k, n in [("python", "Python"), ("javascript", "JavaScript"), ("go", "Go"), ("rust", "Rust")]:
    t = re.sub(rf"({n} wrapper \| ✅ )\d+( tests)", rf"\g<1>{w[k]}\g<2>", t)
p.write_text(t)

# CONTRIBUTING.md
p = Path("CONTRIBUTING.md"); t = p.read_text()
t = re.sub(r"(Tests: `)\d+( passed)", rf"\g<1>{root}\g<2>", t, count=1)
p.write_text(t)

# docs/roadmap.md
p = Path("docs/roadmap.md"); t = p.read_text()
t = re.sub(r"(\|\s*Actions\s*\|\s*)\d+", rf"\g<1>{a}", t, count=1)
t = re.sub(r"(\|\s*Root tests\s*\|\s*)\d+", rf"\g<1>{root}", t, count=1)
p.write_text(t)

# docs/validation_layers.md
p = Path("docs/validation_layers.md"); t = p.read_text()
t = re.sub(r"\b\d{4}\s+actions\b", f"{a} actions", t)
p.write_text(t)

print(f"✓ synced to root={root}, actions={a}")
PYEOF

python3 tools/check_doc_facts.py
