# EventHorizon CLI — Technical Architecture

## Project Structure

```
eventhorizon-cli/
├── pyproject.toml                          # PEP 621 package config
├── ARCHITECTURE.md                         # This file
└── src/
    └── eventhorizon/
        ├── __init__.py                     # Package version (__version__)
        ├── __main__.py                     # python -m eventhorizon support
        ├── cli.py                          # Click command definitions
        ├── splash.py                       # ASCII art splash screen
        ├── scanner/
        │   ├── __init__.py
        │   ├── static_analyzer.py          # Regex-based rule scanner
        │   ├── caching_analyzer.py         # Drupal caching issue detector
        │   └── rules/
        │       └── custom_rules.yml        # Scanner rule definitions
        ├── discovery/
        │   ├── __init__.py
        │   └── module_finder.py            # Drupal module/theme discovery
        ├── reporter/
        │   ├── __init__.py
        │   ├── terminal_reporter.py        # Rich-based terminal output
        │   ├── csv_reporter.py             # CSV file export
        │   └── xlsx_reporter.py            # Excel file export
        └── utils/
            ├── __init__.py
            ├── drupal_detection.py         # Project structure detection (standard/restricted/multisite)
            └── severity.py                 # Severity mapping (error→High)
```

***

## Key Design Decisions

| Decision                     | Rationale                                                                       |
| ---------------------------- | ------------------------------------------------------------------------------- |
| **Click** for CLI            | Industry standard, decorators for clean arg parsing, auto-generated help        |
| **Rich** for terminal output | Tables, progress bars, colored text, markdown rendering — one library           |
| **src layout**               | Prevents accidental imports from project root, PEP recommended                  |
| **pyproject.toml (PEP 621)** | Modern Python packaging, no setup.py or setup.cfg needed                        |
| **Console entry point**      | `eventhorizon = "eventhorizon.cli:main"` registered via `[project.scripts]`     |
| **YAML rules**               | Easy to extend without code changes                                             |
| **No Flask/web deps**        | CLI must be lightweight; no web framework dependencies                          |
| **No AI/LLM deps**           | v1 is pure static analysis; no google-generativeai, openai, anthropic, chromadb |

***

## Data Flow

```
CLI Invocation
    │
    ▼
┌─────────────────────────────┐
│  cli.py (Click)             │
│  Parse args: path, type,    │
│  filter, format, output,    │
│  site                       │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  drupal_detection.py        │
│  detect_project_structure() │
│  6-phase: webroot, .info.yml│
│  discovery, config, multisite│
│  classification, path conv  │
│  (exit 2 if invalid)        │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  drupal_detection.py        │
│  build_scan_targets()       │
│  Filter by custom/contrib,  │
│  --site for multisite       │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  module_finder.py           │
│  Discover modules/themes    │
│  Apply --filter scoping     │
└──────────────┬──────────────┘
               │
               ▼
┌──────────────┴──────────────┐
│                             │
▼                             ▼
┌───────────────┐  ┌──────────────────┐
│ static_       │  │ caching_         │
│ analyzer.py   │  │ analyzer.py      │
│ (YAML rules)  │  │ (context-aware)  │
└───────┬───────┘  └────────┬─────────┘
        │                   │
        └─────────┬─────────┘
                  │
                  ▼
        ┌─────────────────┐
        │ Findings List   │
        │ [{tool, file,   │
        │   line, severity│
        │   message, rule,│
        │   category}]    │
        └────────┬────────┘
                 │
                 ▼
        ┌─────────────────┐
        │ severity.py     │
        │ Map: error→High │
        │ warning→Medium  │
        │ info→Low        │
        └────────┬────────┘
                 │
      ┌──────────┼──────────┐
      ▼          ▼          ▼
┌──────────┐ ┌────────┐ ┌────────┐
│ terminal │ │ csv    │ │ xlsx   │
│ reporter │ │ report │ │ report │
│ (stdout) │ │ (.csv) │ │(.xlsx) │
└──────────┘ └────────┘ └────────┘
```

***

## Dependencies

```TOML
[project]
dependencies = [
    "click>=8.0",       # CLI framework
    "rich>=13.0",       # Terminal formatting (tables, progress, colors)
    "PyYAML>=6.0",      # YAML rule file parsing
    "openpyxl>=3.0",    # Excel report generation
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",      # Test runner
    "pytest-cov>=4.0",  # Coverage reporting
]
```

**Explicitly excluded:** Flask, Flask-Login, Authlib, NetworkX, ChromaDB, sentence-transformers, google-generativeai, openai, anthropic, Gunicorn.
