package registry

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// sampleJSON is a representative actions.json content for tests.
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
      "action_id": "US67066G1040-SPLIT-2024-06-10-0001",
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
      "action_id": "US0378331005-DIVIDEND-2024-05-16-0002",
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
      "action_id": "US0378331005-SPLIT-2020-08-31-0003",
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
      "action_id": "US30303M1027-SYMBOL_CHANGE-2022-06-09-0004",
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

// helper to create a temp file with sampleJSON
func createTempSample(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "actions.json")
	if err := os.WriteFile(path, []byte(sampleJSON), 0644); err != nil {
		t.Fatalf("failed to write temp file: %v", err)
	}
	return path
}

// helper to load registry from sampleJSON directly
func loadSample(t *testing.T) *Registry {
	t.Helper()
	r, err := FromJSON([]byte(sampleJSON))
	if err != nil {
		t.Fatalf("FromJSON failed: %v", err)
	}
	return r
}

func TestLoadFromFile(t *testing.T) {
	path := createTempSample(t)
	r, err := LoadRegistry(path)
	if err != nil {
		t.Fatalf("LoadRegistry failed: %v", err)
	}
	if r.Count() != 4 {
		t.Errorf("expected count 4, got %d", r.Count())
	}
	if r.Meta().Version == nil || *r.Meta().Version != "1.0.0" {
		t.Errorf("meta version not loaded correctly")
	}
}

func TestLoadFromFileMissing(t *testing.T) {
	_, err := LoadRegistry("/nonexistent/path/actions.json")
	if err == nil {
		t.Error("expected error for missing file, got nil")
	}
}

func TestFromJSONInvalid(t *testing.T) {
	_, err := FromJSON([]byte("not valid json"))
	if err == nil {
		t.Error("expected error for invalid JSON, got nil")
	}
}

func TestFromJSONMissingActions(t *testing.T) {
	_, err := FromJSON([]byte(`{"meta":{"version":"1.0.0"}}`))
	if err != nil {
		t.Errorf("unexpected error for missing actions: %v", err)
	}
	// JSON unmarshal will set Actions as nil, not error.
	// Our code doesn't error on missing actions; it just builds empty indexes.
	// We can test that a registry with nil actions behaves.
}

func TestByISIN(t *testing.T) {
	r := loadSample(t)
	aapl := r.ByISIN("US0378331005")
	if len(aapl) != 2 {
		t.Fatalf("expected 2 actions for AAPL, got %d", len(aapl))
	}
	for _, a := range aapl {
		if a.ISIN == nil || *a.ISIN != "US0378331005" {
			t.Error("ISIN mismatch in result")
		}
	}
}

func TestByISINUnknown(t *testing.T) {
	r := loadSample(t)
	res := r.ByISIN("US0000000000")
	if len(res) != 0 {
		t.Errorf("expected empty slice for unknown ISIN, got %d", len(res))
	}
}

func TestByActionID(t *testing.T) {
	r := loadSample(t)
	action := r.ByActionID("US67066G1040-SPLIT-2024-06-10-0001")
	if action == nil {
		t.Fatal("expected action, got nil")
	}
	if action.Ratio == nil || *action.Ratio != "10:1" {
		t.Errorf("ratio not correct")
	}
}

func TestByActionIDNotFound(t *testing.T) {
	r := loadSample(t)
	action := r.ByActionID("NONEXISTENT")
	if action != nil {
		t.Error("expected nil for unknown action ID")
	}
}

func TestByActionType(t *testing.T) {
	r := loadSample(t)
	splits := r.ByActionType("SPLIT")
	if len(splits) != 2 {
		t.Fatalf("expected 2 splits, got %d", len(splits))
	}
	for _, a := range splits {
		if a.ActionType == nil || *a.ActionType != "SPLIT" {
			t.Error("action type mismatch")
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

func TestByDateRangeExDate(t *testing.T) {
	r := loadSample(t)
	actions := r.ByDateRange("2020-01-01", "2023-12-31", "ex_date")
	if len(actions) != 1 {
		t.Fatalf("expected 1 action in range, got %d", len(actions))
	}
	if actions[0].ActionID == nil || *actions[0].ActionID != "US0378331005-SPLIT-2020-08-31-0003" {
		t.Errorf("unexpected action returned")
	}
}

func TestByDateRangeEffectiveDate(t *testing.T) {
	r := loadSample(t)
	actions := r.ByDateRange("2024-01-01", "2024-12-31", "effective_date")
	if len(actions) != 2 {
		t.Fatalf("expected 2 actions, got %d", len(actions))
	}
}

func TestByDateRangeInvalidField(t *testing.T) {
	r := loadSample(t)
	actions := r.ByDateRange("", "", "invalid")
	if len(actions) != 0 {
		t.Errorf("expected 0 for invalid field, got %d", len(actions))
	}
}

func TestAllActionTypes(t *testing.T) {
	r := loadSample(t)
	types := r.AllActionTypes()
	expected := []string{"DIVIDEND", "SPLIT", "SYMBOL_CHANGE"}
	if len(types) != len(expected) {
		t.Fatalf("expected %d types, got %d", len(expected), len(types))
	}
	for i := range expected {
		if types[i] != expected[i] {
			t.Errorf("type order mismatch at index %d: got %s, want %s", i, types[i], expected[i])
		}
	}
}

func TestCount(t *testing.T) {
	r := loadSample(t)
	if r.Count() != 4 {
		t.Errorf("expected count 4, got %d", r.Count())
	}
}

func TestToJSONRoundTrip(t *testing.T) {
	r := loadSample(t)
	data, err := r.ToJSON()
	if err != nil {
		t.Fatalf("ToJSON failed: %v", err)
	}
	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("failed to unmarshal ToJSON output: %v", err)
	}
	actions, ok := raw["actions"].([]interface{})
	if !ok || len(actions) != 4 {
		t.Errorf("ToJSON did not preserve actions")
	}
}

func TestSaveAndReload(t *testing.T) {
	r := loadSample(t)
	dir := t.TempDir()
	path := filepath.Join(dir, "out.json")
	if err := r.Save(path); err != nil {
		t.Fatalf("Save failed: %v", err)
	}
	loaded, err := LoadRegistry(path)
	if err != nil {
		t.Fatalf("reload failed: %v", err)
	}
	if loaded.Count() != r.Count() {
		t.Errorf("count mismatch after reload")
	}
	if *loaded.Meta().Version != *r.Meta().Version {
		t.Errorf("meta version mismatch")
	}
}