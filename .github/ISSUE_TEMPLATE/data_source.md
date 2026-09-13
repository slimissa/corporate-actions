---
name: Data source
about: Suggest a new data source, fetcher, or coverage expansion for the registry
title: '[Source] '
labels: ['data-source', 'enhancement']
assignees: []
---

<!--
Thanks for helping expand the Corporate Actions Registry's data coverage.

This template is for proposing a new source of corporate actions data,
a new instrument universe, or a new fetcher implementation. It is NOT for
reporting a specific missing action (use the Action update template for that).

Examples of good uses of this template:
  - "Add ESMA FIRDS as an EU instrument source"
  - "Implement a Japan Exchange Group (JPX) fetcher"
  - "Cover Korean corporate actions from KIND"
  - "Add IEX Cloud as a fallback source for US dividends"

Examples of bad uses:
  - "AAPL dividend for 2024-05-10 is missing"  → use Action update
  - "The registry should cover more instruments"  → too vague, specify the source
-->

## Summary

<!-- One-line description, e.g. "Add ESMA FIRDS fetcher for EU equities" -->

## Source details

| Field | Value |
|-------|-------|
| Source name | |
| Provider | (SEC, exchange operator, commercial vendor, regulator, other) |
| Geographic coverage | US / EU / UK / JP / HK / global / other |
| Instrument types | equities / ETFs / bonds / derivatives / mixed |
| Action types supported | splits / dividends / symbol changes / mergers / all |

## Access

### Endpoint or interface

<!--
How does the source expose data? Check all that apply.
-->

- [ ] Public REST API (no key required)
- [ ] Public REST API (free key required)
- [ ] Commercial REST API (paid key)
- [ ] CSV / bulk file download
- [ ] HTML scraping required
- [ ] JavaScript-rendered page (requires headless browser)
- [ ] PDF documents (requires parser)
- [ ] Email / newsletter subscription
- [ ] Manual data (from exchange announcements)

### Documentation URL

<!-- Link to the source's API docs, data page, or file listing -->

`https://...`

### Authentication

| Field | Value |
|-------|-------|
| Required? | yes / no |
| Type | API key / OAuth / session cookie / none |
| Free tier available? | yes / no |
| Free tier limits | (e.g. 250 requests/day, 500 rows per response) |
| Pricing (if paid) | (e.g. $30/month starter tier) |

## Legal and licensing

**Required.** Any source we integrate must be legally redistributable, or
the license must permit the intended use.

- [ ] The source is public domain (government regulator, exchange press release).
- [ ] The source is open data under a permissive license (CC-BY, ODbL, MIT, etc.).
- [ ] The source is commercial but the license permits redistribution.
- [ ] The source is commercial and the license prohibits redistribution.
- [ ] I am unsure about the license status.

**License details** (paste the relevant clause or link):

```
<link or paste excerpt>
```

**Redistribution risk**:

<!--
If we cannot redistribute the raw data, we may still be able to use it as
a verification source (compare against it, but publish only our own
derived entries). State which category applies.
-->

- [ ] Redistribution permitted → can be a primary source
- [ ] Redistribution prohibited → can be a verification source only
- [ ] Unclear → flag for maintainer review before any integration

## Coverage compared to what we have

<!--
The current registry covers US equities via Yahoo Finance (yfinance).
List which gaps this source would fill.
-->

| Gap | This source fills it? |
|-----|----------------------|
| International equities | yes / no / partial |
| Non-dividend action types (merger, spinoff, rights, tender) | yes / no / partial |
| Non-USD currencies | yes / no / partial |
| Historical coverage before 2000 | yes / no / partial |
| Real-time updates | yes / no / partial |
| Regulatory-grade provenance | yes / no / partial |

## Effort estimate

<!--
Your honest assessment. Do not oversell.
-->

| Task | Estimate |
|------|----------|
| Investigate API / interface | hours / days |
| Implement fetcher | hours / days |
| Handle rate limits | trivial / moderate / complex |
| Parse / normalize output | trivial / moderate / complex |
| Write tests | hours / days |
| **Total** | |

## Risk and reliability

| Factor | Assessment |
|--------|------------|
| Reliability | high / medium / low |
| Stability of interface | high / medium / low (does the source change often?) |
| Rate-limit risk | high / medium / low |
| Data quality risk | high / medium / low |
| Provenance clarity | high / medium / low |

<!--
Explain any risks. For example: "Nasdaq's API times out from non-US IPs,
which is why our current Nasdaq fetcher is broken." Or: "ESMA FIRDS files
are updated daily and are known to be stable."
-->

## Alternatives considered

<!--
List other sources you looked at and why you did not propose them.
This saves maintainers from re-investigating.
-->

| Alternative | Why rejected |
|-------------|--------------|
| | |

## Prototype (optional)

<!--
If you have already written a small script or proof of concept, link it
or paste the key snippet. A working prototype moves this proposal from
"interesting idea" to "ready to implement."
-->

```python
# Optional proof of concept
```

**Sample output** (if applicable):

```json
{
  "example": "one action extracted from this source"
}
```

## Suggested integration plan

<!--
How should this source fit into the existing pipeline?
-->

- [ ] New fetcher in `tools/fetch_<source>.py`
- [ ] Extend an existing fetcher (`fetch_yahoo_actions.py`, etc.)
- [ ] Manual curation with the source as verification only
- [ ] Separate pipeline (does not integrate with `run_update.sh`)

**Which workflow consumes it?**

- [ ] `update-actions.yml` (weekly fetch + merge + PR)
- [ ] `check-sources.yml` (source health monitoring)
- [ ] Manual / one-off ingestion

**Which existing action types does it help populate?**

- [ ] SPLIT
- [ ] REVERSE_SPLIT
- [ ] DIVIDEND
- [ ] SPECIAL_DIVIDEND
- [ ] SYMBOL_CHANGE
- [ ] SPINOFF
- [ ] DELISTING
- [ ] MERGER

## Checklist

Before submitting, please confirm:

- [ ] I have searched existing issues to make sure this source is not already proposed.
- [ ] I have provided a working URL to the source's documentation or data page.
- [ ] I have stated the license status honestly, including "unsure" if applicable.
- [ ] I have described what the source covers and what it does not.
- [ ] I have not asked for a vague "add more data" without naming the source.
- [ ] I understand that a source with unclear or restrictive licensing may be rejected even if technically accessible.
- [ ] I understand that "the source exists" is not sufficient — it must be:
  - legally usable
  - reliable enough to be a dependency
  - technically integrable into the current pipeline

## Additional context

<!-- Anything else. Screenshots, links to related discussion, notes from prior attempts. -->

---

**Maintainer notes** (do not edit):

- [ ] License status verified independently.
- [ ] Endpoint tested with a live request.
- [ ] Coverage claim checked against current registry gaps.
- [ ] Effort estimate sanity-checked.
- [ ] Decision:
  - [ ] Accepted → create implementation issue, assign, link to this one
  - [ ] Deferred → label `roadmap/v1.x`, document why
  - [ ] Rejected → state the reason clearly (licensing, reliability, redundancy)
- [ ] If accepted, add to `docs/data_sources.md`.