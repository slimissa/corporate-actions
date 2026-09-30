#!/usr/bin/env python3
"""Fetch SEC 8-K filings into the symbol-change corpus.

Given a list of (label, cik, date_from, date_to), find the first 8-K
filed in the range, download its primary document, and write it to
tests/corpus/sec_symbol_change/<label>.html.

Usage:
    python3 scripts/corpus/fetch_corpus.py

Edit the FILINGS list below to add or remove candidates.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[2] / "tests" / "corpus" / "sec_symbol_change"
UA = os.environ.get(
    "SEC_EDGAR_USER_AGENT",
    "corporate-actions-registry corpus-fetch contact@example.com",
)

FILINGS = [
    # label, cik, date_from, date_to
    ("pos_01_meta_fb_to_meta_8k",   "1326801",  "2022-06-01", "2022-06-30"),
    ("pos_02_sq_to_xyz_8k",         "1512673",  "2025-01-01", "2025-01-31"),
    ("pos_03_antm_to_elv_8k",       "1099800",  "2022-06-01", "2022-06-30"),
    ("pos_04_fisv_to_fi_8k",        "798354",   "2023-07-01", "2023-07-31"),
    # Fifth positive: fill in from EDGAR full-text search
    ("neg_01_aapl_earnings_8k",     "320193",   "2025-01-01", "2025-04-30"),
    ("neg_02_msft_dividend_8k",     "789019",   "2025-01-01", "2025-04-30"),
    ("neg_03_nvda_split_8k",        "1045810",  "2024-04-01", "2024-07-31"),
    ("neg_04_jpm_earnings_8k",      "19617",    "2025-01-01", "2025-04-30"),
    ("neg_05_amzn_earnings_8k",     "1018724",  "2025-01-01", "2025-04-30"),
    ("neg_06_googl_earnings_8k",    "1652044",  "2025-01-01", "2025-04-30"),
    ("neg_07_meta_earnings_8k",     "1326801",  "2025-01-01", "2025-04-30"),
    ("neg_08_tsla_earnings_8k",     "1318605",  "2025-01-01", "2025-04-30"),
    ("neg_09_brk_earnings_8k",      "1067983",  "2025-01-01", "2025-04-30"),
    ("neg_10_generic_exhibit_8k",   "320193",   "2024-01-01", "2024-12-31"),
]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def padded(cik: str) -> str:
    """Zero-pad to 10 digits without going through an int (avoids octal)."""
    return cik.lstrip("0").zfill(10)


def find_filing(cik: str, date_from: str, date_to: str) -> tuple[str, str] | None:
    """Return (accession, primary_document) for the first 8-K in the range."""
    url = f"https://data.sec.gov/submissions/CIK{padded(cik)}.json"
    data = json.loads(fetch(url))
    recent = data["filings"]["recent"]
    for form, acc, date, doc in zip(
        recent["form"],
        recent["accessionNumber"],
        recent["filingDate"],
        recent["primaryDocument"],
    ):
        if form == "8-K" and date_from <= date <= date_to:
            return acc, doc
    return None


def primary_url(cik: str, accession: str) -> str:
    """Build the index.json URL for a filing."""
    return (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{cik.lstrip('0') or '0'}/{accession.replace('-', '')}"
    )


def pick_document(base: str) -> str | None:
    """Return the primary HTML document name from a filing index."""
    idx = json.loads(fetch(base + "/index.json"))
    items = idx.get("directory", {}).get("item", [])
    candidates = [
        i["name"] for i in items
        if i["name"].lower().endswith((".htm", ".html"))
    ]
    # Prefer the document whose name doesn't start with 'ex' (exhibits)
    # and doesn't contain 'index'.
    for name in candidates:
        low = name.lower()
        if "index" not in low and not low.startswith("ex"):
            return name
    return candidates[0] if candidates else None


def main() -> int:
    CORPUS.mkdir(parents=True, exist_ok=True)
    manifest_path = CORPUS / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    for label, cik, df, dt in FILINGS:
        out = CORPUS / f"{label}.html"
        if out.exists():
            print(f"skip {label} (exists)")
            continue

        print(f"fetch {label}: CIK {cik} {df}..{dt}")
        found = find_filing(cik, df, dt)
        if not found:
            print("  no 8-K found in range; widen the dates")
            continue

        accession, _ = found
        base = primary_url(cik, accession)
        doc = pick_document(base)
        if not doc:
            print("  no HTML document in index")
            continue

        doc_url = f"{base}/{doc}"
        body = fetch(doc_url)
        out.write_bytes(body)
        print(f"  wrote {out.name} ({len(body)} bytes)")
        print(f"  source: {doc_url}")

        # Append to the manifest
        kind = "positive" if label.startswith("pos_") else "negative"
        entry = {
            "file": out.name,
            "cik": padded(cik),
            "accession": accession,
            "source_url": doc_url,
            "fetched_at": time.strftime("%Y-%m-%d"),
        }
        if kind == "positive":
            entry["symbol"] = "<FILL IN>"  # user confirms
        else:
            entry["reason"] = "<FILL IN>"
        manifest[kind].append(entry)

        time.sleep(0.2)  # SEC allows 10 req/s

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"\nmanifest updated: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
