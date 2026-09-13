---
name: Action update
about: Report a missing, incorrect, or outdated corporate action
title: '[Action] '
labels: ['data-update', 'action-update']
assignees: []
---

<!--
Thanks for helping improve the Corporate Actions Registry.

This template is for reporting a specific corporate action that is
missing, wrong, or out of date. Please fill in as many fields as you
can. If a field is unknown, leave it blank.

Once submitted, a maintainer will verify against the source URL you
provide. If correct, the action is added to actions.json in the next
weekly update cycle or immediately via PR.

Please do NOT use this template for:
  - Adding a new instrument (use the Data source template instead)
  - Reporting a general bug (use the Bug report template)
  - Asking a question (use GitHub Discussions)
-->

## Summary

<!-- One-line description, e.g. "NVDA 10:1 split missing" -->

## Action details

### Action type

<!-- Check exactly one. See docs/action_types.md for definitions. -->

- [ ] `SPLIT` — forward stock split
- [ ] `REVERSE_SPLIT` — reverse stock split
- [ ] `DIVIDEND` — regular cash dividend
- [ ] `SPECIAL_DIVIDEND` — one-time cash dividend
- [ ] `SYMBOL_CHANGE` — ticker change (ISIN unchanged)
- [ ] `SPINOFF` — subsidiary separation
- [ ] `DELISTING` — removal from exchange
- [ ] `MERGER` — acquisition (placeholder in v1.0.0, not yet populated)

### Instrument

| Field | Value |
|-------|-------|
| ISIN | `US...` |
| Ticker | `AAPL` |
| Exchange MIC | `XNAS` |
| Currency | `USD` |

<!--
ISIN is the permanent identifier. If you do not know it, provide the
ticker and exchange and a maintainer will look it up. The ISIN takes
precedence over the ticker when both are given.
-->

### Dates

All dates in `YYYY-MM-DD` format. Leave blank if unknown.

| Date | Value |
|------|-------|
| Announcement | |
| Ex-date | |
| Record date | |
| Effective / payment date | |

<!--
Which dates are required depends on the action type. See docs/action_types.md
for the exact rules. Roughly:
  - SPLIT: announcement, ex_date, effective_date
  - DIVIDEND: announcement, ex_date, record_date, effective_date
  - SYMBOL_CHANGE: announcement, effective_date
  - DELISTING: announcement, effective_date
-->

### Action-specific fields

**For SPLIT and REVERSE_SPLIT:**

| Field | Value |
|-------|-------|
| Ratio | `10:1` |

<!-- Ratio format is "new:old". A 10-for-1 forward split is "10:1". A 1-for-10 reverse split is "1:10". -->

**For DIVIDEND and SPECIAL_DIVIDEND:**

| Field | Value |
|-------|-------|
| Amount per share | `0.25` |
| Currency | `USD` |

**For SYMBOL_CHANGE:**

| Field | Value |
|-------|-------|
| Old ticker | `FB` |
| New ticker | `META` |

**For SPINOFF:**

| Field | Value |
|-------|-------|
| Spun-off entity name | |
| Spun-off ISIN (if assigned) | |
| Distribution ratio | `1:3` (one share of new for every three held) |

**For DELISTING:**

| Field | Value |
|-------|-------|
| Reason | merger / bankruptcy / voluntary / regulatory |
| Acquirer ISIN (if merger) | |

**For MERGER:**

| Field | Value |
|-------|-------|
| Acquirer ISIN | |
| Exchange ratio | `1.28:1` (acquirer:target) |
| Cash component per share | `0` |

## Source

**Required.** Every action must have a source URL that a maintainer can
verify. Prefer primary sources (SEC filings, exchange announcements, official
company press releases). Do not use Wikipedia, Yahoo Finance summary pages,
or third-party blogs unless no primary source exists.

| Field | Value |
|-------|-------|
| Source type | SEC 8-K / SEC S-4 / exchange announcement / company press release / other |
| Source URL | `https://...` |
| Verification URL | `https://...` (optional secondary source) |

## Correction vs. addition

- [ ] This action is **missing** from the registry entirely.
- [ ] This action is **present but incorrect**. Provide the details below.

If this is a correction, state exactly what is wrong:

| Field | Current value in registry | Correct value |
|-------|---------------------------|---------------|
| | | |

<!-- Example:
| ratio | 10:1 | 10:1 was correct, but ex_date should be 2024-06-10 not 2024-06-11 |
-->

## Impact on existing data

<!--
Actions affect historical P&L, price adjustment, and position reconciliation.
Flag any downstream impact:
-->

- [ ] This action changes the adjusted price history for the instrument.
- [ ] This action affects dividend-adjusted total return calculations.
- [ ] This action changes a previously reported share count.
- [ ] This action was already covered by a different `action_id` in the registry (potential duplicate).

## Evidence

<!-- Paste a short excerpt from the source. Example from an SEC 8-K:

"NVIDIA today announced that its Board of Directors declared a ten-for-one
forward stock split of the Company's common stock. The split will be
effected through the distribution of nine additional shares of common
stock for each outstanding share of common stock."

Do not paste more than ~15 lines. Include the URL above.
-->

```
<paste excerpt here>
```

## Suggested JSON entry

<!--
Optional, for advanced reporters. If you can construct the full action
object in JSON, paste it below. A maintainer will validate against
schema.json.
-->

```json
{
  "isin": "US67066G1040",
  "action_id": "US67066G1040-SPLIT-2024-06-10-10-1",
  "action_type": "SPLIT",
  "ratio": "10:1",
  "dates": {
    "announcement": "2024-05-22",
    "ex_date": "2024-06-10",
    "record_date": "2024-06-07",
    "effective_date": "2024-06-10"
  },
  "status": "COMPLETED",
  "provenance": {
    "source": "NVIDIA press release",
    "source_url": "https://nvidianews.nvidia.com/news/..."
  },
  "impact": {
    "price_multiplier": 0.1,
    "share_multiplier": 10.0,
    "cash_adjustment": 0.0
  }
}
```

## Checklist

Before submitting, please confirm:

- [ ] I have searched existing issues to make sure this action is not already reported.
- [ ] I have provided at least one source URL that a maintainer can verify.
- [ ] The action type I checked matches the actual event.
- [ ] All dates I provided are in `YYYY-MM-DD` format.
- [ ] If this is a correction, I have described exactly what is wrong and what it should be.
- [ ] I understand that any accepted change to `actions.json` will appear in the next release after the weekly update cycle.

## Additional context

<!--
Anything else that would help a maintainer verify this action. For example:
  - Links to the same event on other exchanges or markets
  - Related actions (e.g. a special dividend declared alongside a regular one)
  - Screenshots of the source (only if the source is not linkable)
-->

---

**Maintainer notes** (do not edit):

- [ ] Action verified against the source URL provided.
- [ ] All dates and ratios cross-checked against a secondary source.
- [ ] No duplicate exists under a different `action_id`.
- [ ] `impact` block derived (not manually entered) via `derive_impacts.py`.
- [ ] Entry added to `actions.json`, validated, and included in next release.
- [ ] If this is a correction, the previous entry has been removed or updated.
```

## What this template provides

**Structured fields by action type.** A single form that adapts to what the reporter is submitting. SPLIT reporters fill in the ratio; dividend reporters fill in the amount; symbol-change reporters fill in old/new ticker. No wasted effort on fields that do not apply.

**Required source URL.** Every accepted action must have a verifiable source. The template enforces this with a required field and a clear instruction to prefer primary sources (SEC, exchange, company) over secondary ones.

**Correction vs. addition.** Most issue templates assume "new thing." This one explicitly handles both. Corrections are common in financial data and need a different review path.

**Downstream impact section.** Corporate actions affect backtested P&L, price adjustment, and share counts. The template flags these consequences so maintainers can assess risk.

**Suggested JSON entry.** Advanced reporters can supply the full JSON, which a maintainer validates against `schema.json`. This turns a report into a near-drop-in addition — the maintainer's job becomes verification, not authoring.

**Maintainer checklist.** The last section is only for maintainers. It documents the exact steps to accept an action. It is visible in the issue thread, so reporters can see what will happen.
