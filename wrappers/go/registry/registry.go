// Package registry provides a typed interface to the Corporate Actions Registry.
//
// It loads actions.json and builds in-memory indexes for fast lookups by
// ISIN, action ID, and action type, along with date range filtering.
package registry

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
)

// Dates contains the announcement, ex, record, and effective dates of a
// corporate action. All fields are optional.
type Dates struct {
	Announcement   *string `json:"announcement,omitempty"`
	ExDate         *string `json:"ex_date,omitempty"`
	RecordDate     *string `json:"record_date,omitempty"`
	EffectiveDate  *string `json:"effective_date,omitempty"`
}

// Provenance contains source and verification information for an action.
type Provenance struct {
	Source             *string `json:"source,omitempty"`
	SourceURL          *string `json:"source_url,omitempty"`
	VerificationSource *string `json:"verification_source,omitempty"`
	VerificationURL    *string `json:"verification_url,omitempty"`
}

// Impact contains financial impact multipliers for backtesting.
type Impact struct {
	PriceMultiplier *float64 `json:"price_multiplier,omitempty"`
	ShareMultiplier *float64 `json:"share_multiplier,omitempty"`
	CashAdjustment  *float64 `json:"cash_adjustment,omitempty"`
}

// Action represents a single corporate action entry.
type Action struct {
	ISIN        *string      `json:"isin,omitempty"`
	ActionID    *string      `json:"action_id,omitempty"`
	ActionType  *string      `json:"action_type,omitempty"`
	Ratio       *string      `json:"ratio,omitempty"`
	Amount      *float64     `json:"amount,omitempty"`
	Currency    *string      `json:"currency,omitempty"`
	Dates       *Dates       `json:"dates,omitempty"`
	Status      *string      `json:"status,omitempty"`
	Provenance  *Provenance  `json:"provenance,omitempty"`
	Impact      *Impact      `json:"impact,omitempty"`
}

// Meta contains metadata about the registry file.
type Meta struct {
	Version     *string `json:"version,omitempty"`
	GeneratedAt *string `json:"generated_at,omitempty"`
	Source      *string `json:"source,omitempty"`
	Notes       *string `json:"notes,omitempty"`
}

// Registry is the main container for all corporate actions.
type Registry struct {
	meta    Meta
	actions []Action

	// Indexes (map key -> indices in actions slice)
	indexISIN   map[string][]int
	indexType   map[string][]int
	indexID     map[string]int
}

// LoadRegistry loads the registry from a JSON file.
func LoadRegistry(path string) (*Registry, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading registry file: %w", err)
	}
	return FromJSON(data)
}

// FromJSON parses the registry from raw JSON bytes.
// The JSON must have the structure:
//
//	{
//	  "meta": { ... },
//	  "actions": [ ... ]
//	}
func FromJSON(data []byte) (*Registry, error) {
	var raw struct {
		Meta    Meta     `json:"meta"`
		Actions []Action `json:"actions"`
	}
	if err := json.Unmarshal(data, &raw); err != nil {
		return nil, fmt.Errorf("parsing registry JSON: %w", err)
	}

	r := &Registry{
		meta:      raw.Meta,
		actions:   raw.Actions,
		indexISIN: make(map[string][]int),
		indexType: make(map[string][]int),
		indexID:   make(map[string]int),
	}

	// Build indexes
	for i, action := range r.actions {
		if action.ISIN != nil {
			isin := *action.ISIN
			r.indexISIN[isin] = append(r.indexISIN[isin], i)
		}
		if action.ActionType != nil {
			typ := *action.ActionType
			r.indexType[typ] = append(r.indexType[typ], i)
		}
		if action.ActionID != nil {
			r.indexID[*action.ActionID] = i
		}
	}
	return r, nil
}

// ByISIN returns all actions for the given ISIN.
func (r *Registry) ByISIN(isin string) []Action {
	indices, ok := r.indexISIN[isin]
	if !ok {
		return nil
	}
	result := make([]Action, len(indices))
	for i, idx := range indices {
		result[i] = r.actions[idx]
	}
	return result
}

// ByActionID returns a single action by its unique action_id, or nil if not found.
func (r *Registry) ByActionID(actionID string) *Action {
	idx, ok := r.indexID[actionID]
	if !ok {
		return nil
	}
	action := r.actions[idx]
	return &action
}

// ByActionType returns all actions of a given type (e.g., "SPLIT", "DIVIDEND").
func (r *Registry) ByActionType(actionType string) []Action {
	indices, ok := r.indexType[actionType]
	if !ok {
		return nil
	}
	result := make([]Action, len(indices))
	for i, idx := range indices {
		result[i] = r.actions[idx]
	}
	return result
}

// ByDateRange filters actions by a date range on a specified date field.
// The date field can be "announcement", "ex_date", "record_date", or
// "effective_date". Dates are compared lexicographically (YYYY-MM-DD).
// startDate and endDate are optional (empty string means no bound).
func (r *Registry) ByDateRange(startDate, endDate, dateField string) []Action {
	var result []Action
	for _, action := range r.actions {
		if action.Dates == nil {
			continue
		}
		var dateValue *string
		switch dateField {
		case "announcement":
			dateValue = action.Dates.Announcement
		case "ex_date":
			dateValue = action.Dates.ExDate
		case "record_date":
			dateValue = action.Dates.RecordDate
		case "effective_date":
			dateValue = action.Dates.EffectiveDate
		default:
			return nil // invalid field
		}
		if dateValue == nil {
			continue
		}
		d := *dateValue
		if startDate != "" && d < startDate {
			continue
		}
		if endDate != "" && d > endDate {
			continue
		}
		result = append(result, action)
	}
	return result
}

// AllActionTypes returns a sorted list of all unique action types.
func (r *Registry) AllActionTypes() []string {
	types := make([]string, 0, len(r.indexType))
	for t := range r.indexType {
		types = append(types, t)
	}
	sort.Strings(types)
	return types
}

// Count returns the total number of actions.
func (r *Registry) Count() int {
	return len(r.actions)
}

// Meta returns a reference to the registry metadata.
func (r *Registry) Meta() *Meta {
	return &r.meta
}

// ToJSON marshals the registry back to a JSON representation.
func (r *Registry) ToJSON() ([]byte, error) {
	return json.MarshalIndent(struct {
		Meta    Meta     `json:"meta"`
		Actions []Action `json:"actions"`
	}{
		Meta:    r.meta,
		Actions: r.actions,
	}, "", "  ")
}

// Save writes the registry to a file.
func (r *Registry) Save(path string) error {
	data, err := r.ToJSON()
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}