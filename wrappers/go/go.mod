module github.com/slimissa/corporate-actions/wrappers/go

// The Go wrapper uses features that require Go 1.21:
//   - errors.Join (used in the fixture loader test path)
//   - stdlib "slices" (used by ticker_index for stable sort)
// If you need to support an older Go, lower this and remove those
// call sites; the core API does not need them.
go 1.21