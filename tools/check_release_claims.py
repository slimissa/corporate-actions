#!/usr/bin/env python3
"""
tools/check_release_claims.py
...
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = PROJECT_ROOT / "tools" / "release_claims.json"

class FatalError(SystemExit):
    def __init__(self, message: str, code: int = 2) -> None:
        print(f"error: {message}", file=sys.stderr)
        super().__init__(code)

def load_manifest() -> dict:
    if not MANIFEST.exists():
        raise FatalError(f"manifest not found: {MANIFEST}")
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FatalError(f"{MANIFEST}: invalid JSON: {exc}") from exc

ALLOWED_KEYS = {"file", "contains", "absent"}
DOC_FACTS_KEY = "doc-facts"

def check_claim(claim: dict) -> tuple[bool, str]:
    if "file" not in claim:
        return False, "claim has no 'file' key"
    unknown = sorted(set(claim) - ALLOWED_KEYS)
    if unknown:
        return False, (f"{claim['file']}: unknown claim key(s) {unknown}")
    path = PROJECT_ROOT / claim["file"]
    if not path.exists():
        return False, f"missing file: {claim['file']}"
    text = path.read_text(encoding="utf-8")
    notes = []
    if "contains" in claim:
        needle = claim["contains"]
        if needle not in text:
            return False, f"{claim['file']} does not contain {needle!r}"
        notes.append(f"contains {needle!r}")
    if "absent" in claim:
        needle = claim["absent"]
        if needle in text:
            return False, (f"{claim['file']} contains {needle!r}, which must be absent")
        notes.append(f"does not contain {needle!r}")
    if not notes:
        return True, f"{claim['file']} exists"
    return True, f"{claim['file']} " + " and ".join(notes)

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="check_release_claims")
    p.add_argument("version")
    p.add_argument("--list", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    manifest = load_manifest()
    claims = manifest.get(args.version)
    if claims is None:
        raise FatalError(f"no claims for version {args.version} in {MANIFEST.name}.")
    
    doc_facts = manifest.get(DOC_FACTS_KEY, [])
    labelled = [(args.version, c) for c in claims]
    labelled += [(DOC_FACTS_KEY, c) for c in doc_facts]

    results = []
    for section, claim in labelled:
        prefix = "" if section == args.version else f"[{section}] "
        if not isinstance(claim, dict):
            results.append((False, f"{prefix}not an object: {claim!r}"))
            continue
        ok, detail = check_claim(claim)
        results.append((ok, prefix + detail))

    rule = "=" * 60
    print(rule)
    print(f"  release claims — v{args.version}")
    print(rule)
    for ok, detail in results:
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] {detail}")
    print(rule)
    failed = [d for ok, d in results if not ok]
    if failed:
        print(f"  {len(failed)} claim(s) failed")
    else:
        print(f"  all {len(results)} claim(s) verified")
    return 0 if all(ok for ok, _ in results) else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except FatalError as exc:
        sys.exit(exc.code)
