#!/usr/bin/env python3
"""Verify all version sites agree.

The Corporate Actions Registry has one version number that must appear
identically in every file that states it. If any two disagree, this
script fails and names the mismatches.

Sites (in priority order — first is source of truth):
  1. VERSION                            — the canonical file
  2. CHANGELOG.md                       — top released section
  3. actions.json                       — meta.version
  4. wrappers/python/pyproject.toml     — version
  5. wrappers/javascript/package.json   — version
  6. wrappers/rust/Cargo.toml           — version
  7. README.md                          — badge/registry-X.Y.Z-orange

Exit codes:
  0 — all sites agree
  1 — mismatch (names each site and its value)
  2 — a site file is missing or malformed
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

def read(path):
    p = REPO / path
    if not p.is_file():
        print(f"ERROR: missing site file: {path}", file=sys.stderr)
        sys.exit(2)
    return p.read_text(encoding="utf-8")

def version_from_VERSION_file():
    return read("VERSION").strip()

def version_from_changelog():
    text = read("CHANGELOG.md")
    # First "## [X.Y.Z]" heading that is NOT [Unreleased]
    for m in re.finditer(r"^## \[(\d+\.\d+\.\d+)\]", text, re.MULTILINE):
        return m.group(1)
    print("ERROR: CHANGELOG.md has no released ## [X.Y.Z] section", file=sys.stderr)
    sys.exit(2)

def version_from_actions_json():
    data = json.loads(read("actions.json"))
    v = data.get("meta", {}).get("version")
    if not v:
        print("ERROR: actions.json meta.version missing", file=sys.stderr)
        sys.exit(2)
    return v

def version_from_pyproject():
    text = read("wrappers/python/pyproject.toml")
    m = re.search(r'^version\s*=\s*"([\d.]+)"', text, re.MULTILINE)
    if not m:
        print("ERROR: pyproject.toml missing version", file=sys.stderr)
        sys.exit(2)
    return m.group(1)

def version_from_package_json():
    return json.loads(read("wrappers/javascript/package.json"))["version"]

def version_from_cargo_toml():
    text = read("wrappers/rust/Cargo.toml")
    # Only the [package] version, not dependencies
    in_pkg = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            in_pkg = (s == "[package]")
        if in_pkg:
            m = re.match(r'^version\s*=\s*"([\d.]+)"', s)
            if m:
                return m.group(1)
    print("ERROR: Cargo.toml [package].version missing", file=sys.stderr)
    sys.exit(2)

def version_from_readme_badge():
    text = read("README.md")
    m = re.search(r"badge/registry-(\d+\.\d+\.\d+)-orange", text)
    if not m:
        print("ERROR: README badge/registry-X.Y.Z-orange missing", file=sys.stderr)
        sys.exit(2)
    return m.group(1)

SITES = [
    ("VERSION",                          version_from_VERSION_file),
    ("CHANGELOG.md",                     version_from_changelog),
    ("actions.json",                     version_from_actions_json),
    ("wrappers/python/pyproject.toml",   version_from_pyproject),
    ("wrappers/javascript/package.json", version_from_package_json),
    ("wrappers/rust/Cargo.toml",         version_from_cargo_toml),
    ("README.md",                        version_from_readme_badge),
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

    print("ERROR: version mismatch across sites:", file=sys.stderr)
    for name, v in versions.items():
        print(f"  {name}: {v}", file=sys.stderr)
    print(f"\nUnique values: {sorted(unique)}", file=sys.stderr)
    return 1

if __name__ == "__main__":
    sys.exit(main())