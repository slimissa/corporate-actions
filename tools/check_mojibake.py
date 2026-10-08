#!/usr/bin/env python3
"""Detect UTF-8 / Latin-1 round-trip corruption in text files.

mojibake-check: skip — this file contains the patterns as literals

Some editors and paste operations save UTF-8 bytes as Latin-1, producing
sequences like `â€"` where `—` was intended. This check catches that
class of corruption before it lands in a commit.

Run:
    python3 tools/check_mojibake.py

Exit codes:
    0 - clean
    1 - one or more files contain mojibake patterns
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Byte sequences that indicate UTF-8 read as Latin-1.
MOJIBAKE_PATTERNS = [
    re.compile(r"â€"),       # em-dash, en-dash, curly quotes
    re.compile(r"â€™"),
    re.compile(r"â€œ"),
    re.compile(r"â€\x9d"),
    re.compile(r"â€”"),
    re.compile(r"â€“"),
    re.compile(r"Â£"),        # pound sign
    re.compile(r"Â©"),        # copyright
    re.compile(r"Ã©"),        # e-acute
    re.compile(r"Ã "),        # a-grave
    re.compile(r"Ã¨"),        # e-grave
    re.compile(r"â‚"),
    re.compile(r"â†"),        # arrows
    re.compile(r"âˆ"),        # math symbols
    re.compile(r"âœ"),        # checkmarks
    re.compile(r"Ã¢â‚¬â„¢"),
    re.compile(r"Ã¢â‚¬Å“"),
    re.compile(r"Ã¢â‚¬Â"),
]

# Directories to skip.
EXCLUDE_DIRS = {".git", ".venv", "__pycache__", "node_modules", "target", ".pytest_cache", "dist"}

# Extensions to check.
TEXT_EXT = {".md", ".py", ".json", ".txt", ".sh", ".js", ".go", ".rs", ".toml", ".yml", ".yaml", ".c", ".h"}


def _is_excluded(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & EXCLUDE_DIRS)


def _scan(path: Path) -> list[str]:
    """Return a list of mojibake fragments found in the file."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    # A file may declare itself exempt by mentioning the marker in its
    # first 5 lines. Used by this tool's own source, which contains the
    # mojibake patterns as literals.
    first_lines = "\n".join(text.splitlines()[:5])
    if "mojibake-check: skip" in first_lines:
        return []
    hits = []
    for pat in MOJIBAKE_PATTERNS:
        for m in pat.finditer(text):
            hits.append(m.group(0))
    return hits


def main() -> int:
    total_files = 0
    bad_files = 0

    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if _is_excluded(path):
            continue
        if path.suffix not in TEXT_EXT:
            continue
        total_files += 1
        hits = _scan(path)
        if hits:
            bad_files += 1
            rel = path.relative_to(REPO_ROOT)
            print(f"{rel}: {len(hits)} hit(s)")
            for frag in set(hits):
                print(f"  {frag!r}")

    print()
    print(f"Scanned {total_files} file(s), {bad_files} with mojibake.")
    return 1 if bad_files else 0


if __name__ == "__main__":
    sys.exit(main())
