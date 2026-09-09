"""
Tests for provenance validation in the Corporate Actions Registry.

These tests verify that `validate_provenance` correctly checks:
- provenance dictionary is present (or not)
- source_url is required and non-empty
- source_url must start with http:// or https://
- other provenance fields are ignored
- returns a list of error strings

The function under test lives in `tools/validate.py`.
"""

import os
import sys

# Ensure repository root is on sys.path so we can import tools.validate
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.validate import validate_provenance


class TestProvenanceValidation:
    def test_valid_http_source_url(self):
        action = {"provenance": {"source_url": "http://example.com"}}
        assert validate_provenance(action) == []

    def test_valid_https_source_url(self):
        action = {"provenance": {"source_url": "https://example.com/page"}}
        assert validate_provenance(action) == []

    def test_missing_provenance_object(self):
        action = {}
        errors = validate_provenance(action)
        assert any("provenance.source_url is required" in e for e in errors)

    def test_provenance_without_source_url(self):
        action = {"provenance": {"source": "Some source"}}
        errors = validate_provenance(action)
        assert any("provenance.source_url is required" in e for e in errors)

    def test_empty_source_url(self):
        action = {"provenance": {"source_url": ""}}
        errors = validate_provenance(action)
        assert any("provenance.source_url is required" in e for e in errors)

    def test_source_url_not_http(self):
        action = {"provenance": {"source_url": "ftp://example.com/file"}}
        errors = validate_provenance(action)
        assert any("source_url must be HTTP(S)" in e for e in errors)

    def test_source_url_without_scheme(self):
        action = {"provenance": {"source_url": "www.example.com"}}
        errors = validate_provenance(action)
        assert any("source_url must be HTTP(S)" in e for e in errors)

    def test_source_url_with_uppercase_scheme(self):
        action = {"provenance": {"source_url": "HTTPS://EXAMPLE.COM"}}
        # The function checks for lowercase 'http' prefixes, so this should fail.
        errors = validate_provenance(action)
        assert any("source_url must be HTTP(S)" in e for e in errors)

    def test_source_url_none(self):
        action = {"provenance": {"source_url": None}}
        errors = validate_provenance(action)
        assert any("provenance.source_url is required" in e for e in errors)


class TestProvenanceExtraFields:
    def test_extra_fields_ignored(self):
        action = {
            "provenance": {
                "source": "Some source",
                "source_url": "https://example.com",
                "verification_source": "SEC",
                "verification_url": "https://sec.gov",
            }
        }
        assert validate_provenance(action) == []