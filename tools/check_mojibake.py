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
from typing import Optional

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
    # U+FFFD replacement character: UTF-8 was corrupted at read time.
    if '\ufffd' in text:
        hits.append('\ufffd (U+FFFD)')
    return hits


def _check_fence(path: Path) -> Optional[str]:
    """Return a description of unclosed code fence, or None if OK.

    State machine tracking the opening fence character (``` or ~~~).
    A fence closes only when a matching-kind fence of equal-or-greater
    length appears. Mixing backtick and tilde fences in one file is
    valid; counting them independently would false-positive on any file
    that uses both.

    Only meaningful for .md files. Exempt files are honored via the
    same 'mojibake-check: skip' marker used by _scan.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
    first_lines = "\n".join(text.splitlines()[:5])
    if "mojibake-check: skip" in first_lines:
        return None

    # (char, length) of the currently-open fence, or None.
    open_marker: Optional[tuple[str, int]] = None
    open_line = 0
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = re.match(r"^(`{3,}|~{3,})", line)
        if not m:
            continue
        marker = m.group(1)
        char = marker[0]
        length = len(marker)
        if open_marker is None:
            open_marker = (char, length)
            open_line = lineno
        elif open_marker[0] == char and length >= open_marker[1]:
            open_marker = None
    if open_marker is not None:
        char, length = open_marker
        return f"unclosed {char * 3} fence opened at line {open_line}"
    return None


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Detect mojibake, replacement chars, and unclosed fences."
    )
    parser.add_argument("--path", type=Path, default=None,
                        help="Scan a single file instead of the whole tree.")
    parser.add_argument("--quiet", action="store_true",
                        help="Exit code only; no per-file listing.")
    args = parser.parse_args()

    if args.path is not None:
        paths = [args.path]
    else:
        paths = [p for p in sorted(REPO_ROOT.rglob("*"))
                 if p.is_file()
                 and not _is_excluded(p)
                 and p.suffix in TEXT_EXT]

    total_files = 0
    bad_files = 0
    for path in paths:
        total_files += 1
        hits = _scan(path)
        fence = _check_fence(path) if path.suffix == ".md" else None
        if not hits and not fence:
            continue
        bad_files += 1
        if args.quiet:
            continue
        rel = path.relative_to(REPO_ROOT) if args.path is None else path
        if hits:
            print(f"{rel}: {len(hits)} mojibake hit(s)")
            for frag in set(hits):
                print(f"  {frag!r}")
        if fence:
            print(f"{rel}: {fence}")

    if not args.quiet:
        print()
        print(f"Scanned {total_files} file(s), {bad_files} with issues.")
    return 1 if bad_files else 0


if __name__ == "__main__":
    sys.exit(main())
