# Contributing to Documentation

This guide covers how to contribute to the documentation in `docs/`. For
general contribution guidelines (code style, commit messages, PR workflow),
see the root [`CONTRIBUTING.md`](../CONTRIBUTING.md).

Documentation contributions follow the same review process as code: a
pull request, review, and merge. The difference is what gets reviewed.
Doc reviews check for accuracy, structure, and completeness — not
performance or correctness in the algorithmic sense.

---

## Table of contents

1. [What lives where](#what-lives-where)
2. [Documentation philosophy](#documentation-philosophy)
3. [Voice and tone](#voice-and-tone)
4. [File structure](#file-structure)
5. [Formatting conventions](#formatting-conventions)
6. [Code and data examples](#code-and-data-examples)
7. [Tables](#tables)
8. [Cross-references and links](#cross-references-and-links)
9. [When to update documentation](#when-to-update-documentation)
10. [Workflow for a docs PR](#workflow-for-a-docs-pr)
11. [Review checklist](#review-checklist)
12. [Common pitfalls](#common-pitfalls)
13. [Testing your changes](#testing-your-changes)
14. [What this guide does not cover](#what-this-guide-does-not-cover)

---

## 1. What lives where

The repository has two documentation surfaces:

### Root-level files

| File | Audience | Purpose |
|------|----------|---------|
| `README.md` | New visitors | Overview, quick start, links to deeper docs |
| `CHANGELOG.md` | Everyone | Version history |
| `CONTRIBUTING.md` | Contributors | Code contribution process, commit style, review process |
| `LICENSE` | Everyone | Apache 2.0 |

### `docs/` directory

| File | Audience | Purpose |
|------|----------|---------|
| `action_types.md` | Consumers, contributors | Semantics of each of the eight action types |
| `validation_layers.md` | Contributors, maintainers | The seven validation layers and what each catches |
| `data_sources.md` | Contributors, maintainers | Current, broken, planned, and rejected sources |
| `roadmap.md` | Everyone | Planned versions through v3.0.0 |
| `contributing.md` | Doc contributors | This file |

### Wrapper READMEs

Each wrapper has its own README in `wrappers/<language>/README.md`. They
are idiomatic to the language and follow the wrapper's own conventions,
which are similar to but not identical to this document's. Do not
refactor wrapper READMEs to match `docs/` style unless asked.

### When in doubt

If the content is about **how to use** the registry, it goes in a wrapper
README or the root README. If it is about **how the registry works**, it
goes in `docs/`. If it is about **how to change the registry**, it goes in
`CONTRIBUTING.md` or `docs/contributing.md`.

---

## 2. Documentation philosophy

Three principles guide every doc in this repository.

### 2.1 Falsifiability over clarity

A doc that says "the validator checks dates" is unclear. A doc that says
"`validate_temporal` enforces `announcement ≤ ex_date` for SPLIT" is
falsifiable — a reader can check whether that is true.

Whenever a claim can be made concrete, make it concrete. Prefer "242
actions" over "many actions." Prefer "2024-06-10" over "June 2024." Prefer
"exit code 1" over "fails."

### 2.2 Show the failure

Most docs show what works. This repository's docs show what fails too.
When documenting a rule, show the case that violates it. When documenting
a source, show where it breaks. When documenting a function, show the
error it produces.

A reader who has seen the failure mode can recognize it in the wild.

### 2.3 Cite the implementation

Every rule stated in `docs/` should trace back to a specific function,
schema field, or workflow. If a doc says "the validator rejects X," the
doc should also say which layer rejects it and where that layer lives in
the code.

This prevents doc drift. When the code changes, the doc's citation points
at the change.

---

## 3. Voice and tone

### Person

- Use **second person** ("you") for instructions. "Run `pytest tests/`."
- Use **third person** for descriptions. "The validator loads three
  registries."
- Avoid **first person** ("I", "we") except when explaining a deliberate
  decision. "We chose to warn rather than error on missing ISINs because..."

### Tense

- **Present tense** for what exists. "The registry contains 242 actions."
- **Future tense** only for roadmap items. "v1.1.0 will add MERGER."
- **Past tense** for history. "The endpoint was retired in 2024."

Avoid conditional tense ("would", "could") unless describing a
hypothetical. "If the source fails, the workflow exits 1" is better than
"If the source would fail, the workflow could exit 1."

### Active vs passive

Prefer active voice.

- **Prefer**: "The validator loads the ISO 4217 registry."
- **Avoid**: "The ISO 4217 registry is loaded by the validator."

Passive is acceptable when the actor is genuinely unknown or irrelevant.
"Dates are compared lexicographically" is fine because no specific actor
is responsible.

### Precision

Use precise terms. The registry has specific meanings for words that are
common in English:

| Word | Meaning in this repo |
|------|---------------------|
| Action | A single corporate event entry in `actions.json` |
| Event | Synonym for action, used only in prose |
| Entry | Synonym for action, used in operational docs |
| Layer | One of the seven validation passes |
| Registry | This project or a sibling (`Asset Identifiers`, `ISO 4217`, `Exchange Calendar`) |
| Fetcher | A script in `tools/` that extracts actions from a source |

Do not use "action" to mean "function," and do not use "event" to mean
"the GitHub event trigger."

### Terminology stability

Once a term is defined in one doc, other docs use the same term. "Ex-date"
is the term; do not write "ex date" or "exdate" in prose. "ISIN" is
uppercase; do not write "isin" in prose (though `isin` in code is fine).

A short glossary of terms used across the docs:

| Term | Format |
|------|--------|
| ISIN | Uppercase, no periods |
| CUSIP | Uppercase, no periods |
| MIC | Uppercase |
| ex-date | Hyphenated, lowercase except when starting a sentence |
| record date | Two words |
| effective date | Two words |
| `actions.json` | Backticked, lowercase |
| `schema.json` | Backticked, lowercase |
| `$LAS_DATA_HOME` | Backticked, uppercase |

---

## 4. File structure

Every file in `docs/` follows the same structure.

### 4.1 Required elements

1. **Title** — `# <Title>` on line one.
2. **Purpose paragraph** — one or two sentences describing what the doc
   covers and why. Immediately after the title, before the table of
   contents.
3. **Table of contents** — numbered list of sections, using relative
   anchor links.
4. **Numbered sections** — each section starts with `## N. Title` where
   `N` is the section number.
5. **See also** — the last section is `## See also`, listing related
   files with relative links.

### 4.2 Optional elements

- **Version history** — for docs that evolve with the registry.
  Placed just before `## See also`.
- **Subsections** — use `###` for subsections, `####` for sub-subsections.
  Do not go deeper than `####`.
- **Callouts** — use blockquotes for warnings or notes. Do not use emoji.

### 4.3 Section numbering

Numbers are stable across edits. If you remove a section, do not
renumber the ones after it — leave the gap. If you add a section between
two existing ones, use a decimal (`## 4.1 New Section`). This makes
links stable.

### 4.4 Anchor links

The table of contents uses GitHub-flavored markdown anchors. They are
generated from the heading text:

- Lowercase
- Spaces become hyphens
- Punctuation is stripped
- Backticks are stripped

Example:

| Heading | Anchor |
|---------|--------|
| `## 1. What lives where` | `#1-what-lives-where` |
| `## 6. Code and data examples` | `#6-code-and-data-examples` |
| `## See also` | `#see-also` |

If you edit a heading, update the corresponding anchor in the table of
contents.

---

## 5. Formatting conventions

### 5.1 Headings

- One `#` at the top of the file (the title).
- `##` for sections.
- `###` for subsections.
- `####` for sub-subsections, used sparingly.
- No blank line between `##` and the paragraph after it — GitHub renders
  them the same, but consistency matters.

### 5.2 Paragraphs

- One blank line between paragraphs.
- No hard-wrapped lines. Each paragraph is a single long line in the
  source; the renderer wraps it. This makes diffs cleaner.
- One idea per paragraph. If a paragraph has three ideas, split it.

### 5.3 Lists

- Use `-` for unordered lists.
- Use `1.` for ordered lists, and let the renderer handle numbering.
- Use `- [ ]` for checklists.
- Blank line before and after a list.

### 5.4 Inline code

- Backticks for: file paths, function names, field names, command-line
  flags, literal values, environment variables.
- Example: `` `tools/validate.py` ``, `` `--strict-isin` ``, `` `$LAS_DATA_HOME` ``.

Do not backtick prose terms. "The registry" is fine; `` `the registry` ``
is not.

### 5.5 Emphasis

- **Bold** for emphasis on a key term or a warning. Use sparingly.
- *Italic* for first-use introduction of a term. "The validator loads
  three *supporting registries*."
- Do not use both bold and italic for the same phrase.
- Do not use emphasis for entire sentences.

### 5.6 Line length

No enforced limit. Long lines are fine because the renderer wraps them.
Hard-wrapping a paragraph at 80 columns makes diffs noisy — one word
change produces a multi-line diff.

### 5.7 Whitespace

- One blank line between block-level elements.
- No trailing whitespace.
- No multiple consecutive blank lines.
- File ends with a single newline.

---

## 6. Code and data examples

### 6.1 Code blocks

Always tag the language:

````markdown
```bash
python3 tools/validate.py --actions actions.json
```
````

Supported tags: `bash`, `python`, `javascript`, `go`, `rust`, `json`,
`yaml`, `toml`, `text`.

For plain output that is not a specific language, use `text`.

### 6.2 Bash examples

- Prefer single-line commands when possible.
- Use `\` for line continuation only when the line is too long.
- Omit the `$` prompt character. The reader knows the line is a command.
- Show expected output in a separate block if it is short. If it is long,
  describe it in prose.

Good:

````markdown
```bash
python3 tools/validate.py --actions actions.json --schema schema.json
```
````

Bad:

````markdown
```bash
$ python3 tools/validate.py --actions actions.json --schema schema.json
```
````

### 6.3 JSON examples

- Two-space indentation.
- Field order matches the schema.
- Omit optional fields that are null.
- Include enough context to be self-contained. Do not show a fragment
  without the enclosing braces.

Good:

```json
{
  "isin": "US0378331005",
  "action_id": "US0378331005-DIVIDEND-2024-05-16-0.2500",
  "action_type": "DIVIDEND",
  "amount": 0.25,
  "currency": "USD"
}
```

Bad (fragment without context):

```json
"amount": 0.25,
"currency": "USD"
```

### 6.4 Python examples

- Follow PEP 8 style in the examples.
- Include the import statement if the function being called requires one.
- Prefer explicit over implicit. `from pathlib import Path` rather than
  `import pathlib`.

### 6.5 Error output

Show error output verbatim, in a `text` block:

````markdown
```text
Validation FAILED with the following errors:
  - Action US0378331005-DIVIDEND-2024-05-16-0.2500: arithmetic: DIVIDEND amount must be positive: -0.25
```
````

Do not paraphrase error messages. If the message contains a path, show
the path.

### 6.6 Truncating long output

If output is very long, use `...` on its own line. Do not silently drop
lines without a marker.

```text
Loading Asset Identifiers registry...
  Loaded 294 ISINs
...
OK: 242 actions validated successfully.
```

---

## 7. Tables

Tables are used heavily in this repository's docs. They are the primary
way to communicate structured comparisons.

### 7.1 When to use a table

- Comparing options (e.g. "which flags does each wrapper support")
- Listing fields with types and examples
- Mapping inputs to outputs
- Listing dependencies or blockers

### 7.2 When not to use a table

- Prose (narrative content)
- Code (use code blocks)
- Long paragraphs (use sections)

If a table cell contains more than ~80 characters, the table is probably
the wrong format. Break it into subsections.

### 7.3 Formatting

- Left-align all columns by default with `|:---|`.
- Center-align boolean columns with `|:---:|`.
- Right-align numeric columns with `|---:|`.
- Use backticks inside cells for code.
- Use `—` (em dash) for "not applicable".

Example:

| Field | Required | Type |
|-------|:--------:|------|
| `isin` | ✅ | string |
| `amount` | — | number |
| `currency` | — | string |

### 7.4 Column width

Column widths in the source do not need to match render width. Markdown
renderers compute widths automatically. Keep the source table readable
by hand but do not obsess over alignment.

---

## 8. Cross-references and links

### 8.1 Linking within `docs/`

Use relative links with the `.md` extension:

```markdown
See [`action_types.md`](./action_types.md) for definitions.
```

Do not use absolute GitHub URLs. Relative links work in every context:
GitHub web UI, local preview, generated sites.

### 8.2 Linking to code

Always link to files with backticks:

```markdown
See `tools/validate.py` for the implementation.
```

Include a link only if the file is not in the same directory and you want
a clickable reference:

```markdown
See [`tools/validate.py`](../tools/validate.py) for the implementation.
```

### 8.3 Linking to sections within a file

Use anchors:

```markdown
See [Warnings vs errors](#warnings-vs-errors) for details.
```

Verify the anchor is correct after editing headings.

### 8.4 External links

- Always use `https://`, never `http://`.
- Do not use link shorteners.
- Link to the exact page, not the top-level site.
- Check that links work before submitting.

### 8.5 Broken link detection

There is no automated link checker in CI yet. Verify links manually or
with a tool like `markdown-link-check` before submitting a large docs PR.

---

## 9. When to update documentation

### 9.1 Triggers

Update documentation when:

- A schema field is added, renamed, or removed (all affected docs).
- A validation layer changes its rules (`validation_layers.md`).
- A data source is added, fixed, or removed (`data_sources.md`).
- A roadmap item ships (`roadmap.md` — move it out of the planned
  section).
- A wrapper's public API changes (that wrapper's README).
- A CI workflow changes what it runs (root `README.md`, `roadmap.md`).
- The `--strict-isin` default changes (`validation_layers.md`,
  `roadmap.md`).

### 9.2 Same PR, not follow-up

Documentation updates ship in the **same pull request** as the code
change. This is enforced by the PR template, which requires a docs
update section if the change is user-visible.

A follow-up docs PR is acceptable only when:

- The original PR is time-critical (hotfix).
- The docs update is substantial and requires its own review.

Otherwise, docs and code ship together.

### 9.3 Changelog

Every user-visible change adds a line to `CHANGELOG.md`. See the root
`CONTRIBUTING.md` for the exact format.

---

## 10. Workflow for a docs PR

### 10.1 Before you start

1. **Search for existing content.** The change may fit an existing file
   rather than a new one. Do not create `docs/new_topic.md` unless the
   topic has no home.
2. **Open an issue for large changes.** A new doc, a major rewrite, or a
   restructure warrants a discussion before writing.
3. **Read the existing docs.** Match the tone and structure of the file
   you are editing.

### 10.2 Writing

1. Edit or create the file.
2. Follow the conventions in this document.
3. Update the table of contents if you added or renamed sections.
4. Update cross-references in other docs if you renamed a heading that
   is linked elsewhere.

### 10.3 Testing

See [Testing your changes](#13-testing-your-changes) below.

### 10.4 Submitting

1. Commit with a clear message:

   ```bash
   git commit -m "docs: clarify temporal rules for DELISTING"
   ```

   Use the `docs:` prefix. The rest of the message describes the change,
   not the file.

2. Open a PR using the template.

3. Fill in the "Documentation" section of the PR template.

4. Request review from a maintainer.

### 10.5 During review

Reviewers may ask for:

- Tightening language (removing hedging, using concrete values)
- Adding failure examples where only success is shown
- Fixing anchors
- Splitting long sections

Accept these changes; they improve the doc. Push back only if a
reviewer's suggestion contradicts this guide, and cite the specific
section.

---

## 11. Review checklist

Reviewers of docs PRs check the following.

### Accuracy

- [ ] Every rule cites the implementation that enforces it.
- [ ] Every example is valid (passes the validator, if applicable).
- [ ] Every failure example produces the claimed error message.
- [ ] Every date is in ISO 8601 format.
- [ ] Every field name matches `schema.json`.
- [ ] Every file path is correct.

### Structure

- [ ] The doc has a title, purpose paragraph, and table of contents.
- [ ] Section numbers are stable (no renumbering).
- [ ] The `See also` section is present and up-to-date.
- [ ] The table of contents matches the sections.

### Style

- [ ] Second person for instructions.
- [ ] Present tense for descriptions.
- [ ] Active voice.
- [ ] No emojis.
- [ ] No empty praise phrases ("very", "simply", "just").
- [ ] Consistent terminology.

### Links

- [ ] Internal links resolve.
- [ ] External links use `https://`.
- [ ] Anchor links match heading text.

### Completeness

- [ ] Edge cases documented, not just the happy path.
- [ ] Related docs updated if a heading was renamed.
- [ ] `CHANGELOG.md` updated if user-visible.

---

## 12. Common pitfalls

### 12.1 Hedging language

Avoid: "The validator usually catches this."
Use: "The validator catches this."

If there are exceptions, name them. If there are not, do not hedge.

### 12.2 Vague references

Avoid: "See the other doc for details."
Use: "See [`action_types.md`](./action_types.md) for the exact date rules."

Every link names its destination.

### 12.3 Stale examples

Examples rot. A JSON example with `"version": "1.0.0"` becomes wrong when
v1.1.0 ships. Use placeholders or check the example against the current
state before submitting.

For examples that reference specific versions, use the format used in
the rest of the docs: show a specific version and note whether it is
current.

### 12.4 Missing failure modes

Half of the value of a doc is showing what fails. If a section describes
a rule, show the case where the rule is violated. If a section describes
a source, describe where it breaks.

### 12.5 Undocumented behavior

Do not describe behavior that is not implemented. The docs describe what
the code does, not what it should do. Planned behavior belongs in
`roadmap.md`.

### 12.6 Over-linking

Do not link every mention of a file. Link the first mention, then use
backticks for subsequent mentions.

### 12.7 Inconsistent capitalization

- "registry" (lowercase) is generic.
- "Registry" (capital R) refers to a specific named thing, e.g. the
  "Corporate Actions Registry".
- "Asset Identifiers Registry" (capital R) is a specific sibling
  registry.
- Section headings use title case: "What Lives Where", not "What lives
  where". Exception: sentence case is used in this repository because
  section headings are often longer. Pick one and stay consistent within
  a file.

### 12.8 Unexplained jargon

Terms like ISIN, MIC, LEI, FIGI are common in financial data. Define
them on first use in each doc, even if the term is defined in another
doc. A reader should not have to hunt across files.

---

## 13. Testing your changes

### 13.1 Render locally

GitHub renders markdown the same way as the web UI. To check locally,
use `grip`:

```bash
pip install grip
grip docs/your_file.md
```

Or use VS Code's markdown preview (`Cmd+Shift+V` or `Ctrl+Shift+V`).

### 13.2 Check anchors

After editing headings, verify that the table of contents links work.
On GitHub, click each link in the rendered preview. Locally, search for
the anchor in the raw file.

### 13.3 Check code examples

For JSON examples, paste them into a file and run:

```bash
python3 -c "import json; json.load(open('example.json'))"
```

For bash examples, run them in a scratch directory. Make sure the
command works.

For Python examples, run them with the current venv active.

### 13.4 Check links

For internal links, verify the target file exists:

```bash
for f in $(grep -oP '\]\(\./\K[^)]+' docs/*.md | sort -u); do
    [ -f "docs/$f" ] || echo "MISSING: $f"
done
```

For external links, a manual check is sufficient for small PRs. For large
PRs, use `markdown-link-check`:

```bash
npx markdown-link-check docs/your_file.md
```

### 13.5 Spell check

Run a spell check before submitting:

```bash
aspell check docs/your_file.md
```

Add domain-specific terms (ISIN, MIC, CUSIP) to a personal dictionary
rather than to a project file.

### 13.6 Line endings

Ensure LF line endings, not CRLF. This is enforced by `.gitattributes`
if present; otherwise check with:

```bash
file docs/your_file.md
```

Should not contain "CRLF line terminators".

---

## 14. What this guide does not cover

This guide is specifically for the `docs/` folder. Other contribution
topics are covered elsewhere:

| Topic | See |
|-------|-----|
| Code contribution process | [`CONTRIBUTING.md`](../CONTRIBUTING.md) |
| Commit message format | [`CONTRIBUTING.md`](../CONTRIBUTING.md) |
| PR review process | [`CONTRIBUTING.md`](../CONTRIBUTING.md), [`.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md) |
| Reporting a missing action | [`.github/ISSUE_TEMPLATE/action_update.md`](../.github/ISSUE_TEMPLATE/action_update.md) |
| Proposing a new data source | [`.github/ISSUE_TEMPLATE/data_source.md`](../.github/ISSUE_TEMPLATE/data_source.md) |
| Reporting a bug | Use the bug report template |
| Security issues | See `SECURITY.md` (if present) |
| Wrapper-specific contribution | Each wrapper's `README.md` |

If a topic has no home, propose one by opening an issue.

---

## See also

- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — code contribution process
- [`action_types.md`](./action_types.md) — action type semantics
- [`validation_layers.md`](./validation_layers.md) — the seven validation layers
- [`data_sources.md`](./data_sources.md) — data sources and licensing
- [`roadmap.md`](./roadmap.md) — planned versions
- [`../README.md`](../README.md) — repository overview
