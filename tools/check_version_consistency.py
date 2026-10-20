#!/usr/bin/env python3
"""Verify every version site in the repo agrees.

Sites (7):
  1. VERSION
  2. CHANGELOG.md top released heading
  3. actions.json meta.version
  4. wrappers/python/pyproject.toml
  5. wrappers/javascript/package.json
  6. wrappers/rust/Cargo.toml
  7. README.md registry badge

Exit codes:
  0 — all sites agree
  1 — mismatch (names each site and its value)
  2 — a site file is missing or malformed
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

def _read(path):
    p = REPO / path
    if not p.is_file():
        print(f"ERROR: missing site file: {path}", file=sys.stderr)
        sys.exit(2)
    return p.read_text(encoding="utf-8")

def _v_VERSION():
    return _read("VERSION").strip()

def _v_changelog():
    text = _read("CHANGELOG.md")
    for m in re.finditer(r"^## \[(\d+\.\d+\.\d+)\]", text, re.MULTILINE):
        return m.group(1)
    print("ERROR: CHANGELOG.md has no released ## [X.Y.Z] section", file=sys.stderr)
    sys.exit(2)

def _v_actions_json():
    v = json.loads(_read("actions.json")).get("meta", {}).get("version")
    if not v:
        print("ERROR: actions.json meta.version missing", file=sys.stderr)
        sys.exit(2)
    return v

def _v_pyproject():
    m = re.search(r'^version\s*=\s*"([\d.]+)"', _read("wrappers/python/pyproject.toml"), re.MULTILINE)
    if not m:
        print("ERROR: pyproject.toml version missing", file=sys.stderr)
        sys.exit(2)
    return m.group(1)

def _v_package_json():
    return json.loads(_read("wrappers/javascript/package.json"))["version"]

def _v_cargo():
    in_pkg = False
    for line in _read("wrappers/rust/Cargo.toml").splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            in_pkg = (s == "[package]")
        if in_pkg:
            m = re.match(r'^version\s*=\s*"([\d.]+)"', s)
            if m:
                return m.group(1)
    print("ERROR: Cargo.toml [package].version missing", file=sys.stderr)
    sys.exit(2)


def _v_readme():
    m = re.search(r"registry-v?(\d+\.\d+\.\d+)-orange", _read("README.md"))
    if not m:
        print("ERROR: README badge registry-X.Y.Z-orange missing", file=sys.stderr)
        sys.exit(2)
    return m.group(1)


SITES = [
    ("VERSION",                          _v_VERSION),
    ("CHANGELOG.md",                     _v_changelog),
    ("actions.json",                     _v_actions_json),
    ("wrappers/python/pyproject.toml",   _v_pyproject),
    ("wrappers/javascript/package.json", _v_package_json),
    ("wrappers/rust/Cargo.toml",         _v_cargo),
    ("README.md",                        _v_readme),
]

def main():
    versions = {}
    for name, fn in SITES:
        try:
            versions[name] = fn()
        except SystemExit:
            raise
        except Exception as e:
            print(f"ERROR reading {name}: {e}", file=sys.stderr)
            sys.exit(2)
    unique = set(versions.values())
    if len(unique) == 1:
        print(f"OK: all {len(SITES)} version sites say {unique.pop()}")
        return 0
    print("ERROR: version mismatch:", file=sys.stderr)
    for name, v in versions.items():
        print(f"  {name}: {v}", file=sys.stderr)
    return 1

if __name__ == "__main__":
    sys.exit(main())
