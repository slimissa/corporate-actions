// Ticker-index support for ByTicker.
//
// Loads identifiers.json (the Asset Identifiers registry) and returns
// a map from "TICKER|EXCHANGE" to ISIN. Results are cached per absolute
// path for the life of the process.
//
// See docs/wrapper_contract.md section 4.8.
package registry

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
)

// identifiersDocument is the top-level shape of identifiers.json.
type identifiersDocument struct {
	Instruments []identifierInstrument `json:"instruments"`
}

type identifierInstrument struct {
	Ticker   string `json:"ticker"`
	Exchange string `json:"exchange"`
	ISIN     string `json:"isin"`
}

// tickerCache caches the parsed index by absolute path. A mutex guards
// concurrent access; the map is read on every ByTicker call and written
// only on a cache miss.
var (
	tickerCacheMu sync.Mutex
	tickerCache   = map[string]map[string]string{}
)

// ResetTickerIndexCache clears the per-path ticker index cache. For
// tests only.
func ResetTickerIndexCache() {
	tickerCacheMu.Lock()
	defer tickerCacheMu.Unlock()
	tickerCache = map[string]map[string]string{}
}

// tickerKey normalises a (ticker, exchange) pair into the cache key.
func tickerKey(ticker, exchange string) string {
	return strings.ToUpper(ticker) + "|" + strings.ToUpper(exchange)
}

// resolveIdentifiersPath returns the path to identifiers.json.
//
// Priority:
//  1. Explicit argument
//  2. $CORP_ACTIONS_IDENTIFIERS_PATH
//  3. $LAS_DATA_HOME/identifiers.json
//
// The returned error wraps ErrMissingData so callers can match on it
// with errors.Is.
func resolveIdentifiersPath(explicit string) (string, error) {
	if explicit != "" {
		return explicit, nil
	}
	if p := os.Getenv("CORP_ACTIONS_IDENTIFIERS_PATH"); p != "" {
		return p, nil
	}
	if home := os.Getenv("LAS_DATA_HOME"); home != "" {
		return filepath.Join(home, "identifiers.json"), nil
	}
	return "", fmt.Errorf(
		"%w: neither CORP_ACTIONS_IDENTIFIERS_PATH nor LAS_DATA_HOME "+
			"is set, and no identifiersPath was provided",
		ErrMissingData,
	)
}

// loadTickerIndex loads identifiers.json and returns a map from
// "TICKER|EXCHANGE" to ISIN. The result is cached by absolute path.
//
// The returned error wraps ErrMissingData so callers can match on it
// with errors.Is.
func loadTickerIndex(path string) (map[string]string, error) {
	abs, err := filepath.Abs(path)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrMissingData, err)
	}

	tickerCacheMu.Lock()
	defer tickerCacheMu.Unlock()

	if cached, ok := tickerCache[abs]; ok {
		return cached, nil
	}

	data, err := os.ReadFile(abs)
	if err != nil {
		return nil, fmt.Errorf(
			"%w: %s not found; set CORP_ACTIONS_IDENTIFIERS_PATH or LAS_DATA_HOME",
			ErrMissingData, abs,
		)
	}

	// Strip a UTF-8 BOM if present.
	data = bytes.TrimPrefix(data, []byte{0xEF, 0xBB, 0xBF})

	var doc identifiersDocument
	if err := json.Unmarshal(data, &doc); err != nil {
		return nil, fmt.Errorf(
			"%w: parsing %s: %v", ErrMissingData, abs, err,
		)
	}

	index := make(map[string]string, len(doc.Instruments))
	for _, inst := range doc.Instruments {
		if inst.Ticker == "" || inst.Exchange == "" || inst.ISIN == "" {
			continue
		}
		index[tickerKey(inst.Ticker, inst.Exchange)] = inst.ISIN
	}

	tickerCache[abs] = index
	return index, nil
}