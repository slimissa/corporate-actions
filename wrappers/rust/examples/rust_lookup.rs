//! Rust Example: Querying the Corporate Actions Registry
//!
//! Demonstrates how to use the `corporate-actions` crate to load and
//! query the Corporate Actions Registry (actions.json).
//!
//! Build and run from the wrappers/rust directory:
//!
//!     cd wrappers/rust
//!     cargo run --example rust_lookup -- ../../actions.json
//!
//! Or, if you copied this file to wrappers/rust/examples/, cargo will
//! pick it up automatically as an example:
//!
//!     cd wrappers/rust
//!     cargo run --example rust_lookup -- --help
//!
//! Command-line usage:
//!
//!     rust_lookup [OPTIONS]
//!
//!     --actions PATH                Path to actions.json
//!     --isin ISIN                   Look up all actions for an ISIN
//!     --action-id ID                Look up one action by action_id
//!     --action-type TYPE            Filter by action type (SPLIT, DIVIDEND, ...)
//!     --date-range START END        Filter by date range (YYYY-MM-DD)
//!     --date-field FIELD            Date field for --date-range
//!     --summary                     Only print summary counts
//!     --help, -h                    Show this help message

use corporate_actions_registry::{Action, Registry};
use std::env;
use std::path::PathBuf;
use std::process;

const USAGE: &str = "\
Usage: rust_lookup [OPTIONS]

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
";

#[derive(Default, Debug)]
struct Args {
    actions: Option<PathBuf>,
    isin: Option<String>,
    action_id: Option<String>,
    action_type: Option<String>,
    date_range: Option<(String, String)>,
    date_field: String,
    summary: bool,
}

fn parse_args() -> Args {
    let mut args = Args {
        date_field: "ex_date".to_string(),
        ..Default::default()
    };

    let mut iter = env::args().skip(1);
    while let Some(arg) = iter.next() {
        match arg.as_str() {
            "--actions" => {
                args.actions = iter.next().map(PathBuf::from);
                if args.actions.is_none() {
                    eprintln!("Error: --actions requires a path argument");
                    process::exit(2);
                }
            }
            "--isin" => {
                args.isin = iter.next();
                if args.isin.is_none() {
                    eprintln!("Error: --isin requires an argument");
                    process::exit(2);
                }
            }
            "--action-id" => {
                args.action_id = iter.next();
                if args.action_id.is_none() {
                    eprintln!("Error: --action-id requires an argument");
                    process::exit(2);
                }
            }
            "--action-type" => {
                args.action_type = iter.next();
                if args.action_type.is_none() {
                    eprintln!("Error: --action-type requires an argument");
                    process::exit(2);
                }
            }
            "--date-range" => {
                let start = iter.next();
                let end = iter.next();
                match (start, end) {
                    (Some(s), Some(e)) => args.date_range = Some((s, e)),
                    _ => {
                        eprintln!("Error: --date-range requires START and END arguments");
                        process::exit(2);
                    }
                }
            }
            "--date-field" => {
                match iter.next() {
                    Some(f) => args.date_field = f,
                    None => {
                        eprintln!("Error: --date-field requires an argument");
                        process::exit(2);
                    }
                }
            }
            "--summary" => args.summary = true,
            "--help" | "-h" => {
                print!("{}", USAGE);
                process::exit(0);
            }
            other => {
                if other.starts_with("--") {
                    eprintln!("Unknown argument: {}", other);
                    print!("{}", USAGE);
                    process::exit(2);
                } else {
                    // Positional argument: treat as path to actions.json
                    if args.actions.is_none() {
                        args.actions = Some(PathBuf::from(other));
                    } else {
                        eprintln!("Error: unexpected positional argument: {}", other);
                        print!("{}", USAGE);
                        process::exit(2);
                    }
                }
            }
        }
    }

    args
}

/// Locate actions.json.
/// Priority: --actions > cwd/actions.json > ../actions.json relative to
/// the current working directory.
fn find_actions_file(cli_path: &Option<PathBuf>) -> PathBuf {
    if let Some(p) = cli_path {
        if !p.exists() {
            eprintln!("Error: file not found: {}", p.display());
            process::exit(2);
        }
        return p.clone();
    }

    let cwd = env::current_dir().unwrap_or_else(|_| PathBuf::from("."));

    // Check cwd, then parent, then grandparent (for wrappers/rust layout).
    let candidates = [
        cwd.join("actions.json"),
        cwd.join("..").join("actions.json"),
        cwd.join("..").join("..").join("actions.json"),
    ];
    for candidate in &candidates {
        if candidate.exists() {
            return candidate.clone();
        }
    }

    eprintln!("Error: could not find actions.json. Use --actions PATH or pass a path as a positional argument.");
    process::exit(2);
}

fn print_action(action: &Action) {
    if let Some(v) = &action.action_id {
        println!("  action_id:   {}", v);
    }
    if let Some(v) = &action.isin {
        println!("  isin:        {}", v);
    }
    if let Some(v) = &action.action_type {
        println!("  action_type: {}", v);
    }
    if let Some(v) = &action.ratio {
        println!("  ratio:       {}", v);
    }
    if let Some(v) = action.amount {
        let currency = action.currency.as_deref().unwrap_or("");
        println!("  amount:      {} {}", v, currency);
    }
    if let Some(d) = &action.dates {
        if let Some(v) = &d.announcement {
            println!("  announced:   {}", v);
        }
        if let Some(v) = &d.ex_date {
            println!("  ex_date:     {}", v);
        }
        if let Some(v) = &d.record_date {
            println!("  record_date: {}", v);
        }
        if let Some(v) = &d.effective_date {
            println!("  effective:   {}", v);
        }
    }
    if let Some(p) = &action.provenance {
        if let Some(url) = &p.source_url {
            println!("  source:      {}", url);
        }
    }
    if let Some(im) = &action.impact {
        let mut parts: Vec<String> = Vec::new();
        if let Some(x) = im.price_multiplier {
            parts.push(format!("price×{}", x));
        }
        if let Some(x) = im.share_multiplier {
            parts.push(format!("share×{}", x));
        }
        if let Some(x) = im.cash_adjustment {
            parts.push(format!("cash+{}", x));
        }
        if !parts.is_empty() {
            println!("  impact:      {}", parts.join(", "));
        }
    }
}

fn print_actions(actions: &[Action], header: &str) {
    if actions.is_empty() {
        println!("{}: (none)", header);
        return;
    }
    println!("{}: {} action(s)", header, actions.len());
    for a in actions {
        println!();
        print_action(a);
    }
}

fn main() {
    let args = parse_args();
    let actions_path = find_actions_file(&args.actions);

    println!("Loading registry from: {}", actions_path.display());

    let registry = match Registry::load_from_file(&actions_path) {
        Ok(r) => r,
        Err(e) => {
            eprintln!("Error loading registry: {}", e);
            process::exit(1);
        }
    };

    let meta = registry.meta();
    println!(
        "  version:       {}",
        meta.version.as_deref().unwrap_or("(unknown)")
    );
    println!(
        "  source:        {}",
        meta.source.as_deref().unwrap_or("(unknown)")
    );
    println!(
        "  generated_at:  {}",
        meta.generated_at.as_deref().unwrap_or("(unknown)")
    );
    println!("  total actions: {}", registry.count());
    println!("  action types:  {}", registry.all_action_types().join(", "));
    println!();

    // Targeted queries
    if let Some(id) = &args.action_id {
        match registry.by_action_id(id) {
            Some(a) => print_actions(&[a], &format!("Lookup by action_id '{}'", id)),
            None => print_actions(&[], &format!("Lookup by action_id '{}'", id)),
        }
        return;
    }

    if let Some(isin) = &args.isin {
        let actions = registry.by_isin(isin);
        print_actions(&actions, &format!("Lookup by ISIN '{}'", isin));
        return;
    }

    if let Some(t) = &args.action_type {
        let actions = registry.by_action_type(t);
        print_actions(&actions, &format!("Lookup by action_type '{}'", t));
        return;
    }

    if let Some((start, end)) = &args.date_range {
        let actions = registry.by_date_range(Some(start), Some(end), &args.date_field);
        print_actions(
            &actions,
            &format!(
                "Lookup by {} between {} and {}",
                args.date_field, start, end
            ),
        );
        return;
    }

    // Default summary
    println!("Registry summary by action type:");
    for t in registry.all_action_types() {
        let acts = registry.by_action_type(&t);
        println!("  {}: {}", t, acts.len());
    }

    println!();
    println!("First 3 actions (for illustration):");
    for a in registry.all_actions().iter().take(3) {
        println!();
        print_action(a);
    }

    if !args.summary {
        println!();
        println!("Use --isin, --action-id, --action-type, or --date-range for targeted queries.");
        println!("Run with --help for full usage.");
    }
}