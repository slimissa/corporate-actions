// Go Example: Querying the Corporate Actions Registry
//
// Demonstrates how to use the Go wrapper
// (github.com/slimissa/corporate-actions/wrappers/go/registry)
// to load and query the Corporate Actions Registry (actions.json).
//
// Build and run from wrappers/go:
//
//     cd wrappers/go
//     go run ../../examples/go_lookup.go ../../actions.json
//
// Or, place this file in wrappers/go/examples/ and run:
//
//     cd wrappers/go
//     go run ./examples/go_lookup.go ../../actions.json
//
// Command-line usage:
//
//     go_lookup [OPTIONS]
//
//     --actions PATH                Path to actions.json
//     --isin ISIN                   Look up all actions for an ISIN
//     --action-id ID                Look up one action by action_id
//     --action-type TYPE            Filter by action type
//     --date-range START END        Filter by date range (YYYY-MM-DD)
//     --date-field FIELD            Date field for --date-range
//     --summary                     Only print summary counts
//     --help, -h                    Show this help message

package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	registry "github.com/slimissa/corporate-actions/wrappers/go/registry"
)

const usage = `Usage: go_lookup [OPTIONS]

Options:
  --actions PATH                Path to actions.json
  --isin ISIN                   Look up all actions for an ISIN
  --action-id ID                Look up one action by action_id
  --action-type TYPE            Filter by type (SPLIT, DIVIDEND, SYMBOL_CHANGE, ...)
  --date-range START END        Filter by date range (YYYY-MM-DD)
  --date-field FIELD            Date field for --date-range
                                (announcement, ex_date, record_date, effective_date)
  --summary                     Only print summary counts
  --help, -h                    Show this help message
`

type args struct {
	actions    string
	isin       string
	actionID   string
	actionType string
	dateRange  [2]string
	hasRange   bool
	dateField  string
	summary    bool
}

func parseArgs() args {
	a := args{dateField: "ex_date"}
	argv := os.Args[1:]
	for i := 0; i < len(argv); i++ {
		arg := argv[i]
		switch arg {
		case "--actions":
			i++
			if i >= len(argv) {
				fmt.Fprintln(os.Stderr, "Error: --actions requires a path")
				os.Exit(2)
			}
			a.actions = argv[i]
		case "--isin":
			i++
			if i >= len(argv) {
				fmt.Fprintln(os.Stderr, "Error: --isin requires an argument")
				os.Exit(2)
			}
			a.isin = argv[i]
		case "--action-id":
			i++
			if i >= len(argv) {
				fmt.Fprintln(os.Stderr, "Error: --action-id requires an argument")
				os.Exit(2)
			}
			a.actionID = argv[i]
		case "--action-type":
			i++
			if i >= len(argv) {
				fmt.Fprintln(os.Stderr, "Error: --action-type requires an argument")
				os.Exit(2)
			}
			a.actionType = argv[i]
		case "--date-range":
			if i+2 >= len(argv) {
				fmt.Fprintln(os.Stderr, "Error: --date-range requires START and END")
				os.Exit(2)
			}
			a.dateRange[0] = argv[i+1]
			a.dateRange[1] = argv[i+2]
			a.hasRange = true
			i += 2
		case "--date-field":
			i++
			if i >= len(argv) {
				fmt.Fprintln(os.Stderr, "Error: --date-field requires an argument")
				os.Exit(2)
			}
			a.dateField = argv[i]
		case "--summary":
			a.summary = true
		case "--help", "-h":
			fmt.Print(usage)
			os.Exit(0)
		default:
			if strings.HasPrefix(arg, "--") {
				fmt.Fprintf(os.Stderr, "Unknown argument: %s\n", arg)
				fmt.Print(usage)
				os.Exit(2)
			}
			// Positional: path to actions.json
			if a.actions == "" {
				a.actions = arg
			} else {
				fmt.Fprintf(os.Stderr, "Unexpected positional argument: %s\n", arg)
				fmt.Print(usage)
				os.Exit(2)
			}
		}
	}
	return a
}

// findActionsFile locates actions.json.
// Priority: explicit path > cwd/actions.json > ../actions.json > ../../actions.json
func findActionsFile(cliPath string) string {
	if cliPath != "" {
		if _, err := os.Stat(cliPath); err != nil {
			fmt.Fprintf(os.Stderr, "Error: file not found: %s\n", cliPath)
			os.Exit(2)
		}
		return cliPath
	}

	cwd, _ := os.Getwd()
	candidates := []string{
		filepath.Join(cwd, "actions.json"),
		filepath.Join(cwd, "..", "actions.json"),
		filepath.Join(cwd, "..", "..", "actions.json"),
	}
	for _, c := range candidates {
		if _, err := os.Stat(c); err == nil {
			return c
		}
	}
	fmt.Fprintln(os.Stderr, "Error: could not find actions.json. Use --actions PATH.")
	os.Exit(2)
	return ""
}

func printAction(a registry.Action) {
	if a.ActionID != nil {
		fmt.Printf("  action_id:   %s\n", *a.ActionID)
	}
	if a.ISIN != nil {
		fmt.Printf("  isin:        %s\n", *a.ISIN)
	}
	if a.ActionType != nil {
		fmt.Printf("  action_type: %s\n", *a.ActionType)
	}
	if a.Ratio != nil {
		fmt.Printf("  ratio:       %s\n", *a.Ratio)
	}
	if a.Amount != nil {
		cur := ""
		if a.Currency != nil {
			cur = *a.Currency
		}
		fmt.Printf("  amount:      %v %s\n", *a.Amount, cur)
	}
	if a.Dates != nil {
		if a.Dates.Announcement != nil {
			fmt.Printf("  announced:   %s\n", *a.Dates.Announcement)
		}
		if a.Dates.ExDate != nil {
			fmt.Printf("  ex_date:     %s\n", *a.Dates.ExDate)
		}
		if a.Dates.RecordDate != nil {
			fmt.Printf("  record_date: %s\n", *a.Dates.RecordDate)
		}
		if a.Dates.EffectiveDate != nil {
			fmt.Printf("  effective:   %s\n", *a.Dates.EffectiveDate)
		}
	}
	if a.Provenance != nil && a.Provenance.SourceURL != nil {
		fmt.Printf("  source:      %s\n", *a.Provenance.SourceURL)
	}
	if a.Impact != nil {
		var parts []string
		if a.Impact.PriceMultiplier != nil {
			parts = append(parts, fmt.Sprintf("price×%v", *a.Impact.PriceMultiplier))
		}
		if a.Impact.ShareMultiplier != nil {
			parts = append(parts, fmt.Sprintf("share×%v", *a.Impact.ShareMultiplier))
		}
		if a.Impact.CashAdjustment != nil {
			parts = append(parts, fmt.Sprintf("cash+%v", *a.Impact.CashAdjustment))
		}
		if len(parts) > 0 {
			fmt.Printf("  impact:      %s\n", strings.Join(parts, ", "))
		}
	}
}

func printActions(actions []registry.Action, header string) {
	if len(actions) == 0 {
		fmt.Printf("%s: (none)\n", header)
		return
	}
	fmt.Printf("%s: %d action(s)\n", header, len(actions))
	for _, a := range actions {
		fmt.Println()
		printAction(a)
	}
}

func main() {
	a := parseArgs()
	actionsPath := findActionsFile(a.actions)

	fmt.Printf("Loading registry from: %s\n", actionsPath)

	r, err := registry.LoadRegistry(actionsPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error loading registry: %v\n", err)
		os.Exit(1)
	}

	meta := r.Meta()
	version := "(unknown)"
	if meta.Version != nil {
		version = *meta.Version
	}
	source := "(unknown)"
	if meta.Source != nil {
		source = *meta.Source
	}
	generatedAt := "(unknown)"
	if meta.GeneratedAt != nil {
		generatedAt = *meta.GeneratedAt
	}
	fmt.Printf("  version:       %s\n", version)
	fmt.Printf("  source:        %s\n", source)
	fmt.Printf("  generated_at:  %s\n", generatedAt)
	fmt.Printf("  total actions: %d\n", r.Count())
	fmt.Printf("  action types:  %s\n", strings.Join(r.AllActionTypes(), ", "))
	fmt.Println()

	// Targeted queries
	if a.actionID != "" {
		action := r.ByActionID(a.actionID)
		if action != nil {
			printActions([]registry.Action{*action}, fmt.Sprintf("Lookup by action_id '%s'", a.actionID))
		} else {
			printActions(nil, fmt.Sprintf("Lookup by action_id '%s'", a.actionID))
		}
		return
	}

	if a.isin != "" {
		actions := r.ByISIN(a.isin)
		printActions(actions, fmt.Sprintf("Lookup by ISIN '%s'", a.isin))
		return
	}

	if a.actionType != "" {
		actions := r.ByActionType(a.actionType)
		printActions(actions, fmt.Sprintf("Lookup by action_type '%s'", a.actionType))
		return
	}

	if a.hasRange {
		actions := r.ByDateRange(a.dateRange[0], a.dateRange[1], a.dateField)
		printActions(actions, fmt.Sprintf("Lookup by %s between %s and %s", a.dateField, a.dateRange[0], a.dateRange[1]))
		return
	}

	// Default summary
	fmt.Println("Registry summary by action type:")
	for _, t := range r.AllActionTypes() {
		acts := r.ByActionType(t)
		fmt.Printf("  %s: %d\n", t, len(acts))
	}

	fmt.Println()
	fmt.Println("Use --isin, --action-id, --action-type, or --date-range for targeted queries.")
	fmt.Println("Run with --help for full usage.")
}