# Canopus

CLI-native, plugin-based personal AI assistant runtime.

## Quick start

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Verify installation
canopus version

# Run a health check
canopus doctor

# List available profiles
canopus profile list

# Show a profile's details
canopus profile show local-private

# One-shot run (requires a model provider — see Phase 2)
canopus run "summarise my notes from today"

# Interactive chat (requires a model provider — see Phase 2)
canopus chat
```

## Data layout

All runtime data lives under `~/.canopus/`:

```
~/.canopus/
├── config/
│   ├── config.toml       # main config (created on first run)
│   ├── profiles/         # user-defined .toml profiles
│   └── policies/
├── plugins/
├── memory/
├── traces/               # JSON execution traces
├── workflows/
├── cache/
└── logs/
```

## Development

```bash
# Run tests
pytest

# Lint
ruff check canopus tests

# Type-check
mypy canopus
```
