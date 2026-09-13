# Action Types

The Corporate Actions Registry supports eight action types. Each one
describes a distinct corporate event that changes something about an
instrument: its price, its share count, its ticker, its currency, or its
existence.

This document defines each type. It specifies:

- What the action is
- Which fields are required
- The date ordering rules enforced by `tools/validate.py`
- How the `impact` multipliers are derived by `tools/derive_impacts.py`
- A complete JSON example
- Edge cases and common pitfalls

The schema (`schema.json`) is the source of truth for field structure.
This document is the source of truth for semantics.

---

## Table of contents

1. [Overview](#overview)
2. [SPLIT](#split)
3. [REVERSE_SPLIT](#reverse_split)
4. [DIVIDEND](#dividend)
5. [SPECIAL_DIVIDEND](#special_dividend)
6. [SYMBOL_CHANGE](#symbol_change)
7. [SPINOFF](#spinoff)
8. [DELISTING](#delisting)
9. [MERGER](#merger)
10. [Cross-type comparison](#cross-type-comparison)
11. [Version history](#version-history)

---

## Overview

### Action object structure

Every action entry has the same shape regardless of type:

```json
{
  "isin": "US0378331005",
  "action_id": "US0378331005-DIVIDEND-2024-05-16-0.2500",
  "action_type": "DIVIDEND",
  "ratio": null,
  "amount": 0.25,
  "currency": "USD",
  "dates": {
    "announcement": "2024-05-02",
    "ex_date": "2024-05-16",
    "record_date": "2024-05-17",
    "effective_date": "2024-05-23"
  },
  "status": "COMPLETED",
  "provenance": {
    "source": "Apple Inc. press release",
    "source_url": "https://www.apple.com/newsroom/...",
    "verification_source": null,
    "verification_url": null
  },
  "impact": {
    "price_multiplier": 1.0,
    "share_multiplier": 1.0,
    "cash_adjustment": 0.25
  }
}
```

Fields that do not apply to a given type are omitted. The schema
enforces this with `oneOf` constraints per action type.

### Which fields are required by type

| Field | SPLIT | REV_SPLIT | DIVIDEND | SPECIAL_DIV | SYMBOL_CHG | SPINOFF | DELISTING | MERGER |
|-------|:-----:|:---------:|:--------:|:-----------:|:----------:|:-------:|:---------:|:------:|
| `ratio` | ✅ | ✅ | — | — | — | ✅ | — | — |
| `amount` | — | — | ✅ | ✅ | — | — | — | — |
| `currency` | — | — | ✅ | ✅ | — | — | — | — |
| `dates.announcement` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `dates.ex_date` | ✅ | ✅ | ✅ | ✅ | — | ✅ | — | — |
| `dates.record_date` | — | — | ✅ | ✅ | — | — | — | — |
| `dates.effective_date` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

The `impact` object is always present after `derive_impacts.py` runs, but it
is recomputed from the primary fields; it is not authoritative.

### Date semantics

| Date | Meaning |
|------|---------|
| `announcement` | The date the action became public (press release, filing, or exchange notice). |
| `ex_date` | The first trading day on which the security trades without the entitlement. For splits, the price adjusts at the open on this date. For dividends, purchases on this date do not receive the dividend. |
| `record_date` | The date on which shareholders must be on the register to receive the entitlement. |
| `effective_date` | The date the action takes legal or operational effect. For splits, this equals the ex-date in most markets. For dividends, this is usually the payment date. |

ISO 8601 `YYYY-MM-DD` format only. No time component.

---

## SPLIT

### Definition

A forward stock split increases the number of shares outstanding by
multiplying the count while dividing the price by the same factor. The
economic value of the position is unchanged. The purpose is usually to
lower the per-share price, improving liquidity or meeting index-inclusion
thresholds.

### Example

NVIDIA executed a 10-for-1 forward split effective 2024-06-10. An investor
holding 100 shares at $1,200 each before the split holds 1,000 shares at
$120 each after — same total value, different structure.

### Required fields

| Field | Format | Example |
|-------|--------|---------|
| `action_type` | literal `"SPLIT"` | |
| `ratio` | `"new:old"` | `"10:1"` |
| `dates.announcement` | ISO date | `"2024-05-22"` |
| `dates.ex_date` | ISO date | `"2024-06-10"` |
| `dates.effective_date` | ISO date | `"2024-06-10"` |

`dates.record_date` is optional but recommended.

### Temporal rules

Enforced by `validate_temporal`:

- `announcement` ≤ `ex_date`
- `ex_date` = `effective_date` (for most markets; deviation is reported as an error)
- `record_date` ≤ `ex_date` (if `record_date` is present)

### Ratio format

Always `"new:old"` — the number of new shares received for each old share.

| Event | Ratio string | Meaning |
|-------|--------------|---------|
| 10-for-1 forward | `"10:1"` | 1 share becomes 10 |
| 4-for-1 forward | `"4:1"` | 1 share becomes 4 |
| 7-for-1 forward | `"7:1"` | 1 share becomes 7 |
| 3-for-2 forward | `"3:2"` | 2 shares become 3 |

Ratio parts must be positive integers. Whitespace is not permitted.

### Impact derivation

For ratio `N:O`:

```
share_multiplier = N / O
price_multiplier = O / N
cash_adjustment  = 0.0
```

Example, `10:1`:
- `share_multiplier = 10.0` (ten times the shares)
- `price_multiplier = 0.1` (one tenth the price)
- `cash_adjustment  = 0.0`

### Backtest application

When restating historical prices for a split with ex-date `X`:

- For any price on a date `< X`: multiply by `price_multiplier`.
- For any price on a date `≥ X`: leave unchanged.
- For share counts: multiply everything before `X` by `share_multiplier`.

The price series is continuous across `X` after adjustment.

### Full example

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
    "source": "NVIDIA Corp press release",
    "source_url": "https://nvidianews.nvidia.com/news/nvidia-announces-ten-for-one-forward-stock-split"
  },
  "impact": {
    "price_multiplier": 0.1,
    "share_multiplier": 10.0,
    "cash_adjustment": 0.0
  }
}
```

### Edge cases

- **Fractional shares.** Some brokers do not split fractional lots cleanly and issue a cash-in-lieu payment. That cash is not modeled here; it is a broker-specific detail.
- **Ex-date vs. effective date.** In the US, ex-date equals effective date for splits. In some non-US markets, the ex-date precedes the effective date by one or two trading days. The validator flags this as an error; if a non-US split is added with a divergence, the validator rule for `SPLIT` would need adjustment.
- **Simultaneous dividend.** It is possible for a split and a dividend to share an ex-date. They are separate entries with distinct `action_id`s.

---

## REVERSE_SPLIT

### Definition

A reverse stock split decreases the number of shares outstanding by dividing
the count while multiplying the price by the same factor. Often used to
regain exchange listing compliance after a prolonged price decline.

### Example

GE executed a 1-for-8 reverse split effective 2021-08-02. 800 shares at $10
each become 100 shares at $80 each. Same total value.

### Required fields

Identical to `SPLIT`. The only difference is the ratio orientation.

### Ratio format

For a reverse split, the ratio is `"new:old"` with `new < old`.

| Event | Ratio string |
|-------|--------------|
| 1-for-8 reverse | `"1:8"` |
| 1-for-10 reverse | `"1:10"` |
| 2-for-3 reverse | `"2:3"` |

### Temporal rules

Same as `SPLIT`:
- `announcement` ≤ `ex_date`
- `ex_date` = `effective_date`
- `record_date` ≤ `ex_date` (if present)

### Impact derivation

Same formula, produces multiplicative values less than 1 for share count
and greater than 1 for price:

For ratio `1:8`:
- `share_multiplier = 0.125` (one eighth of the shares)
- `price_multiplier = 8.0` (eight times the price)

### Full example

```json
{
  "isin": "US3696041033",
  "action_id": "US3696041033-REVERSE_SPLIT-2021-08-02-1-8",
  "action_type": "REVERSE_SPLIT",
  "ratio": "1:8",
  "dates": {
    "announcement": "2021-07-30",
    "ex_date": "2021-08-02",
    "record_date": "2021-07-30",
    "effective_date": "2021-08-02"
  },
  "status": "COMPLETED",
  "provenance": {
    "source": "General Electric press release",
    "source_url": "https://www.ge.com/news/press-releases/ge-completes-one-for-eight-reverse-stock-split"
  },
  "impact": {
    "price_multiplier": 8.0,
    "share_multiplier": 0.125,
    "cash_adjustment": 0.0
  }
}
```

### Edge cases

- **Cash-in-lieu.** Reverse splits frequently produce fractional shares that brokers redeem for cash. Not modeled here.
- **Combined with delisting.** A reverse split is often a prelude to delisting. The two are separate entries.
- **Ratio representation.** A "1-for-8" is stored as `"1:8"`, not `"8:1"`. Do not invert.

---

## DIVIDEND

### Definition

A regular cash dividend is a distribution of earnings to shareholders. It
reduces the price of the stock by the amount distributed on the ex-date,
but shareholders receive cash.

### Example

Apple pays a quarterly dividend of $0.25 per share. An investor holding
1,000 shares receives $250 in cash on the payment date.

### Required fields

| Field | Format | Example |
|-------|--------|---------|
| `action_type` | literal `"DIVIDEND"` | |
| `amount` | number ≥ 0 | `0.25` |
| `currency` | ISO 4217 code | `"USD"` |
| `dates.announcement` | ISO date | `"2024-05-02"` |
| `dates.ex_date` | ISO date | `"2024-05-16"` |
| `dates.record_date` | ISO date | `"2024-05-17"` |
| `dates.effective_date` | ISO date | `"2024-05-23"` |

### Temporal rules

Enforced by `validate_temporal`:

- `announcement` ≤ `ex_date`
- `ex_date` < `record_date` (strictly less)
- `record_date` ≤ `effective_date`

The typical US order is: announcement < ex-date < record-date < payment-date.

### Amount and currency

- `amount` is per share, in the currency of the instrument.
- `currency` must be an active ISO 4217 code (validated against the ISO 4217 registry).
- The amount is the gross amount, before withholding tax.

### Impact derivation

```
share_multiplier = 1.0
price_multiplier = 1.0
cash_adjustment  = amount
```

Dividends do not adjust price multipliers — they adjust cash returns.

### Backtest application

Two ways to handle dividends in a backtest:

1. **Total return.** Add the cash amount to the position value on the
   ex-date. Reinvest at the close if modeling compounding.
2. **Price return.** Do not adjust prices at all; instead, treat the
   dividend as income. This is often paired with `price_multiplier = 1.0`.

The registry stores the raw amount and leaves the strategy decision to the
consumer. This is deliberate; total-return vs. price-return is a modeling
choice.

### Full example

```json
{
  "isin": "US0378331005",
  "action_id": "US0378331005-DIVIDEND-2024-05-16-0.2500",
  "action_type": "DIVIDEND",
  "amount": 0.25,
  "currency": "USD",
  "dates": {
    "announcement": "2024-05-02",
    "ex_date": "2024-05-16",
    "record_date": "2024-05-17",
    "effective_date": "2024-05-23"
  },
  "status": "COMPLETED",
  "provenance": {
    "source": "Apple Inc. press release",
    "source_url": "https://www.apple.com/newsroom/2024/05/apple-reports-second-quarter-results/"
  },
  "impact": {
    "price_multiplier": 1.0,
    "share_multiplier": 1.0,
    "cash_adjustment": 0.25
  }
}
```

### Edge cases

- **Dividends declared in foreign currency.** The `currency` field captures
  this. Cross-currency conversion is the consumer's responsibility.
- **Withholding tax.** Gross amount is stored. Net depends on the holder's
  jurisdiction.
- **Ex-date falling on a weekend.** Ex-dates are trading days by definition.
- **Multiple dividends on the same ex-date.** Rare but possible (regular plus
  special). They are separate entries.

---

## SPECIAL_DIVIDEND

### Definition

A one-time cash distribution that is not part of a recurring dividend
program. Usually arises from asset sales, excess cash, or legal settlements.

### Example

Microsoft paid a special dividend of $3.00 per share in late 2004, funded by
accumulated overseas cash.

### Required fields and rules

Identical to `DIVIDEND`. The only semantic difference is that a special
dividend is not expected to recur. From the registry's perspective, both
types have the same schema and the same temporal rules.

### Why a separate type

Consumers often want to distinguish:

- **Recurring dividends** for yield calculations, payout ratios, and
  dividend-growth strategies.
- **Special dividends** as one-off events that should not be annualized.

If both were labeled `DIVIDEND`, a naive `trailing_12m_dividends` calculation
would overstate the yield following a special distribution.

### Full example

```json
{
  "isin": "US5949181045",
  "action_id": "US5949181045-SPECIAL_DIVIDEND-2004-11-17-3.0000",
  "action_type": "SPECIAL_DIVIDEND",
  "amount": 3.0,
  "currency": "USD",
  "dates": {
    "announcement": "2004-11-15",
    "ex_date": "2004-11-17",
    "record_date": "2004-11-19",
    "effective_date": "2004-12-03"
  },
  "status": "COMPLETED",
  "provenance": {
    "source": "Microsoft press release",
    "source_url": "https://news.microsoft.com/2004/11/15/microsoft-declares-special-dividend/"
  },
  "impact": {
    "price_multiplier": 1.0,
    "share_multiplier": 1.0,
    "cash_adjustment": 3.0
  }
}
```

### Edge cases

- **Special vs. regular on the same day.** Both entries coexist. Consumers
  should sum them for total cash received.
- **Special dividend as part of a merger.** Some mergers include a special
  dividend paid before closing. Record it as a separate `SPECIAL_DIVIDEND`.

---

## SYMBOL_CHANGE

### Definition

The instrument's ticker symbol changes. The ISIN does not. The underlying
security is the same; only the exchange-listed label changes.

### Example

Facebook Inc. renamed itself Meta Platforms Inc. and changed its ticker from
`FB` to `META` effective 2022-06-09. The ISIN `US30303M1027` is unchanged.

### Required fields

| Field | Format | Example |
|-------|--------|---------|
| `action_type` | literal `"SYMBOL_CHANGE"` | |
| `dates.announcement` | ISO date | `"2022-06-09"` |
| `dates.effective_date` | ISO date | `"2022-06-09"` |

No `ratio`, no `amount`, no `currency`, no `ex_date`, no `record_date`.

### Temporal rules

Enforced by `validate_temporal`:

- `announcement` ≤ `effective_date`

That is the only rule. `ex_date` and `record_date` are ignored even if
present, and their presence is not an error.

### Impact derivation

```
share_multiplier = 1.0
price_multiplier = 1.0
cash_adjustment  = 0.0
```

A symbol change does not affect price, share count, or cash flow.

### Consumer guidance

Symbol changes break naive joins by ticker. If a consumer keys its data by
ticker, a position held through a symbol change will appear to disappear and
a new position will appear to open. The correct handling:

- Key positions by ISIN.
- When a `SYMBOL_CHANGE` is encountered, update the display ticker but keep
  the ISIN as the primary key.

### Full example

```json
{
  "isin": "US30303M1027",
  "action_id": "US30303M1027-SYMBOL_CHANGE-2022-06-09",
  "action_type": "SYMBOL_CHANGE",
  "dates": {
    "announcement": "2022-06-09",
    "effective_date": "2022-06-09"
  },
  "status": "COMPLETED",
  "provenance": {
    "source": "Meta Platforms press release",
    "source_url": "https://about.fb.com/news/2022/06/facebook-is-now-meta/"
  },
  "impact": {
    "price_multiplier": 1.0,
    "share_multiplier": 1.0,
    "cash_adjustment": 0.0
  }
}
```

### Edge cases

- **Ticker reuse.** After `FB` became `META`, the ticker `FB` was later
  reassigned to a different company. The registry preserves the ISIN as the
  key, so consumers keyed on ISIN are unaffected.
- **Change of exchange without change of ticker.** Not a `SYMBOL_CHANGE`.
  That is a listing change and is not modeled in v1.0.0.
- **Change of both ticker and exchange.** Not modeled in v1.0.0.

---

## SPINOFF

### Definition

A company separates part of its business into a new, independent entity.
Shareholders of the parent receive shares of the new entity, usually in
proportion to their holdings.

### Example

GE separated its healthcare division into GE HealthCare. Shareholders of GE
received shares of GEHC.

### Required fields

| Field | Format | Example |
|-------|--------|---------|
| `action_type` | literal `"SPINOFF"` | |
| `ratio` | `"new:old"` | `"1:3"` (1 GEHC per 3 GE) |
| `dates.announcement` | ISO date | `"2023-01-04"` |
| `dates.ex_date` | ISO date | `"2023-01-04"` |
| `dates.effective_date` | ISO date | `"2023-01-04"` |

The spun-off ISIN is not stored in v1.0.0. If the new entity is added to the
registry, its ISIN will reference it implicitly through the `action_id` naming.

### Temporal rules

Enforced by `validate_temporal`:

- `announcement` ≤ `ex_date`
- `ex_date` = `effective_date`

`record_date` is ignored.

### Impact derivation

No automatic multipliers are computed for spinoffs. The allocation of value
between parent and child depends on market pricing on the ex-date, which is
not available in the registry.

```
share_multiplier = 1.0 (conservative default)
price_multiplier = 1.0 (conservative default)
cash_adjustment  = 0.0
```

Consumers who model spinoffs adjust prices manually based on the observed
close of parent and child on the ex-date.

### Full example

```json
{
  "isin": "US3696041033",
  "action_id": "US3696041033-SPINOFF-2023-01-04-1-3",
  "action_type": "SPINOFF",
  "ratio": "1:3",
  "dates": {
    "announcement": "2023-01-04",
    "ex_date": "2023-01-04",
    "effective_date": "2023-01-04"
  },
  "status": "COMPLETED",
  "provenance": {
    "source": "GE press release",
    "source_url": "https://www.ge.com/news/press-releases/ge-completes-separation-ge-healthcare"
  },
  "impact": {
    "price_multiplier": 1.0,
    "share_multiplier": 1.0,
    "cash_adjustment": 0.0
  }
}
```

### Edge cases

- **Fractional entitlements.** Some distributions result in fractional shares.
  Brokers handle these with cash-in-lieu; not modeled.
- **Tax basis allocation.** The parent/child cost basis split is a tax
  accounting detail, not a registry concern.
- **Multi-way splits.** A company may separate into more than two entities.
  Each gets its own `SPINOFF` entry.
- **Immediate merger of the spinoff.** If the new entity is immediately
  acquired, both a `SPINOFF` and a `MERGER` might be recorded. In v1.0.0 only
  the `SPINOFF` is modeled.

---

## DELISTING

### Definition

The instrument is removed from the exchange. Trading ceases. The position
cannot be closed on that venue.

### Example

Twitter was delisted from the NYSE following its acquisition by Elon Musk in
October 2022.

### Required fields

| Field | Format | Example |
|-------|--------|---------|
| `action_type` | literal `"DELISTING"` | |
| `dates.announcement` | ISO date | `"2022-10-27"` |
| `dates.effective_date` | ISO date | `"2022-10-28"` |

No `ex_date`, no `record_date`, no `ratio`, no `amount`.

### Temporal rules

Enforced by `validate_temporal`:

- `announcement` ≤ `effective_date`
- `ex_date` must not be present (error if it is)
- `record_date` must not be present (error if it is)

### Impact derivation

```
share_multiplier = 1.0
price_multiplier = 1.0
cash_adjustment  = 0.0
```

No automatic adjustment. The final settlement value is the acquisition price
or a bankruptcy recovery amount, which is not in the registry.

### Full example

```json
{
  "isin": "US90184L1026",
  "action_id": "US90184L1026-DELISTING-2022-10-28",
  "action_type": "DELISTING",
  "dates": {
    "announcement": "2022-10-27",
    "effective_date": "2022-10-28"
  },
  "status": "COMPLETED",
  "provenance": {
    "source": "Twitter press release",
    "source_url": "https://www.prnewswire.com/news-releases/twitter-announces-completion-of-acquisition-by-elon-musk-301658187.html"
  },
  "impact": {
    "price_multiplier": 1.0,
    "share_multiplier": 1.0,
    "cash_adjustment": 0.0
  }
}
```

### Consumer guidance

When a `DELISTING` is encountered:

- Stop generating orders for the instrument on the delisting exchange.
- If a position is held, treat it as liquidated at the last known price, or
  at the acquisition price if available.
- The ISIN is retained in the registry for audit; the ticker may be reused
  later by a different issuer.

### Edge cases

- **Delisting by acquisition.** Recorded as `DELISTING` in v1.0.0. The
  acquisition itself would be a `MERGER` entry in a future version.
- **Delisting by bankruptcy.** The recovery value is often zero; the registry
  does not store a recovery value.
- **Voluntary delisting.** Same schema; the reason field would be added in a
  future version.
- **Cross-listing removal.** If an instrument delists from a secondary
  exchange but remains on a primary, that is not recorded in v1.0.0.

---

## MERGER

### Definition

One company acquires another. Shareholders of the target may receive cash,
shares of the acquirer, or both, depending on the deal terms.

### Status in v1.0.0

**Not populated.** The schema reserves `MERGER` as a valid action type so
that future entries validate without a schema change, but no `MERGER` entries
exist in the current `actions.json`.

**The validator rejects `MERGER` actions in v1.0.0.** Any `MERGER` entry
will fail with `"MERGER is not allowed in v1.0.0"` from `validate.py`. This
is deliberate: the extraction pipeline does not yet handle acquisition
filings (SEC S-4 and merger-related 8-K filings), so any entry would be
hand-curated and unverifiable at scale.

### Planned schema

When implemented in v1.1.0, a `MERGER` entry will have:

- `ratio` — the exchange ratio `"acquirer:target"` for stock deals
- `amount` — the cash component per share for cash-and-stock deals
- `currency` — the currency of the cash component
- `dates.ex_date` and `dates.effective_date`

### Why it is not in v1.0.0

Three reasons:

1. **Filing complexity.** Mergers are announced via SEC S-4 proxy statements
   and merger-related 8-K filings, not the dividend and split 8-Ks the
   current fetcher parses. Extending the fetcher is a v1.1.0 task.
2. **Deal uncertainty.** Mergers can be delayed, renegotiated, or abandoned.
   Modeling them correctly requires tracking multiple statuses
   (announced, shareholder-approved, regulatory-approved, closed, terminated),
   which the current schema does not support.
3. **Ambiguity at close.** A merger closes on the same day the target
   delists. Recording both a `MERGER` and a `DELISTING` for the same event
   could confuse consumers. The correct representation needs design work.

### Placeholder entry (invalid in v1.0.0)

```json
{
  "isin": "US...",
  "action_id": "...-MERGER-...",
  "action_type": "MERGER",
  "ratio": "1.28:1",
  "dates": {
    "announcement": "...",
    "effective_date": "..."
  },
  "status": "COMPLETED",
  "provenance": {
    "source": "SEC S-4",
    "source_url": "https://www.sec.gov/Archives/..."
  },
  "impact": {
    "price_multiplier": 1.0,
    "share_multiplier": 1.0,
    "cash_adjustment": 0.0
  }
}
```

This will fail validation. Do not submit entries of this shape until v1.1.0.

---

## Cross-type comparison

### Which dates are required

| Type | announcement | ex_date | record_date | effective_date |
|------|:------------:|:-------:|:-----------:|:--------------:|
| SPLIT | required | required | optional | required |
| REVERSE_SPLIT | required | required | optional | required |
| DIVIDEND | required | required | required | required |
| SPECIAL_DIVIDEND | required | required | required | required |
| SYMBOL_CHANGE | required | ignored | ignored | required |
| SPINOFF | required | required | ignored | required |
| DELISTING | required | **forbidden** | **forbidden** | required |
| MERGER | required | — | — | required |

### Which fields are required

| Type | ratio | amount | currency |
|------|:-----:|:------:|:--------:|
| SPLIT | ✅ | — | — |
| REVERSE_SPLIT | ✅ | — | — |
| DIVIDEND | — | ✅ | ✅ |
| SPECIAL_DIVIDEND | — | ✅ | ✅ |
| SYMBOL_CHANGE | — | — | — |
| SPINOFF | ✅ | — | — |
| DELISTING | — | — | — |
| MERGER | conditional | conditional | conditional |

### Impact computation

| Type | price_multiplier | share_multiplier | cash_adjustment |
|------|:----------------:|:----------------:|:---------------:|
| SPLIT | `old / new` | `new / old` | `0.0` |
| REVERSE_SPLIT | `old / new` | `new / old` | `0.0` |
| DIVIDEND | `1.0` | `1.0` | `amount` |
| SPECIAL_DIVIDEND | `1.0` | `1.0` | `amount` |
| SYMBOL_CHANGE | `1.0` | `1.0` | `0.0` |
| SPINOFF | `1.0` | `1.0` | `0.0` |
| DELISTING | `1.0` | `1.0` | `0.0` |
| MERGER | manual | manual | manual |

For SPLIT and REVERSE_SPLIT, `new` and `old` refer to the parts of the
ratio: `"10:1"` has `new = 10` and `old = 1`.

### Date ordering summary

```
SPLIT:              announcement ≤ ex_date = effective_date, record_date ≤ ex_date
REVERSE_SPLIT:      announcement ≤ ex_date = effective_date, record_date ≤ ex_date
DIVIDEND:           announcement ≤ ex_date < record_date ≤ effective_date
SPECIAL_DIVIDEND:   announcement ≤ ex_date < record_date ≤ effective_date
SYMBOL_CHANGE:      announcement ≤ effective_date
SPINOFF:            announcement ≤ ex_date = effective_date
DELISTING:          announcement ≤ effective_date, no ex_date, no record_date
MERGER:             announcement ≤ effective_date (placeholder)
```

---

## Version history

### v1.0.0

- Seven active types: `SPLIT`, `REVERSE_SPLIT`, `DIVIDEND`, `SPECIAL_DIVIDEND`,
  `SYMBOL_CHANGE`, `SPINOFF`, `DELISTING`.
- `MERGER` reserved in schema but rejected by the validator.
- All temporal rules as documented above.
- All impact derivations as documented above.

### v1.1.0 (planned)

- `MERGER` extraction from SEC S-4 filings.
- Multi-status tracking for announced / approved / closed / terminated deals.
- Cash-and-stock deal representation.
- Spinoff child ISIN linked explicitly.

---

## See also

- `schema.json` — the JSON Schema that enforces the field structure.
- `tools/validate.py` — the implementation of the temporal and arithmetic rules.
- `tools/derive_impacts.py` — the implementation of the impact derivation.
- `docs/validation_layers.md` — the seven validation layers.
- `docs/data_sources.md` — where the data comes from.
- `CONTRIBUTING.md` — how to propose a new action.