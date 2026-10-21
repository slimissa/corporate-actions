"""Contract-surface test — every § 4 method and § 4.9 constant must be
present in every wrapper.

Guards against the class of bug that shipped in v1.2.1: Python was
missing `known_as_of` while JS/Go/Rust had it, and the release message
claimed "all four wrappers". Each wrapper's own suite passed in
isolation; only a cross-wrapper surface check catches this.

Design:
  - CANONICAL_METHODS / CANONICAL_CONSTANTS are hardcoded ground truth.
    Adding a § 4 method is a deliberate test edit, not a silent pass.
  - A separate test parses § 4 headings and asserts the hardcoded list
    is still current, so "§ 4.12 added without a test entry" fails.
  - Python detection uses ast.parse (exact — no docstring false positives).
  - JS/Go/Rust detection uses line-anchored regex (documented below).
  - Extractor sanity tests + negative tests prevent a broken pattern
    from silently passing all per-wrapper checks.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List, Set

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "wrapper_contract.md"


# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------

# Canonical methods from § 4.1 – § 4.11, with per-language spelling.
# Keys are Python snake_case names (the canonical form).
CANONICAL_METHODS: Dict[str, Dict[str, str]] = {
    "by_isin":         {"python": "by_isin",         "js": "byIsin",         "go": "ByISIN",         "rust": "by_isin"},
    "by_action_id":    {"python": "by_action_id",    "js": "byActionId",     "go": "ByActionID",     "rust": "by_action_id"},
    "by_action_type":  {"python": "by_action_type",  "js": "byActionType",   "go": "ByActionType",   "rust": "by_action_type"},
    "by_date_range":   {"python": "by_date_range",   "js": "byDateRange",    "go": "ByDateRange",    "rust": "by_date_range"},
    "by_ticker":       {"python": "by_ticker",       "js": "byTicker",       "go": "ByTicker",       "rust": "by_ticker"},
    "all_action_types":{"python": "all_action_types","js": "allActionTypes", "go": "AllActionTypes", "rust": "all_action_types"},
    "all_actions":     {"python": "all_actions",     "js": "allActions",     "go": "AllActions",     "rust": "all_actions"},
    "count":           {"python": "count",           "js": "count",          "go": "Count",          "rust": "count"},
    "adjust_prices":   {"python": "adjust_prices",   "js": "adjustPrices",   "go": "AdjustPrices",   "rust": "adjust_prices"},
    "known_as_of":     {"python": "known_as_of",     "js": "knownAsOf",      "go": "KnownAsOf",      "rust": "known_as_of"},
    "to_dict":         {"python": "to_dict",         "js": "toJSON",         "go": "ToJSON",         "rust": "to_json"},
    "save":            {"python": "save",            "js": "save",           "go": "Save",           "rust": "save"},
    "meta":            {"python": "meta",            "js": "meta",           "go": "Meta",           "rust": "meta"},
}

# Canonical constants from § 4.9
CANONICAL_CONSTANTS: Dict[str, Dict[str, str]] = {
    "DEFAULT_DATE_FIELD": {"python": "DEFAULT_DATE_FIELD", "js": "DEFAULT_DATE_FIELD", "go": "DefaultDateField", "rust": "DEFAULT_DATE_FIELD"},
    "VALID_DATE_FIELDS":  {"python": "VALID_DATE_FIELDS",  "js": "VALID_DATE_FIELDS",  "go": "ValidDateFields",  "rust": "VALID_DATE_FIELDS"},
    "DEFAULT_ADJUST_FOR": {"python": "DEFAULT_ADJUST_FOR", "js": "DEFAULT_ADJUST_FOR", "go": "DefaultAdjustFor", "rust": "DEFAULT_ADJUST_FOR"},
}

# Methods that do NOT have a § 4.N `method_name` heading (they live under
# § 4.7 Serialization). Excluded from the "each § 4 heading is in the
# canonical map" reverse check.
_SECTION_4_7_METHODS = {"to_dict", "save", "meta"}

WRAPPER_SOURCES: Dict[str, List[Path]] = {
    "python": [
        ROOT / "wrappers/python/corporate_actions_registry/registry.py",
        ROOT / "wrappers/python/corporate_actions_registry/__init__.py",
    ],
    "js":   [ROOT / "wrappers/javascript/src/index.js"],
    "go":   [ROOT / "wrappers/go/registry/registry.go"],
    "rust": [ROOT / "wrappers/rust/src/lib.rs"],
}

# Per-language method patterns. Each is anchored to start-of-line so a
# method name appearing inside a docstring or a `# comment` on its own
# line cannot false-positive (Python uses ast, so this is JS/Go/Rust only).
METHOD_PATTERNS = {
    # `\b` after {name} prevents `save` matching `save_all`; `[^)]*` captures
    # JS params (they cannot contain nested parens in this wrapper).
    "js":   r"^\s+(?:static\s+)?(?:async\s+)?(?:get\s+)?{name}\b\s*\([^)]*\)\s*(?:\{|=>)",
    # Go methods never take generics in this wrapper; `\b` guards against
    # prefix collision (Save/SaveFile).
    "go":   r"^func\s+\([a-z]+\s+\*Registry\)\s+{name}\b\s*\(",
    # Rust: `[^(\n]*` absorbs the full generic list including nested
    # angle brackets (`<P: AsRef<Path>>`). Bounded nesting with `[^>]*`
    # stops at the first `>` and leaves the trailing one to collide
    # with `\(`, which was the v1.2.2 test-only bug. `\b` prevents
    # `save` matching `save_all`.
    "rust": r"^\s+pub\s+(?:async\s+)?fn\s+{name}\b\s*[^(\n]*\(",
}


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def _python_defines_method(name: str) -> bool:
    """True if `name` is defined as a function/method in any Python wrapper file.

    Uses ast.parse so docstring contents, string literals, and comments
    cannot false-positive. Handles @property getters (they are still
    FunctionDef nodes in the AST).
    """
    for f in WRAPPER_SOURCES["python"]:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == name:
                    return True
    return False


def _regex_defines_method(lang: str, name: str) -> bool:
    # Use .replace, not .format: the JS pattern contains literal `\{|=>`
    # which .format() would treat as an unknown placeholder ({|=>) and
    # raise ValueError. .replace leaves the braces alone.
    pattern = METHOD_PATTERNS[lang].replace("{name}", re.escape(name))
    source = WRAPPER_SOURCES[lang][0].read_text(encoding="utf-8")
    return re.search(pattern, source, re.MULTILINE) is not None


def _method_present(lang: str, name: str) -> bool:
    if lang == "python":
        return _python_defines_method(name)
    return _regex_defines_method(lang, name)


def _constant_present(lang: str, name: str) -> bool:
    """True if `name` appears (word-boundary) in any wrapper source file.

    Constants are `DEFAULT_DATE_FIELD = ...` in Python, `pub const` in
    Rust, `const`/`var` in Go, `const` in JS, or re-exported via
    `module.exports` / `pub use`. Word-boundary match covers all forms.
    """
    for f in WRAPPER_SOURCES[lang]:
        if re.search(rf"\b{re.escape(name)}\b", f.read_text(encoding="utf-8")):
            return True
    return False


# ---------------------------------------------------------------------------
# Contract parsing (§ 4 headings only; § 4.7 has no per-method headings)
# ---------------------------------------------------------------------------

def _parse_section_4_headings() -> Set[str]:
    """Extract method names from `### 4.N \\`name\\`` headings.

    Does NOT include § 4.7 (Serialization) or § 4.9 (Constants) — those
    have prose headings, not backtick-quoted method names. Their members
    (`to_dict`, `save`, `meta`, constants) live in the hardcoded maps.
    """
    text = CONTRACT.read_text(encoding="utf-8")
    return set(re.findall(
        r"^### 4\.\d+[a-z]? `([a-z_][a-z0-9_]*)`",
        text, re.MULTILINE,
    ))


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------

def test_contract_file_exists():
    assert CONTRACT.is_file(), f"missing contract: {CONTRACT}"


@pytest.mark.parametrize("lang", sorted(WRAPPER_SOURCES))
def test_wrapper_sources_exist(lang: str):
    for f in WRAPPER_SOURCES[lang]:
        assert f.is_file(), f"{lang} source missing: {f}"


def test_every_section_4_heading_has_a_canonical_entry():
    """§ 4.N `method` headings must all be in CANONICAL_METHODS.

    Catches: someone adds § 4.12 to the contract without adding a test
    entry — the new method is not exercised by any wrapper.
    """
    declared = _parse_section_4_headings()
    hardcoded = set(CANONICAL_METHODS.keys())
    missing = declared - hardcoded
    assert not missing, (
        f"§ 4 declares methods not in CANONICAL_METHODS: {sorted(missing)}. "
        f"Add them to tests/test_contract_surface.py."
    )


def test_every_canonical_method_has_a_section_4_heading():
    """Every CANONICAL_METHODS entry (excluding § 4.7 items) must have a § 4.N heading.

    Catches: someone removes a § 4.N heading but forgets to remove the
    method from CANONICAL_METHODS — the test would still require it.
    """
    declared = _parse_section_4_headings()
    hardcoded = set(CANONICAL_METHODS.keys()) - _SECTION_4_7_METHODS
    stale = hardcoded - declared
    assert not stale, (
        f"CANONICAL_METHODS has entries with no § 4.N heading: {sorted(stale)}. "
        f"If the method was removed from the contract, remove it here too."
    )


def test_all_constants_mentioned_in_contract():
    text = CONTRACT.read_text(encoding="utf-8")
    for name in CANONICAL_CONSTANTS:
        assert name in text, (
            f"Constant `{name}` is in CANONICAL_CONSTANTS but not in the contract."
        )


# ---------------------------------------------------------------------------
# Per-wrapper × per-method surface checks
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lang", sorted(WRAPPER_SOURCES))
@pytest.mark.parametrize("canonical", sorted(CANONICAL_METHODS), ids=sorted(CANONICAL_METHODS))
def test_wrapper_implements_method(lang: str, canonical: str):
    """Every wrapper must implement every canonical method."""
    localized = CANONICAL_METHODS[canonical][lang]
    assert _method_present(lang, localized), (
        f"{lang} wrapper does not define `{localized}` "
        f"(canonical `{canonical}`, wrapper_contract.md § 4). "
        f"Searched: {[str(p) for p in WRAPPER_SOURCES[lang]]}"
    )


@pytest.mark.parametrize("lang", sorted(WRAPPER_SOURCES))
@pytest.mark.parametrize("canonical", sorted(CANONICAL_CONSTANTS), ids=sorted(CANONICAL_CONSTANTS))
def test_wrapper_exports_constant(lang: str, canonical: str):
    """Every wrapper must export every § 4.9 constant."""
    localized = CANONICAL_CONSTANTS[canonical][lang]
    assert _constant_present(lang, localized), (
        f"{lang} wrapper does not export `{localized}` "
        f"(canonical `{canonical}`, wrapper_contract.md § 4.9). "
        f"Searched: {[str(p) for p in WRAPPER_SOURCES[lang]]}"
    )


# ---------------------------------------------------------------------------
# Extractor sanity — positive: the patterns actually work
# ---------------------------------------------------------------------------

def test_python_extractor_positive():
    """Sanity: AST finds a normal method definition in a synthetic file."""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write("class Foo:\n    def by_isin(self, isin): pass\n")
        tmp = Path(f.name)
    try:
        old = WRAPPER_SOURCES["python"]
        WRAPPER_SOURCES["python"] = [tmp]
        try:
            assert _python_defines_method("by_isin")
        finally:
            WRAPPER_SOURCES["python"] = old
    finally:
        tmp.unlink()


def test_python_extractor_handles_property():
    """Sanity: AST finds a @property-decorated method."""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write("class Foo:\n    @property\n    def meta(self): return {}\n")
        tmp = Path(f.name)
    try:
        old = WRAPPER_SOURCES["python"]
        WRAPPER_SOURCES["python"] = [tmp]
        try:
            assert _python_defines_method("meta")
        finally:
            WRAPPER_SOURCES["python"] = old
    finally:
        tmp.unlink()


@pytest.mark.parametrize("lang,source", [
    ("js",   "class C {\n  byIsin(isin) {\n    return [];\n  }\n}\n"),
    ("js",   "class C {\n  get meta() {\n    return {};\n  }\n}\n"),
    ("go",   "func (r *Registry) ByISIN(isin string) []Action {\n\treturn nil\n}\n"),
    ("rust", "impl R {\n    pub fn by_isin(&self, isin: &str) -> Vec<Action> {\n        vec![]\n    }\n}\n"),
])
def test_regex_extractor_positive(lang: str, source: str):
    """Sanity: the regex patterns match realistic wrapper-source forms."""
    import tempfile
    name_map = {"js": "byIsin", "go": "ByISIN", "rust": "by_isin"}
    # For the JS getter test, name_map says "byIsin" — but the source is `get meta()`
    # so we need to detect "meta" not "byIsin". Handle by checking both.
    if "get meta" in source:
        name_map = {"js": "meta", "go": "Meta", "rust": "meta"}
    with tempfile.NamedTemporaryFile("w", suffix=f".{lang if lang != 'rust' else 'rs'}", delete=False) as f:
        f.write(source)
        tmp = Path(f.name)
    try:
        old = WRAPPER_SOURCES[lang]
        WRAPPER_SOURCES[lang] = [tmp]
        try:
            assert _regex_defines_method(lang, name_map[lang])
        finally:
            WRAPPER_SOURCES[lang] = old
    finally:
        tmp.unlink()


# ---------------------------------------------------------------------------
# Extractor sanity — negative: the patterns reject false positives
# ---------------------------------------------------------------------------

def test_python_extractor_rejects_private_method():
    """`_reset_ticker_cache` must not match `reset_ticker_cache`."""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write("class Foo:\n    def _by_isin(self): pass\n")
        tmp = Path(f.name)
    try:
        old = WRAPPER_SOURCES["python"]
        WRAPPER_SOURCES["python"] = [tmp]
        try:
            assert not _python_defines_method("by_isin")
        finally:
            WRAPPER_SOURCES["python"] = old
    finally:
        tmp.unlink()


def test_python_extractor_rejects_docstring_mention():
    """A method name inside a docstring must not be detected as defined."""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(
            "class Foo:\n"
            "    def other(self):\n"
            "        '''This is like by_isin but different.'''\n"
            "        pass\n"
        )
        tmp = Path(f.name)
    try:
        old = WRAPPER_SOURCES["python"]
        WRAPPER_SOURCES["python"] = [tmp]
        try:
            assert not _python_defines_method("by_isin")
        finally:
            WRAPPER_SOURCES["python"] = old
    finally:
        tmp.unlink()


def test_js_extractor_rejects_comment_mention():
    """A method name inside a `// comment` line must not be detected."""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write("class C {\n  // byIsin(isin) { this was the old shape\n}\n")
        tmp = Path(f.name)
    try:
        old = WRAPPER_SOURCES["js"]
        WRAPPER_SOURCES["js"] = [tmp]
        try:
            assert not _regex_defines_method("js", "byIsin")
        finally:
            WRAPPER_SOURCES["js"] = old
    finally:
        tmp.unlink()


# ---------------------------------------------------------------------------
# Diagnostic: coverage summary
# ---------------------------------------------------------------------------

def test_wrapper_method_coverage_summary(capsys):
    """Print how many canonical methods and constants each wrapper covers.

    Fails if any wrapper is below full coverage. Runs in `-v` output as
    a single line per wrapper so triage is fast.
    """
    lines = [f"Coverage out of {len(CANONICAL_METHODS)} methods, "
             f"{len(CANONICAL_CONSTANTS)} constants:"]
    incomplete = []
    for lang in sorted(WRAPPER_SOURCES):
        n_methods = sum(
            1 for c, m in CANONICAL_METHODS.items() if _method_present(lang, m[lang])
        )
        n_constants = sum(
            1 for c, names in CANONICAL_CONSTANTS.items() if _constant_present(lang, names[lang])
        )
        lines.append(
            f"  {lang:10s} {n_methods}/{len(CANONICAL_METHODS)} methods, "
            f"{n_constants}/{len(CANONICAL_CONSTANTS)} constants"
        )
        if n_methods < len(CANONICAL_METHODS) or n_constants < len(CANONICAL_CONSTANTS):
            incomplete.append(lang)
    with capsys.disabled():
        print()
        for line in lines:
            print(line)
    assert not incomplete, (
        f"Incomplete wrappers: {incomplete} — see per-method failures above for detail."
    )
