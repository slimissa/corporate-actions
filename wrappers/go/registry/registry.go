// Package registry provides a typed interface to the Corporate Actions Registry.
//
// It loads actions.json and builds in-memory indexes for fast lookups by
// ISIN, action ID, and action type, along with date range filtering.
//
// The behaviour of every method in this package is specified by
// docs/wrapper_contract.md. When the code disagrees with that document,
// the code is wrong.
package registry

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"sort"
)

// ErrInvalidDateField is returned by ByDateRange when the requested date
// field name is not one of the four valid values.
var ErrInvalidDateField = errors.New("invalid date_field")

// validDateFields is the closed set of date field names accepted by
// ByDateRange. Kept as a map for O(1) lookup.
var validDateFields = map[string]bool{
	"announcement":   true,
	"ex_date":        true,
	"record_date":    true,
	"effective_date": true,
}

// Dates contains the announcement, ex, record, and effective dates of a
// corporate action. All fields are optional.
type Dates struct {
	Announcement  *string `json:"announcement,omitempty"`
	ExDate        *string `json:"ex_date,omitempty"`
	RecordDate    *string `json:"record_date,omitempty"`
	EffectiveDate *string `json:"effective_date,omitempty"`
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
	ISIN       *string     `json:"isin,omitempty"`
	ActionID   *string     `json:"action_id,omitempty"`
	ActionType *string     `json:"action_type,omitempty"`
	Ratio      *string     `json:"ratio,omitempty"`
	Amount     *float64    `json:"amount,omitempty"`
	Currency   *string     `json:"currency,omitempty"`
	Dates      *Dates      `json:"dates,omitempty"`
	Status     *string     `json:"status,omitempty"`
	Provenance *Provenance `json:"provenance,omitempty"`
	Impact     *Impact     `json:"impact,omitempty"`
}

// Meta contains metadata about the registry file.
type Meta struct {
	Version     *string `json:"version,omitempty"`
	GeneratedAt *string `json:"generated_at,omitempty"`
	Source      *string `json:"source,omitempty"`
	Notes       *string `json:"notes,omitempty"`
}

// Registry is the main container for all corporate actions.
//
// A Registry is immutable after construction. All lookup methods return
// fresh slices or freshly-allocated pointers, so a caller cannot corrupt
// the registry's internal state by mutating a returned value.
type Registry struct {
	meta    Meta
	actions []Action

	// Indexes. Each maps a key to one or more positions in `actions`.
	// Positions are stable for the lifetime of the Registry.
	indexISIN map[string][]int
	indexType map[string][]int
	indexID   map[string]int
}

// LoadRegistry loads the registry from a JSON file.
//
// A UTF-8 BOM at the start of the file is ignored. Any other leading
// bytes are passed through to json.Unmarshal.
func LoadRegistry(path string) (*Registry, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading registry file: %w", err)
	}
	return FromJSON(data)
}

// FromJSON parses the registry from raw JSON bytes.
//
// The document must be an object with an "actions" array. The "meta"
// object is optional. Each entry in "actions" must itself be a JSON
// object; a string, number, boolean, null, or array entry is a
// structural error, reported with its index.
//
// A UTF-8 BOM prefix is stripped before parsing.
func FromJSON(data []byte) (*Registry, error) {
	data = bytes.TrimPrefix(data, []byte{0xEF, 0xBB, 0xBF})

	// Decode the actions array into raw messages first so each entry can
	// be inspected before it is unmarshaled into an Action. This is the
	// only way to distinguish a JSON object from a JSON array, string,
	// number, boolean, or null inside the array.
	var raw struct {
		Meta    *Meta              `json:"meta"`
		Actions *[]json.RawMessage `json:"actions"`
	}
	if err := json.Unmarshal(data, &raw); err != nil {
		return nil, fmt.Errorf("parsing registry JSON: %w", err)
	}
	if raw.Actions == nil {
		return nil, fmt.Errorf("parsing registry JSON: missing 'actions' key")
	}

	actions := make([]Action, len(*raw.Actions))
	for i, item := range *raw.Actions {
		trimmed := bytes.TrimSpace(item)
		if len(trimmed) == 0 || trimmed[0] != '{' {
			return nil, fmt.Errorf(
				"parsing registry JSON: action at index %d is not an object",
				i,
			)
		}
		if err := json.Unmarshal(item, &actions[i]); err != nil {
			return nil, fmt.Errorf(
				"parsing registry JSON: action at index %d: %w",
				i, err,
			)
		}
	}

	meta := Meta{}
	if raw.Meta != nil {
		meta = *raw.Meta
	}

	r := &Registry{
		meta:      meta,
		actions:   actions,
		indexISIN: make(map[string][]int),
		indexType: make(map[string][]int),
		indexID:   make(map[string]int),
	}

	for i, action := range r.actions {
		if action.ISIN != nil {
			r.indexISIN[*action.ISIN] = append(r.indexISIN[*action.ISIN], i)
		}
		if action.ActionType != nil {
			r.indexType[*action.ActionType] = append(r.indexType[*action.ActionType], i)
		}
		if action.ActionID != nil {
			// Last one wins. Duplicate action_id values are a data error
			// caught by the validator's uniqueness layer; the loader does
			// not check.
			r.indexID[*action.ActionID] = i
		}
	}

	return r, nil
}

// ByISIN returns all actions for the given ISIN.
//
// Returns an empty slice when no action matches. Matching is exact and
// case-sensitive.
//
// The returned slice is fresh: mutating it does not affect the registry.
func (r *Registry) ByISIN(isin string) []Action {
	indices, ok := r.indexISIN[isin]
	if !ok {
		return []Action{}
	}
	result := make([]Action, len(indices))
	for i, idx := range indices {
		result[i] = r.actions[idx]
	}
	return result
}

// ByActionID returns a single action by its unique action_id, or nil if
// no action matches. Matching is exact and case-sensitive.
//
// The returned pointer refers to a freshly-allocated copy; mutating the
// pointed-to Action does not affect the registry.
func (r *Registry) ByActionID(actionID string) *Action {
	idx, ok := r.indexID[actionID]
	if !ok {
		return nil
	}
	src := r.actions[idx]
	// Copy the top-level struct; this copies the pointers to the nested
	// structs. Deep-copy those so a caller who mutates a nested field
	// does not reach the registry's internal state. Matches the deep-copy
	// contract in docs/wrapper_contract.md section 4.2.
	dst := src
	if src.Dates != nil {
		d := *src.Dates
		dst.Dates = &d
	}
	if src.Provenance != nil {
		p := *src.Provenance
		dst.Provenance = &p
	}
	if src.Impact != nil {
		i := *src.Impact
		dst.Impact = &i
	}
	return &dst
}

// ByActionType returns all actions of a given type (e.g., "SPLIT",
// "DIVIDEND"). Matching is exact and case-sensitive.
//
// The returned slice is fresh: mutating it does not affect the registry.
func (r *Registry) ByActionType(actionType string) []Action {
	indices, ok := r.indexType[actionType]
	if !ok {
		return []Action{}
	}
	result := make([]Action, len(indices))
	for i, idx := range indices {
		result[i] = r.actions[idx]
	}
	return result
}

// ByDateRange returns actions whose dateField falls in the inclusive
// range [startDate, endDate].
//
// dateField must be one of "announcement", "ex_date", "record_date", or
// "effective_date". Any other value returns ErrInvalidDateField.
//
// An empty startDate or endDate means "no bound on that side". Actions
// whose dateField is absent (or whose dates object is nil) are silently
// skipped. Dates are compared as ISO-8601 strings, so lexicographic
// comparison is chronological.
//
// The result is sorted by (dateField, action_id), ascending.
func (r *Registry) ByDateRange(startDate, endDate, dateField string) ([]Action, error) {
	if !validDateFields[dateField] {
		return nil, fmt.Errorf("%w: %s", ErrInvalidDateField, dateField)
	}

	dateValue := func(a Action) string {
		if a.Dates == nil {
			return ""
		}
		switch dateField {
		case "announcement":
			if a.Dates.Announcement != nil {
				return *a.Dates.Announcement
			}
		case "ex_date":
			if a.Dates.ExDate != nil {
				return *a.Dates.ExDate
			}
		case "record_date":
			if a.Dates.RecordDate != nil {
				return *a.Dates.RecordDate
			}
		case "effective_date":
			if a.Dates.EffectiveDate != nil {
				return *a.Dates.EffectiveDate
			}
		}
		return ""
	}

	result := make([]Action, 0)
	for _, action := range r.actions {
		v := dateValue(action)
		if v == "" {
			continue
		}
		if startDate != "" && v < startDate {
			continue
		}
		if endDate != "" && v > endDate {
			continue
		}
		result = append(result, action)
	}

	sort.Slice(result, func(i, j int) bool {
		vi, vj := dateValue(result[i]), dateValue(result[j])
		if vi != vj {
			return vi < vj
		}
		var ai, aj string
		if result[i].ActionID != nil {
			ai = *result[i].ActionID
		}
		if result[j].ActionID != nil {
			aj = *result[j].ActionID
		}
		return ai < aj
	})

	return result, nil
}

// AllActionTypes returns a sorted list of all unique action types present
// in the registry. Reserved types that are not present in the data do not
// appear. The result is empty for an empty registry.
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

// Meta returns a pointer to the registry metadata. The metadata is a
// value type, so the pointer refers to a copy; mutating the fields of
// the returned Meta through their own pointers still reaches the shared
// strings, matching the behaviour of the Python and JavaScript wrappers.
func (r *Registry) Meta() *Meta {
	m := r.meta
	return &m
}

// ToJSON marshals the registry back to a JSON representation with
// exactly two top-level keys: "meta" and "actions".
//
// The output is indented with two spaces and carries no BOM.
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
//
// The output is UTF-8 JSON without a BOM. The file is created with mode
// 0644. Any existing file at the same path is overwritten.
func (r *Registry) Save(path string) error {
	data, err := r.ToJSON()
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}
