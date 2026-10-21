// Package registry provides a typed interface to the Corporate Actions Registry.
//
// It loads actions.json and builds in-memory indexes for fast lookups by
// ISIN, action ID, action type, ticker, and date range.
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
	"regexp"
	"sort"
	"strconv"
	"strings"
)

// ---------------------------------------------------------------------------
// Exported constants (wrapper contract section 4.9)
// ---------------------------------------------------------------------------

// DefaultDateField is the value the Python and JavaScript wrappers use
// when the date-field argument to by_date_range is omitted. Go requires
// the argument; use this constant rather than hard-coding the string.
const DefaultDateField = "ex_date"

// ValidDateFields is the closed set of date field names accepted by
// ByDateRange. Callers who want to enumerate the choices should read
// this slice rather than duplicating the list.
var ValidDateFields = []string{
	"announcement",
	"ex_date",
	"record_date",
	"effective_date",
}

// DefaultAdjustFor is the default set of action types applied by
// AdjustPrices when the caller passes no adjustFor argument. Exported
// per wrapper contract § 4.9.
var DefaultAdjustFor = []string{
	"SPLIT",
	"REVERSE_SPLIT",
	"DIVIDEND",
	"SPECIAL_DIVIDEND",
}

// ---------------------------------------------------------------------------
// Sentinel errors
// ---------------------------------------------------------------------------

// ErrInvalidDateField is returned by ByDateRange when the requested date
// field name is not one of the four valid values.
var ErrInvalidDateField = errors.New("invalid date_field")

// ErrMissingData is returned by ByTicker when the identifiers file
// cannot be resolved or read.
var ErrMissingData = errors.New("missing identifier data")

// validDateFields is a private O(1) lookup table for the values in
// ValidDateFields. Kept separate so that a caller who mutates the
// exported slice does not silently change what the validator accepts.
var isoDateRE = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}$`)

var validDateFields = map[string]bool{
	"announcement":   true,
	"ex_date":        true,
	"record_date":    true,
	"effective_date": true,
}

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

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
	ISIN           *string     `json:"isin,omitempty"`
	ActionID       *string     `json:"action_id,omitempty"`
	ActionType     *string     `json:"action_type,omitempty"`
	Ratio          *string     `json:"ratio,omitempty"`
	Amount         *float64    `json:"amount,omitempty"`
	Currency       *string     `json:"currency,omitempty"`
	Dates          *Dates      `json:"dates,omitempty"`
	Status         *string     `json:"status,omitempty"`
	Provenance     *Provenance `json:"provenance,omitempty"`
	Impact         *Impact     `json:"impact,omitempty"`
	Redistribution *string     `json:"redistribution,omitempty"`
}

// Meta contains metadata about the registry file.
type Meta struct {
	Version     *string `json:"version,omitempty"`
	GeneratedAt *string `json:"generated_at,omitempty"`
	Source      *string `json:"source,omitempty"`
	Notes       *string `json:"notes,omitempty"`
}

// PriceBar is a single date/price observation, the input element for
// AdjustPrices.
type PriceBar struct {
	Date string  `json:"date"`
	Raw  float64 `json:"raw"`
}

// AdjustedBar is the output of AdjustPrices for one input bar: the input
// echoed back, the adjusted price, and the audit trail of action IDs.
type AdjustedBar struct {
	Date             string   `json:"date"`
	Raw              float64  `json:"raw"`
	Adjusted         float64  `json:"adjusted"`
	AppliedActionIDs []string `json:"applied_action_ids"`
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

// ---------------------------------------------------------------------------
// Deep copy
// ---------------------------------------------------------------------------

// deepCopyAction returns an Action whose pointer fields do not share
// storage with the input. Mutating the returned Action, or writing
// through any of its pointer fields, does not affect the original.
func deepCopyAction(a Action) Action {
	dst := a

	if a.ISIN != nil {
		s := *a.ISIN
		dst.ISIN = &s
	}
	if a.ActionID != nil {
		s := *a.ActionID
		dst.ActionID = &s
	}
	if a.ActionType != nil {
		s := *a.ActionType
		dst.ActionType = &s
	}
	if a.Ratio != nil {
		s := *a.Ratio
		dst.Ratio = &s
	}
	if a.Amount != nil {
		f := *a.Amount
		dst.Amount = &f
	}
	if a.Currency != nil {
		s := *a.Currency
		dst.Currency = &s
	}
	if a.Status != nil {
		s := *a.Status
		dst.Status = &s
	}
	if a.Redistribution != nil {
		s := *a.Redistribution
		dst.Redistribution = &s
	}
	if a.Dates != nil {
		d := *a.Dates
		if a.Dates.Announcement != nil {
			s := *a.Dates.Announcement
			d.Announcement = &s
		}
		if a.Dates.ExDate != nil {
			s := *a.Dates.ExDate
			d.ExDate = &s
		}
		if a.Dates.RecordDate != nil {
			s := *a.Dates.RecordDate
			d.RecordDate = &s
		}
		if a.Dates.EffectiveDate != nil {
			s := *a.Dates.EffectiveDate
			d.EffectiveDate = &s
		}
		dst.Dates = &d
	}

	if a.Provenance != nil {
		p := *a.Provenance
		if a.Provenance.Source != nil {
			s := *a.Provenance.Source
			p.Source = &s
		}
		if a.Provenance.SourceURL != nil {
			s := *a.Provenance.SourceURL
			p.SourceURL = &s
		}
		if a.Provenance.VerificationSource != nil {
			s := *a.Provenance.VerificationSource
			p.VerificationSource = &s
		}
		if a.Provenance.VerificationURL != nil {
			s := *a.Provenance.VerificationURL
			p.VerificationURL = &s
		}
		dst.Provenance = &p
	}

	if a.Impact != nil {
		i := *a.Impact
		if a.Impact.PriceMultiplier != nil {
			f := *a.Impact.PriceMultiplier
			i.PriceMultiplier = &f
		}
		if a.Impact.ShareMultiplier != nil {
			f := *a.Impact.ShareMultiplier
			i.ShareMultiplier = &f
		}
		if a.Impact.CashAdjustment != nil {
			f := *a.Impact.CashAdjustment
			i.CashAdjustment = &f
		}
		dst.Impact = &i
	}

	return dst
}

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------

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

// FromJSON parses a registry document from raw bytes.
//
// Byte-order marks are stripped (wrapper contract section 5.1). The
// document must be a JSON object with an "actions" array; each entry
// must itself be an object. The loader rejects non-object entries,
// duplicate action_id values, and entries with neither "isin" nor
// "action_id" — but it does NOT reject unknown fields inside an action.
//
// This is a deliberate divergence from Python's loader: the Python
// side runs jsonschema validation (additionalProperties: false) at
// tools/validate.py, so malformed input there fails before the wrapper
// ever sees it. Go's loader accepts unknown fields so that a schema
// evolution (new optional field) does not break existing Go callers
// before they upgrade. Documented in docs/wrapper_contract.md § 5.

// FromJSON parses the registry from raw JSON bytes.
//
// The document must be an object with an "actions" array. The "meta"
// object is optional. Each entry in "actions" must itself be a JSON
// object; a string, number, boolean, null, or array entry is a
// structural error, reported with its index.
//
// Structural validation, before any index is built:
//
//   - Every entry must carry at least one of isin or action_id.
//   - No two entries may share a non-empty action_id.
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
		// `{"actions": null}` unmarshals to nil same as a missing key.
		// Naming both cases saves a diagnostic round for callers who
		// hand-edit the file and accidentally null the array.
		return nil, fmt.Errorf("parsing registry JSON: missing 'actions' key (or null)")
	}

	actions := make([]Action, len(*raw.Actions))
	seenIDs := make(map[string]int, len(*raw.Actions))

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

		a := &actions[i]

		// Duplicate action_id check (wrapper contract section 5.5).
		if a.ActionID != nil && *a.ActionID != "" {
			if prev, ok := seenIDs[*a.ActionID]; ok {
				return nil, fmt.Errorf(
					"parsing registry JSON: duplicate action_id at index %d: %s (first seen at index %d)",
					i, *a.ActionID, prev,
				)
			}
			seenIDs[*a.ActionID] = i
		}

		// Missing-identifier check (wrapper contract section 5.6).
		hasISIN := a.ISIN != nil && *a.ISIN != ""
		hasID := a.ActionID != nil && *a.ActionID != ""
		if !hasISIN && !hasID {
			return nil, fmt.Errorf(
				"parsing registry JSON: action at index %d has neither 'isin' nor 'action_id'",
				i,
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
			// The loader already rejected duplicates, so a plain
			// assignment is safe here.
			r.indexID[*action.ActionID] = i
		}
	}

	return r, nil
}

// ---------------------------------------------------------------------------
// Lookup methods
// ---------------------------------------------------------------------------

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
		result[i] = deepCopyAction(r.actions[idx])
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
	copy := deepCopyAction(r.actions[idx])
	return &copy
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
		result[i] = deepCopyAction(r.actions[idx])
	}
	return result
}

// ByDateRange returns actions whose dateField falls in the inclusive
// range [startDate, endDate].
//
// dateField must be one of the values in ValidDateFields. Any other
// value returns ErrInvalidDateField.
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

	for _, b := range [][2]string{{"startDate", startDate}, {"endDate", endDate}} {
		if b[1] != "" && !isoDateRE.MatchString(b[1]) {
			return nil, fmt.Errorf("%s must be YYYY-MM-DD, got %q", b[0], b[1])
		}
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
		result = append(result, deepCopyAction(action))
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

// ByTicker returns all actions for a ticker on an exchange.
//
// Resolves (ticker, exchange) to an ISIN using the Asset Identifiers
// registry, then returns the same list as ByISIN(isin).
//
// Path resolution when identifiersPath is empty:
//
//  1. $CORP_ACTIONS_IDENTIFIERS_PATH
//  2. $LAS_DATA_HOME/identifiers.json
//
// Ticker and exchange are uppercased before lookup. An unknown
// (ticker, exchange) pair returns an empty slice, not an error.
//
// Returns ErrMissingData (wrapped) when no identifiers file can be
// resolved.
//
// See docs/wrapper_contract.md section 4.8.
func (r *Registry) ByTicker(ticker, exchange, identifiersPath string) ([]Action, error) {
	p, err := resolveIdentifiersPath(identifiersPath)
	if err != nil {
		return nil, err
	}
	index, err := loadTickerIndex(p)
	if err != nil {
		return nil, err
	}
	key := tickerKey(ticker, exchange)
	isin, ok := index[key]
	if !ok {
		return []Action{}, nil
	}
	return r.ByISIN(isin), nil
}

// AllActions returns a fresh slice of every action, in insertion order.
// Mutating a returned Action does not affect the registry.
func (r *Registry) AllActions() []Action {
	result := make([]Action, len(r.actions))
	for i, a := range r.actions {
		result[i] = deepCopyAction(a)
	}
	return result
}

// AdjustPrices restates a price series for corporate actions.
//
// For each input bar at date D, every applicable action with ex_date > D
// is applied. SPLIT/REVERSE_SPLIT multiply by impact.price_multiplier;
// DIVIDEND/SPECIAL_DIVIDEND subtract impact.cash_adjustment. A bar on
// the ex-date itself is not adjusted. See docs/wrapper_contract.md § 4.10.
//
// adjustFor is variadic: pass no arguments to use DefaultAdjustFor, or
// one or more action type names to narrow (e.g. AdjustPrices(isin,
// prices, "SPLIT") for split-only adjustment).
//
// An unknown ISIN returns an empty slice (not an error), matching ByISIN.
// A malformed date returns an error naming the offending value.
func (r *Registry) AdjustPrices(isin string, prices []PriceBar, adjustFor ...string) ([]AdjustedBar, error) {
	for _, p := range prices {
		if !isoDateRE.MatchString(p.Date) {
			return nil, fmt.Errorf("invalid price date: %q (must be YYYY-MM-DD)", p.Date)
		}
	}

	rawActions := r.ByISIN(isin)
	if len(rawActions) == 0 {
		return []AdjustedBar{}, nil
	}

	set := adjustFor
	if len(set) == 0 {
		set = DefaultAdjustFor
	}
	adjustSet := make(map[string]bool, len(set))
	for _, t := range set {
		adjustSet[t] = true
	}

	var actions []Action
	for _, a := range rawActions {
		if a.ActionType != nil && adjustSet[*a.ActionType] {
			actions = append(actions, a)
		}
	}

	sorted := make([]PriceBar, len(prices))
	copy(sorted, prices)
	sort.SliceStable(sorted, func(i, j int) bool {
		return sorted[i].Date < sorted[j].Date
	})

	result := make([]AdjustedBar, 0, len(prices))
	for _, p := range sorted {
		adjusted := p.Raw
		applied := []string{}

		for _, a := range actions {
			if a.Dates == nil || a.Dates.ExDate == nil {
				continue
			}
			if *a.Dates.ExDate <= p.Date {
				continue
			}
			var at string
			if a.ActionType != nil {
				at = *a.ActionType
			}
			switch at {
			case "SPLIT", "REVERSE_SPLIT":
				adjusted *= actionPriceMultiplier(a)
				if a.ActionID != nil {
					applied = append(applied, *a.ActionID)
				} else {
					applied = append(applied, "")
				}
			case "DIVIDEND", "SPECIAL_DIVIDEND":
				adjusted -= actionCashAdjustment(a)
				if a.ActionID != nil {
					applied = append(applied, *a.ActionID)
				} else {
					applied = append(applied, "")
				}
			}
		}

		result = append(result, AdjustedBar{
			Date:             p.Date,
			Raw:              p.Raw,
			Adjusted:         adjusted,
			AppliedActionIDs: applied,
		})
	}

	return result, nil
}

// actionPriceMultiplier returns the price multiplier for a SPLIT or
// REVERSE_SPLIT action. Prefers impact.price_multiplier; falls back to
// ratio "new:old" (multiplier = old / new); returns 1.0 otherwise.
func actionPriceMultiplier(a Action) float64 {
	if a.Impact != nil && a.Impact.PriceMultiplier != nil {
		return *a.Impact.PriceMultiplier
	}
	if a.Ratio != nil {
		parts := strings.SplitN(*a.Ratio, ":", 2)
		if len(parts) == 2 {
			newS, err1 := strconv.Atoi(parts[0])
			oldS, err2 := strconv.Atoi(parts[1])
			if err1 == nil && err2 == nil && newS > 0 {
				return float64(oldS) / float64(newS)
			}
		}
	}
	return 1.0
}

// actionCashAdjustment returns the cash adjustment for a DIVIDEND or
// SPECIAL_DIVIDEND action. Prefers impact.cash_adjustment; falls back to
// amount; returns 0.0 otherwise.
func actionCashAdjustment(a Action) float64 {
	if a.Impact != nil && a.Impact.CashAdjustment != nil {
		return *a.Impact.CashAdjustment
	}
	if a.Amount != nil {
		return *a.Amount
	}
	return 0.0
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

// Meta returns a pointer to the registry metadata.
//
// The returned pointer refers to a copy of the Meta struct. The pointer
// fields inside it are shared with the registry's internal Meta, but Go
// strings are immutable, so a caller cannot mutate the registry through
// them.
func (r *Registry) Meta() *Meta {
	m := r.meta
	if m.Version != nil {
		v := *m.Version
		m.Version = &v
	}
	if m.GeneratedAt != nil {
		v := *m.GeneratedAt
		m.GeneratedAt = &v
	}
	if m.Source != nil {
		v := *m.Source
		m.Source = &v
	}
	if m.Notes != nil {
		v := *m.Notes
		m.Notes = &v
	}
	return &m
}

// ---------------------------------------------------------------------------
// Serialization
// ---------------------------------------------------------------------------

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
// Save writes the registry to a file.
//
// The write is atomic: content goes to a temp file adjacent to `path`,
// then os.Rename moves it into place. A crash between write and rename
// leaves the original file intact and a .tmp.<pid> orphan rather than
// a truncated target. See issue #95.
func (r *Registry) Save(path string) error {
	data, err := r.ToJSON()
	if err != nil {
		return err
	}
	tmp := path + ".tmp." + strconv.Itoa(os.Getpid())
	if err := os.WriteFile(tmp, data, 0644); err != nil {
		return err
	}
	if err := os.Rename(tmp, path); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	return nil
}
