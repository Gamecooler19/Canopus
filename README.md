# Canopus

**CLI-native personal AI assistant runtime.** Canopus is a Python-first, modular AI operating layer for the command line — combining local and remote LLM support, a unified capability system, legacy file-based plugins, MCP server integration, a layered memory subsystem, and a YAML-driven workflow engine into one cohesive, extensible CLI runtime. It is designed to feel like a serious tool: deterministic where it matters, observable by default, and extensible without chaos.

> **Development is currently paused.** The core foundation through Phase 5 is implemented and tested. See [PROJECT-STATUS.md](PROJECT-STATUS.md) for the full breakdown of what is done and what is planned.

[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-516%20passed-brightgreen)](#testing)
[![Type-checked](https://img.shields.io/badge/mypy-strict-blue)](#testing)

---

## What Canopus is

Canopus is not a chat wrapper. It is an **AI operating layer** built for people who live in the terminal:

- **CLI-first**: every interaction is a command, not a GUI
- **Local-first**: runs fully offline with local LLMs; cloud providers are optional
- **Capability-oriented**: everything Canopus can do is a registered, policy-governed capability
- **Plugin-friendly**: drop a single Python file into `~/.canopus/plugins/` to extend it
- **MCP-ready**: integrates with Model Context Protocol servers as a first-class capability source
- **Memory-aware**: stores and retrieves context across sessions using a local SQLite-backed store
- **Workflow-driven**: define multi-step automations in YAML; execute them from the CLI

---

## Architecture highlights

```
canopus/
├── cli/           — Typer CLI app, command groups, Rich rendering
├── core/          — runtime, config, profiles, tracing, error hierarchy
├── reasoning/     — planner / executor / reflector pipeline, model router, prompts
├── models/        — provider abstraction (local: echo; remote: interface only)
├── capabilities/  — registry, specs, executor, native capabilities
├── plugins/       — legacy Python file loader + MCP client adapters
├── memory/        — SQLite FTS5 store, retrieval, context builder, service layer
├── workflows/     — YAML workflow engine: loader, executor, engine, CLI commands
├── security/      — permissions, sandbox, secrets, redaction
└── storage/       — SQLite helpers, file I/O, cache
```

The system routes all actions through a shared **capability registry**. Whether a capability comes from native code, a legacy Python plugin, or an MCP server, the planner and executor see the same normalized interface.

---

## Current implementation status

| Area | Status |
|---|---|
| CLI runtime (`typer` + `rich`) | ✅ Implemented |
| Config, profiles, runtime model | ✅ Implemented |
| Structured tracing (JSON, per-run) | ✅ Implemented |
| Error hierarchy | ✅ Implemented |
| Model abstraction (provider interface) | ✅ Implemented |
| Echo provider (deterministic, offline) | ✅ Implemented |
| Model router (profile-driven) | ✅ Implemented |
| Reasoning pipeline (planner/executor/reflector) | ✅ Implemented |
| Capability registry + specs | ✅ Implemented |
| Native capabilities (`filesystem.list_dir`, `filesystem.read`, `system.now`) | ✅ Implemented |
| Legacy Python plugin loader | ✅ Implemented |
| MCP client + adapter | ✅ Implemented |
| Memory store (SQLite FTS5) | ✅ Implemented |
| Memory retrieval + context builder | ✅ Implemented |
| Workflow engine (YAML, multi-step, templates) | ✅ Implemented |
| Remote model providers (Ollama, OpenAI, etc.) | ⏸ Deferred |
| Voice pipeline (STT/TTS) | ⏸ Deferred |
| Workflow scheduler | ⏸ Deferred |
| Production packaging / PyPI release | ⏸ Deferred |

---

## Installation

**Requires Python 3.12+** and [`uv`](https://github.com/astral-sh/uv) or `pip`.

```bash
git clone https://github.com/Gamecooler19/Canopus.git
cd Canopus

# With uv (recommended)
uv pip install -e ".[dev]"

# Or with pip
pip install -e ".[dev]"

# Verify
canopus version
canopus doctor
```

### Conda (development environment)

```bash
conda create -n canopus python=3.12
conda activate canopus
pip install -e ".[dev]"
```

---

## Data layout

All runtime data lives under `~/.canopus/`:

```
~/.canopus/
├── config/
│   ├── config.toml          # main config (created on first run)
│   ├── profiles/            # user-defined TOML profiles
│   └── policies/
├── plugins/                 # drop .py files here for legacy plugins
├── memory/                  # SQLite memory store
├── traces/                  # JSON execution traces, one per run
├── workflows/               # YAML workflow definitions
├── cache/
└── logs/
```

---

## Common commands

```bash
# Health check and environment summary
canopus doctor

# Version information
canopus version

# One-shot prompt execution
canopus run "summarise my notes from today"

# Interactive chat session
canopus chat

# Profile management
canopus profile list
canopus profile show local-private

# Capability discovery
canopus capability list
canopus capability inspect filesystem.list_dir

# Memory management
canopus memory list
canopus memory search "architecture decisions"
canopus memory add "Decided to use SQLite for the memory store"

# Workflow execution
canopus workflow list
canopus workflow inspect directory_summary
canopus workflow run directory_summary --input path=/home/user/notes
canopus workflow validate my_workflow

# Legacy plugins
canopus plugin list
canopus plugin doctor

# MCP servers
canopus mcp list
canopus mcp status

# Trace inspection
canopus trace list
canopus trace show <run-id>
```

---

## Profiles

Canopus selects model providers and policy settings based on the active profile:

| Profile | Description |
|---|---|
| `local-private` | Fully local, no network, privacy-first |
| `hybrid-power` | Local models preferred, cloud fallback allowed |
| `remote-fast` | Cloud model providers preferred |

```bash
canopus profile list
canopus profile show hybrid-power
```

User-defined profiles live in `~/.canopus/config/profiles/<name>.toml`.

---

## Writing a plugin

Drop a single Python file into `~/.canopus/plugins/`:

```python
# ~/.canopus/plugins/greet.py
CANOPUS_PLUGIN = {
    "name": "hello.greet",
    "description": "Greet the user by name.",
    "inputs": {"name": "str"},
}

def run(inputs: dict, ctx) -> dict:
    return {"message": f"Hello, {inputs['name']}!"}
```

See [docs/plugin-contract.md](docs/plugin-contract.md) for the full plugin API.

---

## Writing a workflow

Create a YAML file in `~/.canopus/workflows/`:

```yaml
name: quick_summary
description: Read a file and summarise it.
inputs:
  - name: path
    required: true
steps:
  - id: read
    kind: capability
    capability: filesystem.read
    inputs:
      path: "{{ inputs.path }}"
  - id: summarise
    kind: model
    prompt: "Summarise this content:\n{{ steps.read.text }}"
  - id: result
    kind: output
    value: "{{ steps.summarise.text }}"
```

```bash
canopus workflow run quick_summary --input path=/home/user/notes.md
```

See [docs/workflows.md](docs/workflows.md) for the full workflow reference.

---

## Testing

```bash
# Run all tests
pytest

# Run with output
pytest -v

# Run a specific module
pytest tests/test_workflows.py

# Lint
ruff check .

# Type-check
mypy canopus

# All three (CI-equivalent)
ruff check . && mypy canopus && pytest
```

Current state: **516 tests pass**, 1 skipped. mypy strict mode across 80 source files. ruff clean.

---

## Project structure

```
canopus/           — main package
tests/             — pytest test suite (12 modules)
docs/              — documentation (plugin contract, MCP, memory, workflows)
examples/          — example workflows and plugin files
architecture.md    — detailed system architecture document
pyproject.toml     — project metadata and tool configuration
PROJECT-STATUS.md  — current development status and roadmap
CONTRIBUTING.md    — contribution guide
CHANGELOG.md       — change history
```

---

## Documentation index

| Document | Description |
|---|---|
| [architecture.md](architecture.md) | Full system architecture and design principles |
| [PROJECT-STATUS.md](PROJECT-STATUS.md) | Current status, completed phases, roadmap |
| [docs/plugin-contract.md](docs/plugin-contract.md) | Legacy plugin API reference |
| [docs/mcp.md](docs/mcp.md) | MCP integration guide |
| [docs/memory.md](docs/memory.md) | Memory subsystem reference |
| [docs/workflows.md](docs/workflows.md) | Workflow engine reference |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup and contribution guide |
| [SECURITY.md](SECURITY.md) | Security reporting and guidance |

---

## Contributing

Development is currently paused. If you want to contribute when it resumes, see [CONTRIBUTING.md](CONTRIBUTING.md). For bugs or security issues, see [SECURITY.md](SECURITY.md).

---

## License

MIT — see [LICENSE](LICENSE).

---

## Repository

[https://github.com/Gamecooler19/Canopus](https://github.com/Gamecooler19/Canopus)
