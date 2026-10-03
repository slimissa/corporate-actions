# Redistribution Position

**Under what legal theory the Corporate Actions Registry redistributes
the data it holds, and how to respond to a takedown request.**

This document is the reference for anyone who asks whether they may use
`actions.json`. It is also the first file to read if a rights holder
sends a takedown notice.

---

## Table of contents

1. [Summary](#summary)
2. [The legal theory](#the-legal-theory)
3. [The four categories](#the-four-categories)
4. [Per-source mapping](#per-source-mapping)
5. [What users may do](#what-users-may-do)
6. [What the registry does not do](#what-the-registry-does-not-do)
7. [Takedown procedure](#takedown-procedure)
8. [Jurisdictional limits](#jurisdictional-limits)
9. [Known limitations](#known-limitations)
10. [History](#history)
11. [See also](#see-also)

---

## Summary

The registry distributes **facts**, not the sources they came from.

1. Every action states a fact: a split at a date, a dividend at an
   amount, a symbol change on a day. Facts are not copyrightable in the
   United States (*Feist Publications v. Rural Telephone Service*,
   499 U.S. 340 (1991)).
2. Every action cites the source of the fact in `provenance.source_url`.
   The source document itself is not copied into the registry.
3. Every action declares a `redistribution` category. That category is
   either `public-domain`, `facts-only`, or `secondary-source`.
   `restricted` is a fail-safe and never ships.

The registry's **compilation** — its schema, ordering, enrichment,
validation rules, tooling, and documentation — is a copyrighted work of
the maintainers, licensed under Apache 2.0.

Facts are facts. The compilation is ours. The source documents stay
with their authors.

---

## The legal theory

### What copyright protects

Copyright protects *expression*, not *facts*. Two things follow:

- A specific statement ("NVIDIA executed a 10-for-1 split on
  2024-06-10") is a fact. Anyone may state it.
- A specific document (a press release containing that statement) is
  an expression. Its author owns the copyright.

### What compilations are

A *compilation* is a selection and arrangement of facts. The US
Supreme Court held in *Feist* that a compilation is only protected to
the extent that its selection or arrangement is itself original. The
"sweat of the brow" theory — that effort alone earns copyright — was
explicitly rejected.

### The two claims this registry makes

**Claim 1: The facts are facts.** The registry records events that
happened in public markets. Any entry can be independently verified
against its cited source. No one owns a split, a dividend, or a symbol
change.

**Claim 2: The compilation is ours.** The choice of fields, the
ordering, the derived `impact` block, the validator, the four wrappers,
and this document are original work. They are licensed Apache 2.0.

These two claims together are the license position. The rest of this
document applies them to each source.

---

## The four categories

Every action carries one of four `redistribution` values.

### `public-domain`

The source is a work of the United States federal government. Under
17 U.S.C. § 105, US government works are not subject to copyright.

**Freely redistributable. No attribution required.**

**Sources in this category:** SEC EDGAR filings.

### `facts-only`

The source is a document — a press release, an exchange announcement —
whose text is copyrighted by its author, but whose factual content is
not. The registry extracts the facts and cites the source URL. It does
not copy the document.

**Redistributable to the extent of the facts extracted. Attribution
provided via `provenance.source_url`.**

**Sources in this category:** company press releases, exchange
announcements.

### `secondary-source`

The source is a commercial aggregator that provides data under its own
terms of service. The registry's position: the values it extracts
(split ratios, dividend amounts, ex-dates) are facts, and the
compilation from which they were extracted is not redistributed.

**Contestable.** See [Known limitations](#known-limitations).

**Sources in this category:** Yahoo Finance (via `yfinance`).

### `restricted`

**This category never ships.** It exists as a fail-safe so that a
source added without a classification decision fails validation rather
than silently entering the registry.

When an action has `redistribution: "restricted"`, the fix is to add a
rule to [`tools/derive_redistribution.py`](../tools/derive_redistribution.py)
and a row to [Per-source mapping](#per-source-mapping). It is not a
shipping state.

---

## Per-source mapping

The mapping from `provenance.source` to `redistribution` is defined in
`redistribution_for()` in
[`tools/derive_redistribution.py`](../tools/derive_redistribution.py).
This table is its documentation.

| Source prefix | Category | Basis |
|---------------|----------|-------|
| `SEC EDGAR` | `public-domain` | 17 U.S.C. § 105 |
| `Yahoo Finance (yfinance)` | `secondary-source` | Facts extracted; compilation not copied |
| `* press release` *(case-insensitive)* | `facts-only` | Feist: facts not copyrightable |
| `* exchange announcement` *(case-insensitive)* | `facts-only` | Same |
| *(anything else)* | `restricted` | Fail-safe; must be added to the mapping |

To add a source:

1. Decide the category using the definitions above.
2. Add a rule to `redistribution_for()`.
3. Add a row to the table above.
4. Run `python3 tools/derive_redistribution.py` to backfill.
5. Run `python3 -m pytest tests/test_redistribution_doc.py -v` to
   verify the doc mentions the new source.

All three changes land in the same pull request.

---

## What users may do

Users of `actions.json`, the four language wrappers, and the derived
exports (SQL, CSV, Parquet) may:

- **Read, query, and redistribute** the registry under Apache 2.0.
- **Use the registry commercially** without attribution.
- **Modify the registry** and redistribute their modifications.
- **Re-derive** the `impact` values, the `redistribution` values, or any
  other field.

The Apache 2.0 license covers the compilation. The facts themselves
carry no license because facts are not protected.

---

## What the registry does not do

- It does not redistribute any source document's text.
- It does not redistribute Yahoo's price data. Only the split and
  dividend facts extracted from Yahoo's public endpoints.
- It does not redistribute Bloomberg, Refinitiv, CUSIP Global Services,
  or LSE Masterfile data. Sources under those licenses are excluded by
  policy and by the `restricted` fail-safe.
- It does not claim ownership of the facts it records.
- It does not warrant accuracy. Every entry cites its source; the source
  is authoritative.

---

## Takedown procedure

If a rights holder sends a takedown notice, follow these steps in order.
Each step names the file or command that produces the response.

**1. Locate the entry.** Ask the sender for an ISIN and a date, or an
`action_id`. If they cannot name an entry, reply asking for specifics.

**2. Read its `redistribution` value.**

```bash
python3 -c "
import json
actions = json.load(open('actions.json'))['actions']
for a in actions:
    if a['isin'] == 'REPLACE_ISIN':
        print(a['action_id'], a['redistribution'])
"
```

**3. Branch by category.**

- **`public-domain`** — reply citing 17 U.S.C. § 105 and the source URL
  in `provenance.source_url`. No further action.

- **`facts-only`** — reply citing *Feist* and the source URL. The entry
  is a fact extracted from a public document. No further action.

- **`secondary-source`** — evaluate the claim on its merits.
  - If the claim is specific and plausible: proceed to Step 4.
  - If the claim is vague: reply requesting a specific right and a
    specific jurisdiction.

- **`restricted`** — this is a bug in the mapping. Remove the entry,
    open an issue tagged `licensing`, and audit what else shares its
    source prefix.

**4. Remove the entry (if the claim is accepted).**

Add the entry to `_removed_actions.json` before removing it from
`actions.json`:

```json
{
  "isin": "US...",
  "action_type": "DIVIDEND",
  "ex_date": "YYYY-MM-DD",
  "amount": 0.0000,
  "original_action_id": "...",
  "reason": "takedown: <reference to notice>"
}
```

Then remove the entry from `actions.json` and run:

```bash
python3 tools/validate.py --actions actions.json --schema schema.json \
  --identifiers tests/fixtures/identifiers.json \
  --iso4217 tests/fixtures/iso4217.json \
  --exchange-calendar tests/fixtures/exchange_calendar.json \
  --min-actions 100
python3 tools/derive_redistribution.py --check
python3 -m pytest tests/ -q -m "not network" 2>&1 | tail -1
```

**5. Document the takedown.** Add an entry to
`docs/decisions/takedowns.md` (create it if it does not exist) naming:

- The date
- The rights holder
- The entry or entries removed
- The category the removed entries had
- Whether the response was substantive or procedural

**6. Reply to the sender.** State which entries were removed, when, and
under what category. If entries were not removed, state the reason
citing the relevant paragraph of this document.

No response should require a legal opinion beyond reading this file.

---

## Jurisdictional limits

The legal theory in this document is grounded in **United States**
copyright law. Two limits are worth stating explicitly.

### The European Union database right

The EU Database Directive (96/9/EC) grants a *sui generis* right to the
maker of a database that required substantial investment in obtaining,
verifying, or presenting its contents. This right exists independently
of copyright and does not require originality.

A user redistributing this registry within the EU may be subject to
that right with respect to the compilation, even though US law would
not apply it. The Apache 2.0 license does not, and cannot, waive a
third party's database right.

### Other jurisdictions

Other jurisdictions have their own doctrines on the protection of
factual compilations. Users evaluating this registry under a specific
jurisdiction should consult counsel. The registry states its position;
it does not warrant that position for any particular use.

---

## Known limitations

These are documented, deliberate limitations. They are the honest
answer to "what could go wrong?"

- **The Yahoo position is the contestable one.** Yahoo's terms of
  service prohibit redistribution of their data. The registry's
  position is that its entries contain facts cited back to the Yahoo
  URL, and no substantial portion of Yahoo's compilation is copied.
  Yahoo has not challenged this. If Yahoo does, the takedown procedure
  applies.
- **The registry cannot verify a source's terms at time of extraction.**
  A source's terms of service may change after an entry is recorded.
  The `provenance.source_url` captures the URL, not the license state.
- **Attribution is cited but not waived.** The registry does not
  claim any waiver of the rights its sources may hold. It states its
  position on those rights.
- **The `redistribution` field describes the entry's source, not the
  entry's use.** A downstream user redistributing the registry is
  responsible for their own compliance.

---

## History

| Date | Change |
|------|--------|
| 2026-10-03 | Document created. Four categories defined. `restricted` fails validation. Per-source table added. Takedown procedure defined. |

---

## See also

- [`docs/data_sources.md`](./data_sources.md) — where each source comes
  from, its licensing status, and its reliability
- [`tools/derive_redistribution.py`](../tools/derive_redistribution.py)
  — the mapping from `provenance.source` to `redistribution`
- [`_removed_actions.json`](../_removed_actions.json) — the durable
  reject list used by the takedown procedure
- [`LICENSE`](../LICENSE) — Apache 2.0
- [*Feist Publications v. Rural Telephone Service*, 499 U.S. 340
  (1991)](https://supreme.justia.com/cases/federal/us/499/340/) — the
  precedent for facts not being copyrightable