# -*- coding: utf-8 -*-
from pathlib import Path


# ----------------------------------------------------------------------
# #44: fetch_corpus must not re-fetch body/index after find_filing
# ----------------------------------------------------------------------

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "scripts" / "corpus" / "fetch_corpus.py"


def test_fetch_corpus_returns_body_from_find_filing():
    """find_filing returns (accession, doc, body) so caller does not re-fetch."""
    src = SRC.read_text()
    assert "return acc, doc, body" in src, "find_filing must return 3-tuple"
    assert "accession, doc, body = found" in src, "caller must unpack body"


def test_fetch_corpus_no_redundant_refetch_in_main():
    """main() must not call pick_document or body=fetch after find_filing."""
    src = SRC.read_text()
    idx = src.find("def main()")
    assert idx >= 0, "main() not found"
    body = src[idx:]
    assert "pick_document(" not in body, "pick_document still called in main()"
    assert "body = fetch(" not in body, "body re-fetched in main()"
