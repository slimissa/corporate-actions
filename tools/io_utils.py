"""Shared I/O utilities for the Corporate Actions Registry tools."""

from pathlib import Path


def write_atomic(path: Path, payload: str) -> None:
    """Write payload via a temp file + rename.

    Uses write_bytes, not write_text: Path.write_text translates \\n
    to \\r\\n on Windows, doubling the CSV line terminator. See issue #2.

    A killed process between the two steps leaves the original
    untouched rather than truncated.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(payload.encode("utf-8"))
    tmp.replace(path)