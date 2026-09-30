# SEC Symbol-Change Corpus

Labeled 8-K filings for `extract_new_symbol`.

## What this is

`extract_new_symbol` scans SEC 8-K filings for sentences that announce
a symbol change and returns the new ticker. Its regex patterns cannot
tell a real announcement from cover-page boilerplate or a
"Trading Symbol(s)" label on a different kind of filing. This corpus
is the labeled data that proves the extractor makes the right
distinction.

Two positives and nine negatives is small. Small is fine. The corpus
is the specification: whenever a real filing exposes a new failure
mode, add it here before fixing the extractor.

## Files

| File | Purpose |
|------|---------|
| `manifest.json` | Ground truth — the labeled filing list |
| `BASELINE.md` | Last recorded TP/FP numbers |
| `pos_*.html` | Filings that announce a symbol change |
| `neg_*.html` | Filings that mention "symbol" or "ticker" but announce no change |

The `.html` files are raw documents fetched from SEC EDGAR. Their
filenames encode the classification.

## The manifest

`manifest.json` has this shape:

```json
{
  "version": "1.0.0",
  "positive": [
    {"file": "pos_01_meta_fb_to_meta_8k.html", "symbol": "META"},
    {"file": "pos_04_fisv_to_fi_8k.html", "symbol": "FI"}
  ],
  "negative": [
    {"file": "neg_01_aapl_earnings_8k.html", "reason": "quarterly earnings"},
    {"file": "neg_10_fisv_notes_8k.html", "reason": "note issuance"}
  ]
}
```

- `positive[].symbol` — the ticker the extractor must return
- `negative[].reason` — one-line note explaining the filing

Every `.html` file on disk must appear in one of the two lists.
A file without a manifest entry is invisible to the tests.

## The two tests

**`test_corpus_diagnostic`** runs the extractor against every filing
and prints a TP/FP table. It never asserts — it reports. Use it
during development.

```bash
python3 -m pytest tests/test_fetch_sec_edgar_actions.py::test_corpus_diagnostic -v -s
```

**`test_corpus_extraction_accuracy`** is the exit gate. It asserts
every positive produces the expected symbol and every negative
produces `None`.

```bash
python3 -m pytest tests/test_fetch_sec_edgar_actions.py::test_corpus_extraction_accuracy -v
```

## Current state

Recorded in `BASELINE.md`:

```
True positives:  2/2
False positives: 0/9
```

## Why this corpus exists

The extractor uses regexes to find symbol changes in 8-K filings.
The regexes are good at matching phrasing. They are bad at telling
whether the phrasing describes a real change.

Cover pages of every 8-K contain a "Trading Symbol(s)" table.
Earnings releases mention the ticker. Split announcements use the
word "symbol" in the header. Notes issuances say "will trade under
the symbols 'FI27', 'FI30'" for debt instruments.

Without labeled data, the extractor would either miss real changes
or flag dozens of non-events. The corpus pins the boundary.

## Adding a filing

### 1. Find the accession number

- Browse the company's 8-K filings on EDGAR:
  `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=<CIK>&type=8-K`
- Or search EDGAR full-text:
  `https://efts.sec.gov/LATEST/search-index?q=%22begin+trading+under+the+symbol%22&forms=8-K`

The accession number looks like `0001326801-22-000070`.

### 2. Fetch by accession

```bash
python3 scripts/corpus/fetch_by_accession.py <cik> <accession> <label>
```

Example:

```bash
python3 scripts/corpus/fetch_by_accession.py \
    1326801 \
    0001326801-22-000070 \
    pos_01_meta_fb_to_meta_8k
```

The script downloads the primary HTML document and adds a manifest
entry with a placeholder symbol or reason.

### 3. Inspect the file

Before classifying, read every sentence containing "symbol":

```bash
python3 /tmp/inspect.py tests/corpus/sec_symbol_change/<label>.html
```

If `/tmp/inspect.py` is missing:

```bash
cat > /tmp/inspect.py <<'PY'
import re
import sys
from pathlib import Path

html = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
text = re.sub(r"<[^>]+>", " ", html)
text = re.sub(r"&nbsp;?", " ", text)
text = re.sub(r"&amp;?", "&", text)
text = re.sub(r"\s+", " ", text)

for m in re.finditer(r"[^.]{0,150}symbol[^.]{0,150}\.", text, re.IGNORECASE):
    print(m.group(0).strip())
    print("---")
PY
```

### 4. Classify

**Positive** — the filing contains a sentence that announces a
ticker change. The symbol in the sentence is the new ticker.

**Negative** — the filing mentions "symbol" or "ticker" but does not
announce a change. Common sources:

- Cover-page "Trading Symbol(s)" table
- Earnings release that references the ticker
- Notes issuance: "will trade under the symbols 'FI27', 'FI30'..."
- Split announcement that uses "symbol" in the header

If a filing fits neither, discard it. Do not guess.

### 5. Update the manifest

Either edit `manifest.json` directly, or rerun
`/tmp/rebuild_manifest.py` with the updated `POSITIVES` and
`NEGATIVES` dicts:

```bash
python3 /tmp/rebuild_manifest.py
```

The manifest entry must have:

- `file` — the filename
- Positive: `symbol` — the expected ticker
- Negative: `reason` — a one-line description

### 6. Verify

```bash
python3 -m pytest tests/test_fetch_sec_edgar_actions.py::test_corpus_diagnostic -v -s
python3 -m pytest tests/test_fetch_sec_edgar_actions.py::test_corpus_extraction_accuracy -v
```

The diagnostic shows what the extractor does. The accuracy test
asserts it. If the accuracy test fails, the extractor doesn't match
the corpus.

## The rule

**Never modify a filing's classification to make a failing test pass.**

If `test_corpus_extraction_accuracy` fails, one of two things is true:

1. **The extractor is wrong.** Fix the extractor.
2. **The filing is misclassified.** Re-read it and correct the
   manifest.

Do not:

- Delete a positive because the extractor misses it
- Reclassify a positive as a negative
- Change the expected symbol to whatever the extractor returned

The corpus is the specification. The extractor conforms to the
corpus, not the other way around. If you believe a corpus entry is
wrong, open an issue with the reasoning. Do not silently edit.

## Extending the corpus

The corpus grows when a real filing exposes a new failure mode:

- An 8-K that ships through the fetcher and extracts the wrong symbol
- An 8-K that gets silently skipped and should not have been
- A phrasing variant that the regexes don't handle

Add the filing to the corpus **before** fixing the extractor. That
way the fix is proven by the test, not by inspection.

## Why only two positives

A small corpus that is correct is more valuable than a large one that
is wrong. Two positives establish that the extractor handles two
distinct phrasings. Nine negatives establish that it rejects nine
classes of near-miss.

If you add a positive, verify the extractor still passes before
committing. If it fails, either the extractor needs widening or the
positive is misclassified. Both outcomes are useful.

## Related

- `tools/fetch_sec_edgar_actions.py` — the extractor under test
- `scripts/corpus/fetch_by_accession.py` — fetch one filing by accession
- `scripts/corpus/fetch_corpus.py` — bulk fetch by date range
- `BASELINE.md` — last recorded TP/FP numbers
