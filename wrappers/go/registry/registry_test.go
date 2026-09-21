package registry

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

// ----------------------------------------------------------------------
// Fixtures
// ----------------------------------------------------------------------

// sampleJSON is the standard four-action fixture used across the suite.
//
// Actions:
//   - NVDA 10:1 split on 2024-06-10
//   - AAPL dividend on 2024-05-16
//   - AAPL 4:1 split on 2020-08-31
//   - META symbol change on 2022-06-09 (no ex_date, no record_date)
//
// The spread of dates and the missing ex_date let the ByDateRange tests
// exercise inclusive bounds, missing fields, and sorting.
const sampleJSON = `{
  "meta": {
    "version": "1.0.0",
    "generated_at": "2026-09-09T12:00:00Z",
    "source": "Test",
    "notes": "Sample data for testing"
  },
  "actions": [
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
        "source": "NVIDIA",
        "source_url": "https://example.com/nvda-split",
        "verification_source": "SEC EDGAR"
      },
      "impact": {
        "price_multiplier": 0.1,
        "share_multiplier": 10.0
      }
    },
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
        "source": "Apple",
        "source_url": "https://example.com/aapl-div"
      },
      "impact": {
        "cash_adjustment": 0.25,
        "price_multiplier": 1.0,
        "share_multiplier": 1.0
      }
    },
    {
      "isin": "US0378331005",
      "action_id": "US0378331005-SPLIT-2020-08-31-4-1",
      "action_type": "SPLIT",
      "ratio": "4:1",
      "dates": {
        "announcement": "2020-07-30",
        "ex_date": "2020-08-31",
        "record_date": "2020-08-24",
        "effective_date": "2020-08-31"
      },
      "status": "COMPLETED",
      "provenance": {
        "source": "Apple",
        "source_url": "https://example.com/aapl-split"
      },
      "impact": {
        "price_multiplier": 0.25,
        "share_multiplier": 4.0
      }
    },
    {
      "isin": "US30303M1027",
      "action_id": "US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL",
      "action_type": "SYMBOL_CHANGE",
      "dates": {
        "announcement": "2022-06-09",
        "effective_date": "2022-06-09"
      },
      "status": "COMPLETED",
      "provenance": {
        "source": "Meta",
        "source_url": "https://example.com/meta-symbol"
      },
      "impact": {}
    }
  ]
}`

// tiebreakJSON holds two actions sharing an ex_date, to prove the sort
// breaks ties on action_id rather than on insertion order.
const tiebreakJSON = `{
  "meta": {"version": "1.0.0", "generated_at": "2026-09-09T00:00:00Z", "source": "Test"},
  "actions": [
    {
      "isin": "US0000000001",
      "action_id": "US0000000001-DIVIDEND-2024-05-16-0.2500",
      "action_type": "DIVIDEND",
      "dates": {"announcement": "2024-05-02", "ex_date": "2024-05-16", "effective_date": "2024-05-23"}
    },
    {
      "isin": "US0000000002",
      "action_id": "US0000000002-DIVIDEND-2024-05-16-0.3000",
      "action_type": "DIVIDEND",
      "dates": {"announcement": "2024-05-02", "ex_date": "2024-05-16", "effective_date": "2024-05-23"}
    }
  ]
}`

// ----------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------

// writeTempFile writes content to a fresh file under t.TempDir() and
// returns its path. If prefix is non-empty the file is written with
// that byte sequence prepended (used for the BOM test).
func writeTempFile(t *testing.T, content string, prefix []byte) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "actions.json")
	data := append(append([]byte{}, prefix...), []byte(content)...)
	if err := os.WriteFile(path, data, 0644); err != nil {
		t.Fatalf("write temp file: %v", err)
	}
	return path
}

// loadSample returns a Registry built from sampleJSON.
func loadSample(t *testing.T) *Registry {
	t.Helper()
	r, err := FromJSON([]byte(sampleJSON))
	if err != nil {
		t.Fatalf("FromJSON(sampleJSON) failed: %v", err)
	}
	return r
}

// loadTiebreak returns a Registry built from tiebreakJSON.
func loadTiebreak(t *testing.T) *Registry {
	t.Helper()
	r, err := FromJSON([]byte(tiebreakJSON))
	if err != nil {
		t.Fatalf("FromJSON(tiebreakJSON) failed: %v", err)
	}
	return r
}

// actionIDs extracts the action_id of every action, using "" for a nil
// ID so the result is always comparable.
func actionIDs(actions []Action) []string {
	ids := make([]string, len(actions))
	for i, a := range actions {
		if a.ActionID != nil {
			ids[i] = *a.ActionID
		}
	}
	return ids
}

// ----------------------------------------------------------------------
// LoadRegistry / FromJSON
// ----------------------------------------------------------------------

func TestLoadRegistryFromFile(t *testing.T) {
	path := writeTempFile(t, sampleJSON, nil)
	r, err := LoadRegistry(path)
	if err != nil {
		t.Fatalf("LoadRegistry: %v", err)
	}
	if r.Count() != 4 {
		t.Errorf("Count: got %d, want 4", r.Count())
	}
	if r.Meta().Version == nil || *r.Meta().Version != "1.0.0" {
		t.Errorf("Meta().Version: got %v, want \"1.0.0\"", r.Meta().Version)
	}
}

func TestLoadRegistryMissingFile(t *testing.T) {
	_, err := LoadRegistry("/nonexistent/path/actions.json")
	if err == nil {
		t.Fatal("expected error for missing file, got nil")
	}
}

func TestFromJSONInvalid(t *testing.T) {
	_, err := FromJSON([]byte("not valid json"))
	if err == nil {
		t.Fatal("expected error for invalid JSON, got nil")
	}
}

func TestFromJSONMissingActionsKey(t *testing.T) {
	_, err := FromJSON([]byte(`{"meta":{"version":"1.0.0"}}`))
	if err == nil {
		t.Fatal("expected error for missing actions, got nil")
	}
	if !strings.Contains(err.Error(), "missing 'actions' key") {
		t.Errorf("error message does not name the missing key: %v", err)
	}
}

func TestFromJSONActionsNotArray(t *testing.T) {
	cases := []string{
		`{"actions":"string"}`,
		`{"actions":42}`,
		`{"actions":true}`,
		`{"actions":null}`,
		`{"actions":{"not":"a list"}}`,
	}
	for _, doc := range cases {
		doc := doc
		t.Run(doc, func(t *testing.T) {
			_, err := FromJSON([]byte(doc))
			if err == nil {
				t.Fatalf("expected error for %s, got nil", doc)
			}
		})
	}
}

func TestFromJSONNonObjectEntries(t *testing.T) {
	cases := []struct {
		name string
		doc  string
	}{
		{"string entry", `{"actions":["str"]}`},
		{"number entry", `{"actions":[42]}`},
		{"boolean entry", `{"actions":[true]}`},
		{"null entry", `{"actions":[null]}`},
		{"array entry", `{"actions":[[]]}`},
	}
	for _, c := range cases {
		c := c
		t.Run(c.name, func(t *testing.T) {
			_, err := FromJSON([]byte(c.doc))
			if err == nil {
				t.Fatalf("expected error for %s, got nil", c.doc)
			}
			if !strings.Contains(err.Error(), "not an object") {
				t.Errorf("error does not mention 'not an object': %v", err)
			}
		})
	}
}

func TestFromJSONNonObjectEntryNamesIndex(t *testing.T) {
	doc := `{"actions":[{"action_id":"ok"}, "bad"]}`
	_, err := FromJSON([]byte(doc))
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !strings.Contains(err.Error(), "index 1") {
		t.Errorf("error does not name index 1: %v", err)
	}
}

func TestFromJSONBOM(t *testing.T) {
	bom := []byte{0xEF, 0xBB, 0xBF}
	path := writeTempFile(t, sampleJSON, bom)
	r, err := LoadRegistry(path)
	if err != nil {
		t.Fatalf("LoadRegistry with BOM: %v", err)
	}
	if r.Count() != 4 {
		t.Errorf("Count after BOM strip: got %d, want 4", r.Count())
	}
}

func TestFromJSONEmptyActions(t *testing.T) {
	r, err := FromJSON([]byte(`{"actions":[]}`))
	if err != nil {
		t.Fatalf("empty actions should load: %v", err)
	}
	if r.Count() != 0 {
		t.Errorf("Count: got %d, want 0", r.Count())
	}
	if got := r.ByISIN("US0378331005"); len(got) != 0 {
		t.Errorf("ByISIN on empty registry: got %d, want 0", len(got))
	}
	if got := r.ByActionType("SPLIT"); len(got) != 0 {
		t.Errorf("ByActionType on empty registry: got %d, want 0", len(got))
	}
	if got := r.AllActionTypes(); len(got) != 0 {
		t.Errorf("AllActionTypes on empty registry: got %v, want empty", got)
	}
}

func TestFromJSONMissingMeta(t *testing.T) {
	r, err := FromJSON([]byte(`{"actions":[]}`))
	if err != nil {
		t.Fatalf("missing meta should be ok: %v", err)
	}
	m := r.Meta()
	if m.Version != nil || m.Source != nil || m.GeneratedAt != nil {
		t.Errorf("expected empty Meta, got %+v", m)
	}
}

func TestFromJSONNullMeta(t *testing.T) {
	r, err := FromJSON([]byte(`{"actions":[],"meta":null}`))
	if err != nil {
		t.Fatalf("null meta should be ok: %v", err)
	}
	m := r.Meta()
	if m.Version != nil {
		t.Errorf("expected nil Version, got %v", m.Version)
	}
}

// ----------------------------------------------------------------------
// ByISIN
// ----------------------------------------------------------------------

func TestByISIN(t *testing.T) {
	r := loadSample(t)
	aapl := r.ByISIN("US0378331005")
	if len(aapl) != 2 {
		t.Fatalf("len: got %d, want 2", len(aapl))
	}
	for _, a := range aapl {
		if a.ISIN == nil || *a.ISIN != "US0378331005" {
			t.Errorf("unexpected ISIN in result: %v", a.ISIN)
		}
	}
}

func TestByISINUnknown(t *testing.T) {
	r := loadSample(t)
	res := r.ByISIN("US0000000000")
	if len(res) != 0 {
		t.Errorf("expected empty, got %d", len(res))
	}
}

func TestByISINCaseSensitive(t *testing.T) {
	r := loadSample(t)
	res := r.ByISIN("us0378331005")
	if len(res) != 0 {
		t.Errorf("expected empty for lowercase query, got %d", len(res))
	}
}

func TestByISINInsertionOrder(t *testing.T) {
	r := loadSample(t)
	ids := actionIDs(r.ByISIN("US0378331005"))
	want := []string{
		"US0378331005-DIVIDEND-2024-05-16-0.2500",
		"US0378331005-SPLIT-2020-08-31-4-1",
	}
	if !reflect.DeepEqual(ids, want) {
		t.Errorf("order mismatch: got %v, want %v", ids, want)
	}
}

func TestByISINFreshSlice(t *testing.T) {
	r := loadSample(t)
	first := r.ByISIN("US0378331005")
	first[0] = Action{} // clobber the returned slice
	second := r.ByISIN("US0378331005")
	if second[0].ActionID == nil {
		t.Error("registry state corrupted by mutating a returned slice")
	}
}

func TestByISINDeepCopy(t *testing.T) {
    r := loadSample(t)
    first := r.ByISIN("US0378331005")
    *first[0].Dates.ExDate = "1900-01-01"
    again := r.ByISIN("US0378331005")
    if *again[0].Dates.ExDate == "1900-01-01" {
        t.Errorf("registry state corrupted: got %s", *again[0].Dates.ExDate)
    }
}

// ----------------------------------------------------------------------
// ByActionID
// ----------------------------------------------------------------------

func TestByActionID(t *testing.T) {
	r := loadSample(t)
	a := r.ByActionID("US67066G1040-SPLIT-2024-06-10-10-1")
	if a == nil {
		t.Fatal("expected an action, got nil")
	}
	if a.Ratio == nil || *a.Ratio != "10:1" {
		t.Errorf("ratio: got %v, want \"10:1\"", a.Ratio)
	}
}

func TestByActionIDNotFound(t *testing.T) {
	r := loadSample(t)
	if a := r.ByActionID("NONEXISTENT"); a != nil {
		t.Errorf("expected nil, got %+v", a)
	}
}

func TestByActionIDFreshCopyTopLevel(t *testing.T) {
	r := loadSample(t)
	a := r.ByActionID("US67066G1040-SPLIT-2024-06-10-10-1")
	if a == nil {
		t.Fatal("expected an action, got nil")
	}
	newRatio := "999:1"
	a.Ratio = &newRatio
	again := r.ByActionID("US67066G1040-SPLIT-2024-06-10-10-1")
	if *again.Ratio != "10:1" {
		t.Errorf("top-level mutation leaked into registry: got %s", *again.Ratio)
	}
}

func TestByActionIDFreshCopyNestedDates(t *testing.T) {
	r := loadSample(t)
	a := r.ByActionID("US67066G1040-SPLIT-2024-06-10-10-1")
	if a == nil || a.Dates == nil {
		t.Fatal("expected an action with dates, got nil")
	}
	newDate := "1900-01-01"
	a.Dates.ExDate = &newDate
	again := r.ByActionID("US67066G1040-SPLIT-2024-06-10-10-1")
	if again.Dates == nil || again.Dates.ExDate == nil {
		t.Fatal("dates vanished after mutation")
	}
	if *again.Dates.ExDate != "2024-06-10" {
		t.Errorf("nested mutation leaked: got %s", *again.Dates.ExDate)
	}
}

func TestByActionIDFreshCopyNestedProvenance(t *testing.T) {
	r := loadSample(t)
	a := r.ByActionID("US0378331005-DIVIDEND-2024-05-16-0.2500")
	if a == nil || a.Provenance == nil {
		t.Fatal("expected an action with provenance, got nil")
	}
	newSource := "mutated"
	a.Provenance.Source = &newSource
	again := r.ByActionID("US0378331005-DIVIDEND-2024-05-16-0.2500")
	if again.Provenance == nil || again.Provenance.Source == nil {
		t.Fatal("provenance vanished after mutation")
	}
	if *again.Provenance.Source != "Apple" {
		t.Errorf("nested mutation leaked: got %s", *again.Provenance.Source)
	}
}

func TestByActionIDFreshCopyNestedImpact(t *testing.T) {
	r := loadSample(t)
	a := r.ByActionID("US0378331005-DIVIDEND-2024-05-16-0.2500")
	if a == nil || a.Impact == nil {
		t.Fatal("expected an action with impact, got nil")
	}
	newCash := 999.0
	a.Impact.CashAdjustment = &newCash
	again := r.ByActionID("US0378331005-DIVIDEND-2024-05-16-0.2500")
	if again.Impact == nil || again.Impact.CashAdjustment == nil {
		t.Fatal("impact vanished after mutation")
	}
	if *again.Impact.CashAdjustment != 0.25 {
		t.Errorf("nested mutation leaked: got %v", *again.Impact.CashAdjustment)
	}
}

func TestByActionIDReturnsDistinctPointers(t *testing.T) {
	r := loadSample(t)
	a := r.ByActionID("US67066G1040-SPLIT-2024-06-10-10-1")
	b := r.ByActionID("US67066G1040-SPLIT-2024-06-10-10-1")
	if a == b {
		t.Error("ByActionID returned the same pointer twice")
	}
}

// ----------------------------------------------------------------------
// ByActionType
// ----------------------------------------------------------------------

func TestByActionType(t *testing.T) {
	r := loadSample(t)
	splits := r.ByActionType("SPLIT")
	if len(splits) != 2 {
		t.Fatalf("len: got %d, want 2", len(splits))
	}
	for _, a := range splits {
		if a.ActionType == nil || *a.ActionType != "SPLIT" {
			t.Errorf("unexpected type in result: %v", a.ActionType)
		}
	}
}

func TestByActionTypeUnknown(t *testing.T) {
	r := loadSample(t)
	res := r.ByActionType("MERGER")
	if len(res) != 0 {
		t.Errorf("expected empty, got %d", len(res))
	}
}

func TestByActionTypeCaseSensitive(t *testing.T) {
	r := loadSample(t)
	res := r.ByActionType("split")
	if len(res) != 0 {
		t.Errorf("expected empty for lowercase query, got %d", len(res))
	}
}

func TestByActionTypeFreshSlice(t *testing.T) {
	r := loadSample(t)
	first := r.ByActionType("SPLIT")
	first[0] = Action{}
	second := r.ByActionType("SPLIT")
	if second[0].ActionID == nil {
		t.Error("registry state corrupted by mutating a returned slice")
	}
}

// ----------------------------------------------------------------------
// ByDateRange
// ----------------------------------------------------------------------

func TestByDateRangeDefaultField(t *testing.T) {
	r := loadSample(t)
	// With only two arguments the default field (ex_date) is used.
	got, err := r.ByDateRange("2024-01-01", "2024-12-31", "")
	if err == nil {
		t.Fatalf("empty dateField should be an error (use \"ex_date\" explicitly)")
	}
	_ = got
}

func TestByDateRangeExDate(t *testing.T) {
	r := loadSample(t)
	got, err := r.ByDateRange("2020-01-01", "2023-12-31", "ex_date")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	ids := actionIDs(got)
	want := []string{"US0378331005-SPLIT-2020-08-31-4-1"}
	if !reflect.DeepEqual(ids, want) {
		t.Errorf("got %v, want %v", ids, want)
	}
}

func TestByDateRangeEffectiveDate(t *testing.T) {
	r := loadSample(t)
	got, err := r.ByDateRange("2020-01-01", "2023-12-31", "effective_date")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("len: got %d, want 2", len(got))
	}
	ids := actionIDs(got)
	for _, want := range []string{
		"US0378331005-SPLIT-2020-08-31-4-1",
		"US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL",
	} {
		if !contains(ids, want) {
			t.Errorf("missing %s in result %v", want, ids)
		}
	}
}

func TestByDateRangeAnnouncement(t *testing.T) {
	r := loadSample(t)
	got, err := r.ByDateRange("2022-01-01", "2023-12-31", "announcement")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	ids := actionIDs(got)
	want := []string{"US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL"}
	if !reflect.DeepEqual(ids, want) {
		t.Errorf("got %v, want %v", ids, want)
	}
}

func TestByDateRangeRecordDate(t *testing.T) {
	r := loadSample(t)
	got, err := r.ByDateRange("2020-01-01", "2024-12-31", "record_date")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Three of the four actions have record_date; the SYMBOL_CHANGE does not.
	if len(got) != 3 {
		t.Errorf("len: got %d, want 3", len(got))
	}
}

func TestByDateRangeInvalidField(t *testing.T) {
	r := loadSample(t)
	cases := []string{
		"exdate", "ex-date", "effective", "Ex_Date", "EX_DATE",
		"ex_date ", " ex_date", "",
	}
	for _, bad := range cases {
		bad := bad
		t.Run(fmt.Sprintf("field_%q", bad), func(t *testing.T) {
			_, err := r.ByDateRange("", "", bad)
			if err == nil {
				t.Fatalf("expected error for field %q", bad)
			}
			if !errors.Is(err, ErrInvalidDateField) {
				t.Errorf("expected ErrInvalidDateField, got %v", err)
			}
		})
	}
}

func TestByDateRangeErrorNamesOffendingValue(t *testing.T) {
	r := loadSample(t)
	_, err := r.ByDateRange("", "", "exdate")
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !strings.Contains(err.Error(), "exdate") {
		t.Errorf("error does not name the offending value: %v", err)
	}
}

func TestByDateRangeInclusiveStartBound(t *testing.T) {
	r := loadSample(t)
	got, err := r.ByDateRange("2024-05-16", "2024-12-31", "ex_date")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	ids := actionIDs(got)
	if !contains(ids, "US0378331005-DIVIDEND-2024-05-16-0.2500") {
		t.Errorf("action on start bound missing: %v", ids)
	}
}

func TestByDateRangeInclusiveEndBound(t *testing.T) {
	r := loadSample(t)
	got, err := r.ByDateRange("2020-01-01", "2024-05-16", "ex_date")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	ids := actionIDs(got)
	if !contains(ids, "US0378331005-DIVIDEND-2024-05-16-0.2500") {
		t.Errorf("action on end bound missing: %v", ids)
	}
}

func TestByDateRangeSingleDay(t *testing.T) {
	r := loadSample(t)
	got, err := r.ByDateRange("2024-05-16", "2024-05-16", "ex_date")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	ids := actionIDs(got)
	want := []string{"US0378331005-DIVIDEND-2024-05-16-0.2500"}
	if !reflect.DeepEqual(ids, want) {
		t.Errorf("got %v, want %v", ids, want)
	}
}

func TestByDateRangeOpenStart(t *testing.T) {
	r := loadSample(t)
	got, err := r.ByDateRange("", "2024-01-01", "ex_date")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	ids := actionIDs(got)
	want := []string{"US0378331005-SPLIT-2020-08-31-4-1"}
	if !reflect.DeepEqual(ids, want) {
		t.Errorf("got %v, want %v", ids, want)
	}
}

func TestByDateRangeOpenEnd(t *testing.T) {
	r := loadSample(t)
	got, err := r.ByDateRange("2024-01-01", "", "ex_date")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 2 {
		t.Errorf("len: got %d, want 2", len(got))
	}
}

func TestByDateRangeBothOpen(t *testing.T) {
	r := loadSample(t)
	got, err := r.ByDateRange("", "", "ex_date")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Three of the four actions have an ex_date; SYMBOL_CHANGE does not.
	if len(got) != 3 {
		t.Errorf("len: got %d, want 3", len(got))
	}
}

func TestByDateRangeSkipsMissingExDate(t *testing.T) {
	r := loadSample(t)
	got, err := r.ByDateRange("", "", "ex_date")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	ids := actionIDs(got)
	if contains(ids, "US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL") {
		t.Errorf("SYMBOL_CHANGE should be skipped for ex_date: %v", ids)
	}
}

func TestByDateRangeSkipsMissingRecordDate(t *testing.T) {
	r := loadSample(t)
	got, err := r.ByDateRange("", "", "record_date")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	ids := actionIDs(got)
	if contains(ids, "US30303M1027-SYMBOL_CHANGE-2022-06-09-SYMBOL") {
		t.Errorf("SYMBOL_CHANGE should be skipped for record_date: %v", ids)
	}
}

func TestByDateRangeSortedByExDate(t *testing.T) {
	r := loadSample(t)
	got, err := r.ByDateRange("", "", "ex_date")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	dates := make([]string, len(got))
	for i, a := range got {
		if a.Dates != nil && a.Dates.ExDate != nil {
			dates[i] = *a.Dates.ExDate
		}
	}
	sorted := append([]string{}, dates...)
	sortStrings(sorted)
	if !reflect.DeepEqual(dates, sorted) {
		t.Errorf("not sorted: %v", dates)
	}
}

func TestByDateRangeSortedByEffectiveDate(t *testing.T) {
	r := loadSample(t)
	got, err := r.ByDateRange("", "", "effective_date")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	dates := make([]string, len(got))
	for i, a := range got {
		if a.Dates != nil && a.Dates.EffectiveDate != nil {
			dates[i] = *a.Dates.EffectiveDate
		}
	}
	sorted := append([]string{}, dates...)
	sortStrings(sorted)
	if !reflect.DeepEqual(dates, sorted) {
		t.Errorf("not sorted: %v", dates)
	}
}

func TestByDateRangeTiebreakOnActionID(t *testing.T) {
	r := loadTiebreak(t)
	got, err := r.ByDateRange("", "", "ex_date")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	ids := actionIDs(got)
	want := []string{
		"US0000000001-DIVIDEND-2024-05-16-0.2500",
		"US0000000002-DIVIDEND-2024-05-16-0.3000",
	}
	if !reflect.DeepEqual(ids, want) {
		t.Errorf("got %v, want %v", ids, want)
	}
}

func TestByDateRangeSortedRegardlessOfInputOrder(t *testing.T) {
	// Build a registry whose actions are in reverse order.
	reversed := reverseActionsInJSON(t, sampleJSON)
	r, err := FromJSON(reversed)
	if err != nil {
		t.Fatalf("FromJSON: %v", err)
	}
	got, err := r.ByDateRange("", "", "ex_date")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	dates := make([]string, len(got))
	for i, a := range got {
		if a.Dates != nil && a.Dates.ExDate != nil {
			dates[i] = *a.Dates.ExDate
		}
	}
	sorted := append([]string{}, dates...)
	sortStrings(sorted)
	if !reflect.DeepEqual(dates, sorted) {
		t.Errorf("not sorted after reversal: %v", dates)
	}
}

func TestByDateRangeReturnsFreshSlice(t *testing.T) {
	r := loadSample(t)
	first, err := r.ByDateRange("", "", "ex_date")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if first[0].Dates == nil || first[0].Dates.ExDate == nil {
		t.Fatal("first action has no Dates.ExDate")
	}
	newDate := "1900-01-01"
	first[0].Dates.ExDate = &newDate

	second, err := r.ByDateRange("", "", "ex_date")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if second[0].Dates.ExDate != nil && *second[0].Dates.ExDate == "1900-01-01" {
		t.Fatal("ByDateRange result aliases internal state")
	}
}

// ----------------------------------------------------------------------
// AllActionTypes
// ----------------------------------------------------------------------

func TestAllActionTypes(t *testing.T) {
	r := loadSample(t)
	types := r.AllActionTypes()
	want := []string{"DIVIDEND", "SPLIT", "SYMBOL_CHANGE"}
	if !reflect.DeepEqual(types, want) {
		t.Errorf("got %v, want %v", types, want)
	}
}

func TestAllActionTypesEmpty(t *testing.T) {
	r, err := FromJSON([]byte(`{"actions":[]}`))
	if err != nil {
		t.Fatalf("FromJSON: %v", err)
	}
	if got := r.AllActionTypes(); len(got) != 0 {
		t.Errorf("expected empty, got %v", got)
	}
}

func TestAllActionTypesReflectsOnlyPresentTypes(t *testing.T) {
	r := loadSample(t)
	types := r.AllActionTypes()
	for _, t2 := range []string{"MERGER", "SPINOFF", "REVERSE_SPLIT"} {
		if contains(types, t2) {
			t.Errorf("%s should not appear: %v", t2, types)
		}
	}
}

// ----------------------------------------------------------------------
// Count
// ----------------------------------------------------------------------

func TestCount(t *testing.T) {
	r := loadSample(t)
	if r.Count() != 4 {
		t.Errorf("got %d, want 4", r.Count())
	}
}

func TestCountEmpty(t *testing.T) {
	r, err := FromJSON([]byte(`{"actions":[]}`))
	if err != nil {
		t.Fatalf("FromJSON: %v", err)
	}
	if r.Count() != 0 {
		t.Errorf("got %d, want 0", r.Count())
	}
}

// ----------------------------------------------------------------------
// Meta
// ----------------------------------------------------------------------

func TestMeta(t *testing.T) {
	r := loadSample(t)
	m := r.Meta()
	if m.Version == nil || *m.Version != "1.0.0" {
		t.Errorf("Version: got %v, want 1.0.0", m.Version)
	}
	if m.Source == nil || *m.Source != "Test" {
		t.Errorf("Source: got %v, want Test", m.Source)
	}
}

func TestMetaReturnsFreshPointer(t *testing.T) {
	r := loadSample(t)
	a := r.Meta()
	b := r.Meta()
	if a == b {
		t.Error("Meta() returned the same pointer twice; expected a copy each call")
	}
}

// ----------------------------------------------------------------------
// ToJSON / Save
// ----------------------------------------------------------------------

func TestToJSONShape(t *testing.T) {
	r := loadSample(t)
	data, err := r.ToJSON()
	if err != nil {
		t.Fatalf("ToJSON: %v", err)
	}
	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("output is not valid JSON: %v", err)
	}
	if len(raw) != 2 {
		t.Errorf("expected exactly two top-level keys, got %d: %v", len(raw), keys(raw))
	}
	if _, ok := raw["meta"]; !ok {
		t.Error("missing 'meta' key")
	}
	actions, ok := raw["actions"].([]interface{})
	if !ok || len(actions) != 4 {
		t.Errorf("actions: got %v, want array of 4", raw["actions"])
	}
}

func TestToJSONNoBOM(t *testing.T) {
	r := loadSample(t)
	data, err := r.ToJSON()
	if err != nil {
		t.Fatalf("ToJSON: %v", err)
	}
	if len(data) >= 3 && data[0] == 0xEF && data[1] == 0xBB && data[2] == 0xBF {
		t.Error("ToJSON output carries a UTF-8 BOM")
	}
}

func TestToJSONPreservesFields(t *testing.T) {
	r := loadSample(t)
	data, err := r.ToJSON()
	if err != nil {
		t.Fatalf("ToJSON: %v", err)
	}
	var doc struct {
		Meta struct {
			Version string `json:"version"`
			Source  string `json:"source"`
		} `json:"meta"`
		Actions []struct {
			ActionID string `json:"action_id"`
			ISIN     string `json:"isin"`
		} `json:"actions"`
	}
	if err := json.Unmarshal(data, &doc); err != nil {
		t.Fatalf("unmarshal round-trip: %v", err)
	}
	if doc.Meta.Version != "1.0.0" {
		t.Errorf("meta.version: got %q", doc.Meta.Version)
	}
	if doc.Meta.Source != "Test" {
		t.Errorf("meta.source: got %q", doc.Meta.Source)
	}
	if doc.Actions[0].ISIN != "US67066G1040" {
		t.Errorf("first action isin: got %q", doc.Actions[0].ISIN)
	}
}

func TestSaveAndReload(t *testing.T) {
	r := loadSample(t)
	dir := t.TempDir()
	path := filepath.Join(dir, "out.json")
	if err := r.Save(path); err != nil {
		t.Fatalf("Save: %v", err)
	}
	loaded, err := LoadRegistry(path)
	if err != nil {
		t.Fatalf("reload: %v", err)
	}
	if loaded.Count() != r.Count() {
		t.Errorf("count after reload: got %d, want %d", loaded.Count(), r.Count())
	}
	if *loaded.Meta().Version != *r.Meta().Version {
		t.Errorf("meta.version after reload: got %q", *loaded.Meta().Version)
	}
}

func TestSaveProducesValidJSON(t *testing.T) {
	r := loadSample(t)
	dir := t.TempDir()
	path := filepath.Join(dir, "out.json")
	if err := r.Save(path); err != nil {
		t.Fatalf("Save: %v", err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read saved file: %v", err)
	}
	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("saved file is not valid JSON: %v", err)
	}
}

func TestSaveNoBOM(t *testing.T) {
	r := loadSample(t)
	dir := t.TempDir()
	path := filepath.Join(dir, "out.json")
	if err := r.Save(path); err != nil {
		t.Fatalf("Save: %v", err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read saved file: %v", err)
	}
	if len(data) >= 3 && data[0] == 0xEF && data[1] == 0xBB && data[2] == 0xBF {
		t.Error("saved file carries a UTF-8 BOM")
	}
}

func TestSaveEmptyRegistry(t *testing.T) {
	r, err := FromJSON([]byte(`{"meta":{},"actions":[]}`))
	if err != nil {
		t.Fatalf("FromJSON: %v", err)
	}
	dir := t.TempDir()
	path := filepath.Join(dir, "empty.json")
	if err := r.Save(path); err != nil {
		t.Fatalf("Save: %v", err)
	}
	loaded, err := LoadRegistry(path)
	if err != nil {
		t.Fatalf("reload: %v", err)
	}
	if loaded.Count() != 0 {
		t.Errorf("count after reload: got %d, want 0", loaded.Count())
	}
}

func TestSaveTwoCallsProduceIdenticalOutput(t *testing.T) {
	r := loadSample(t)
	dir := t.TempDir()
	p1 := filepath.Join(dir, "a.json")
	p2 := filepath.Join(dir, "b.json")
	if err := r.Save(p1); err != nil {
		t.Fatalf("Save 1: %v", err)
	}
	if err := r.Save(p2); err != nil {
		t.Fatalf("Save 2: %v", err)
	}
	b1, err := os.ReadFile(p1)
	if err != nil {
		t.Fatalf("read p1: %v", err)
	}
	b2, err := os.ReadFile(p2)
	if err != nil {
		t.Fatalf("read p2: %v", err)
	}
	if !reflect.DeepEqual(b1, b2) {
		t.Error("two Save calls produced different output")
	}
}

// ----------------------------------------------------------------------
// Test-only helpers
// ----------------------------------------------------------------------

// contains reports whether s contains needle.
func contains(s []string, needle string) bool {
	for _, x := range s {
		if x == needle {
			return true
		}
	}
	return false
}

// sortStrings sorts in place, avoiding an import of sort for two tests.
func sortStrings(s []string) {
	for i := 1; i < len(s); i++ {
		for j := i; j > 0 && s[j-1] > s[j]; j-- {
			s[j-1], s[j] = s[j], s[j-1]
		}
	}
}

// keys returns the keys of a map, for diagnostic output.
func keys(m map[string]interface{}) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	return out
}

// reverseActionsInJSON parses a top-level JSON document, reverses the
// "actions" array, and returns the re-marshaled bytes. Used to test that
// ByDateRange sorts regardless of input order.
func reverseActionsInJSON(t *testing.T, doc string) []byte {
	t.Helper()
	var raw struct {
		Meta    json.RawMessage   `json:"meta"`
		Actions []json.RawMessage `json:"actions"`
	}
	if err := json.Unmarshal([]byte(doc), &raw); err != nil {
		t.Fatalf("reverseActionsInJSON: %v", err)
	}
	for i, j := 0, len(raw.Actions)-1; i < j; i, j = i+1, j-1 {
		raw.Actions[i], raw.Actions[j] = raw.Actions[j], raw.Actions[i]
	}
	out, err := json.Marshal(raw)
	if err != nil {
		t.Fatalf("reverseActionsInJSON marshal: %v", err)
	}
	return out
}

func TestDefaultDateField(t *testing.T) {
	if DefaultDateField != "ex_date" {
		t.Fatalf("DefaultDateField = %q, want %q", DefaultDateField, "ex_date")
	}
}

func TestValidDateFieldsMatchContract(t *testing.T) {
	want := []string{"announcement", "ex_date", "record_date", "effective_date"}
	if len(ValidDateFields) != len(want) {
		t.Fatalf("len = %d, want %d", len(ValidDateFields), len(want))
	}
	for i, w := range want {
		if ValidDateFields[i] != w {
			t.Fatalf("ValidDateFields[%d] = %q, want %q", i, ValidDateFields[i], w)
		}
	}
}

func TestDuplicateActionIDRaises(t *testing.T) {
	doc := []byte(`{"actions":[
		{"isin":"X","action_id":"A","action_type":"SPLIT"},
		{"isin":"Y","action_id":"A","action_type":"SPLIT"}
	]}`)
	_, err := FromJSON(doc)
	if err == nil {
		t.Fatal("expected error for duplicate action_id")
	}
	if !strings.Contains(err.Error(), "duplicate action_id") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestMissingIdentifierRaises(t *testing.T) {
	doc := []byte(`{"actions":[{"action_type":"SPLIT"}]}`)
	_, err := FromJSON(doc)
	if err == nil {
		t.Fatal("expected error for missing identifier")
	}
	if !strings.Contains(err.Error(), "neither") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestByTickerResolves(t *testing.T) {
	ResetTickerIndexCache()
	path := filepath.Join("..", "..", "..", "tests", "fixtures", "identifiers.json")
	if _, err := os.Stat(path); err != nil {
		t.Skip("fixture missing")
	}
	doc := []byte(`{"actions":[{"isin":"US0000000002","action_id":"X","action_type":"DIVIDEND"}]}`)
	r, err := FromJSON(doc)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	got, err := r.ByTicker("TESTB", "XNAS", path)
	if err != nil {
		t.Fatalf("ByTicker: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("ByTicker returned %d actions, want 1", len(got))
	}
	if got[0].ISIN == nil || *got[0].ISIN != "US0000000002" {
		t.Fatalf("ByTicker returned wrong ISIN: %v", got[0].ISIN)
	}
}

func TestByTickerCaseInsensitive(t *testing.T) {
	ResetTickerIndexCache()
	path := filepath.Join("..", "..", "..", "tests", "fixtures", "identifiers.json")
	if _, err := os.Stat(path); err != nil {
		t.Skip("fixture missing")
	}
	r, _ := FromJSON([]byte(`{"actions":[]}`))
	lower, err := r.ByTicker("testb", "xnas", path)
	if err != nil {
		t.Fatalf("lower: %v", err)
	}
	upper, err := r.ByTicker("TESTB", "XNAS", path)
	if err != nil {
		t.Fatalf("upper: %v", err)
	}
	if len(lower) != len(upper) {
		t.Fatalf("case handling diverges: %d vs %d", len(lower), len(upper))
	}
}

func TestByTickerUnknownReturnsEmpty(t *testing.T) {
	ResetTickerIndexCache()
	path := filepath.Join("..", "..", "..", "tests", "fixtures", "identifiers.json")
	if _, err := os.Stat(path); err != nil {
		t.Skip("fixture missing")
	}
	r, _ := FromJSON([]byte(`{"actions":[]}`))
	got, err := r.ByTicker("NOTREAL", "XNAS", path)
	if err != nil {
		t.Fatalf("ByTicker: %v", err)
	}
	if len(got) != 0 {
		t.Fatalf("expected empty, got %d", len(got))
	}
}

func TestByTickerUnknownExchangeReturnsEmpty(t *testing.T) {
	ResetTickerIndexCache()
	path := filepath.Join("..", "..", "..", "tests", "fixtures", "identifiers.json")
	if _, err := os.Stat(path); err != nil {
		t.Skip("fixture missing")
	}
	r, _ := FromJSON([]byte(`{"actions":[]}`))
	got, err := r.ByTicker("TESTB", "NOTEXCH", path)
	if err != nil {
		t.Fatalf("ByTicker: %v", err)
	}
	if len(got) != 0 {
		t.Fatalf("expected empty, got %d", len(got))
	}
}

func TestByTickerMissingFileReturnsMissingData(t *testing.T) {
	ResetTickerIndexCache()
	r, _ := FromJSON([]byte(`{"actions":[]}`))
	_, err := r.ByTicker("TESTB", "XNAS", "/nonexistent/identifiers.json")
	if err == nil {
		t.Fatal("expected error for missing identifiers file")
	}
	if !strings.Contains(err.Error(), "missing identifier data") {
		t.Fatalf("unexpected error: %v", err)
	}
}