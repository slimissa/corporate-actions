// Contract tests for the Go wrapper.
//
// These tests read tests/wrapper_contract.json and verify that this
// wrapper's ByDateRange agrees with the shared fixture. The same
// fixture is read by the Python, JavaScript, and Rust wrappers, so a
// regression in any one wrapper shows up in all four suites.
//
// The fixture is not yet in the repository; it arrives in Session 3.5.
// Until it does, every test in this file skips with a message naming
// the missing path. Once the fixture is added, no change to this file
// is required.
//
// Fixture shape is specified in docs/wrapper_contract.md section 8.2.
//
// Run:
//     go test ./registry -run TestContract -v

package registry

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// contractFixturePath is resolved relative to this package's directory.
// `go test ./registry` from wrappers/go runs with cwd set to
// wrappers/go/registry, so ../../../ climbs to the repository root.
const contractFixturePath = "../../../tests/wrapper_contract.json"

// contractFixture mirrors the shape of tests/wrapper_contract.json.
//
// The fixture is shared across all four language wrappers; changing it
// requires updating every wrapper's contract test. See section 8.2 of
// docs/wrapper_contract.md.
type contractFixture struct {
	Actions           []Action        `json:"actions"`
	Queries           []contractQuery `json:"queries"`
	InvalidDateFields []string        `json:"invalid_date_fields"`
}

// contractQuery is one entry in the fixture's queries array.
//
// Start and End are pointers because the fixture uses JSON null for an
// open bound. ExpectedActionIDs is the exact expected output of
// ByDateRange, in order.
type contractQuery struct {
	DateField         string   `json:"date_field"`
	Start             *string  `json:"start"`
	End               *string  `json:"end"`
	ExpectedActionIDs []string `json:"expected_action_ids"`
}

// loadContractFixture reads and parses the shared fixture.
//
// If the fixture is missing, the calling test is skipped with a message
// naming the expected path. A parse error fails the test rather than
// skipping, because a malformed fixture is a bug in the fixture, not a
// reason to skip.
func loadContractFixture(t *testing.T) contractFixture {
	t.Helper()
	path := filepath.FromSlash(contractFixturePath)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("contract fixture required but not readable: %s (%v)", path, err)
	}
	var fixture contractFixture
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("parsing contract fixture %s: %v", path, err)
	}
	return fixture
}

// buildRegistryFromFixture returns a Registry whose actions are the
// fixture's actions.
//
// Uses FromJSON so the loader is exercised as well. A bug in the loader
// surfaces here rather than hiding behind a hand-built Registry that
// duplicates the index logic.
func buildRegistryFromFixture(t *testing.T, fixture contractFixture) *Registry {
	t.Helper()
	actionsJSON, err := json.Marshal(fixture.Actions)
	if err != nil {
		t.Fatalf("marshaling fixture actions: %v", err)
	}
	doc := make([]byte, 0, len(actionsJSON)+32)
	doc = append(doc, `{"meta":{},"actions":`...)
	doc = append(doc, actionsJSON...)
	doc = append(doc, '}')
	reg, err := FromJSON(doc)
	if err != nil {
		t.Fatalf("FromJSON on fixture actions: %v", err)
	}
	return reg
}

// stringSlicesEqual reports whether two string slices are equal in
// length and content, position by position.
//
// Written locally rather than importing `reflect` or `slices` so this
// test file has no dependency beyond the standard library packages it
// already uses.
func stringSlicesEqual(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

// TestContractFixtureShape verifies the fixture is well-formed before
// the tests that consume it run. A malformed fixture fails here rather
// than producing misleading failures in the query test.
//
// The shape assertions also serve as a checklist for the fixture's
// author: every action must have an action_id and an isin; every query
// must name one of the four valid date fields.
func TestContractFixtureShape(t *testing.T) {
	fixture := loadContractFixture(t)

	if len(fixture.Actions) == 0 {
		t.Fatal("fixture has no actions")
	}
	if len(fixture.Queries) == 0 {
		t.Fatal("fixture has no queries")
	}
	if len(fixture.InvalidDateFields) == 0 {
		t.Fatal("fixture has no invalid_date_fields")
	}

	for i, a := range fixture.Actions {
		if a.ActionID == nil {
			t.Errorf("action %d: missing action_id", i)
		}
		if a.ISIN == nil {
			t.Errorf("action %d: missing isin", i)
		}
	}

	for i, q := range fixture.Queries {
		if q.DateField == "" {
			t.Errorf("query %d: missing date_field", i)
			continue
		}
		if !validDateFields[q.DateField] {
			t.Errorf(
				"query %d: date_field %q is not one of the four valid names",
				i, q.DateField,
			)
		}
	}
}

// TestContractFixtureSelfConsistency verifies that every action_id the
// fixture expects in a query result actually exists in the fixture's
// actions, and that no query lists the same action_id twice.
//
// A typo in expected_action_ids would otherwise show up as a failure
// under one language and pass under another, depending on the typo.
func TestContractFixtureSelfConsistency(t *testing.T) {
	fixture := loadContractFixture(t)

	known := make(map[string]bool, len(fixture.Actions))
	for _, a := range fixture.Actions {
		if a.ActionID != nil {
			known[*a.ActionID] = true
		}
	}

	for i, q := range fixture.Queries {
		seen := make(map[string]bool, len(q.ExpectedActionIDs))
		for _, id := range q.ExpectedActionIDs {
			if !known[id] {
				t.Errorf(
					"query %d: expected action_id %q is not in the fixture's actions",
					i, id,
				)
			}
			if seen[id] {
				t.Errorf(
					"query %d: action_id %q appears twice in expected_action_ids",
					i, id,
				)
			}
			seen[id] = true
		}
	}
}

// TestContractQueries runs every fixture query through ByDateRange and
// asserts the returned action_ids match the fixture exactly, in order.
//
// This is the test that proves Go agrees with Python, JavaScript, and
// Rust on filter semantics, inclusive bounds, missing-field skipping,
// and sort order.
//
// Each query is a subtest so a failure names the specific query rather
// than aborting on the first mismatch.
func TestContractQueries(t *testing.T) {
	fixture := loadContractFixture(t)
	reg := buildRegistryFromFixture(t, fixture)

	if len(fixture.Queries) == 0 {
		t.Skip("no queries in fixture")
	}

	for i, q := range fixture.Queries {
		q := q // capture loop variable
		name := fmt.Sprintf("query_%02d_%s", i, q.DateField)
		t.Run(name, func(t *testing.T) {
			start := ""
			end := ""
			if q.Start != nil {
				start = *q.Start
			}
			if q.End != nil {
				end = *q.End
			}

			got, err := reg.ByDateRange(start, end, q.DateField)
			if err != nil {
				t.Fatalf(
					"ByDateRange(%q, %q, %q) returned error: %v",
					start, end, q.DateField, err,
				)
			}

			ids := actionIDs(got)
			if !stringSlicesEqual(ids, q.ExpectedActionIDs) {
				t.Fatalf(
					"ByDateRange(%q, %q, %q)\n got:  %v\n want: %v",
					start, end, q.DateField,
					ids, q.ExpectedActionIDs,
				)
			}
		})
	}
}

// TestContractInvalidDateFields asserts that every field name in the
// fixture's invalid_date_fields list causes ByDateRange to return an
// error that wraps ErrInvalidDateField, and that the error message
// names the offending value.
//
// The check on the message matters because the contract requires the
// caller to see what they typed. An empty string is a special case: the
// message contains no visible value, but the error type still matches,
// so the assertion passes without weakening the check.
func TestContractInvalidDateFields(t *testing.T) {
	fixture := loadContractFixture(t)
	reg := buildRegistryFromFixture(t, fixture)

	if len(fixture.InvalidDateFields) == 0 {
		t.Skip("no invalid_date_fields in fixture")
	}

	for _, bad := range fixture.InvalidDateFields {
		bad := bad // capture loop variable
		name := fmt.Sprintf("field_%q", bad)
		t.Run(name, func(t *testing.T) {
			_, err := reg.ByDateRange("", "", bad)
			if err == nil {
				t.Fatalf("expected error for date field %q, got nil", bad)
			}
			if !errors.Is(err, ErrInvalidDateField) {
				t.Errorf(
					"expected ErrInvalidDateField for %q, got %v",
					bad, err,
				)
			}
			if bad != "" && !strings.Contains(err.Error(), bad) {
				t.Errorf(
					"error message %q does not name the offending field %q",
					err.Error(), bad,
				)
			}
		})
	}
}
