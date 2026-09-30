#!/usr/bin/env python3
"""Fetch a filing directly by accession number.

Usage:
    python3 scripts/corpus/fetch_by_accession.py <cik> <accession> <label>

Example:
    python3 scripts/corpus/fetch_by_accession.py 1326801 0001326801-22-000022 pos_01_meta_fb_to_meta_8k
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[2] / "tests" / "corpus" / "sec_symbol_change"
UA = os.environ.get(
    "SEC_EDGAR_USER_AGENT",
    "corporate-actions-registry corpus-fetch contact@example.com",
)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2

    cik, accession, label = sys.argv[1], sys.argv[2], sys.argv[3]
    cik_no_zeros = cik.lstrip("0") or "0"
    acc_no_dashes = accession.replace("-", "")

    base = f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{acc_no_dashes}"
    idx = json.loads(fetch(base + "/index.json"))
    items = idx.get("directory", {}).get("item", [])
    candidates = [
        i["name"] for i in items
        if i["name"].lower().endswith((".htm", ".html"))
    ]
    for name in candidates:
        low = name.lower()
        if "index" not in low and not low.startswith("ex"):
            doc = name
            break
    else:
        doc = candidates[0] if candidates else None

    if not doc:
        print("no HTML document in index", file=sys.stderr)
        return 1

    doc_url = f"{base}/{doc}"
    body = fetch(doc_url)
    out = CORPUS / f"{label}.html"
    out.write_bytes(body)

    print(f"wrote {out.name} ({len(body)} bytes)")
    print(f"source: {doc_url}")

    # Update manifest in place
    manifest_path = CORPUS / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    kind = "positive" if label.startswith("pos_") else "negative"
    entry = {
        "file": out.name,
        "cik": cik.zfill(10),
        "accession": accession,
        "source_url": doc_url,
        "fetched_at": __import__("time").strftime("%Y-%m-%d"),
    }
    if kind == "positive":
        entry["symbol"] = "<FILL IN>"
    else:
        entry["reason"] = "<FILL IN>"
    # Remove any prior entry for the same file
    manifest[kind] = [e for e in manifest[kind] if e.get("file") != out.name]
    manifest[kind].append(entry)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print("manifest updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
