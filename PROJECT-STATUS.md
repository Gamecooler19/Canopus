# Project Status

> **Development is currently paused.** This document is the authoritative record
> of what has been built, what has been deferred, and what the original roadmap
> looks like.

---

## Current maturity

Canopus is in **alpha**. The core foundation is built and tested but has not been
publicly released or used in production. It is a portfolio-grade implementation of
a serious CLI AI runtime architecture.

**As of the pause:**

- 516 tests passing, 1 skipped
- mypy strict mode: 80 source files clean
- ruff: zero warnings
- No public release has been tagged

---

## Completed phases

### Phase 1 — Foundation ✅

Built the skeleton every other phase depends on:

- `canopus` CLI via Typer with Rich output
- Config loading from `~/.canopus/config/config.toml`
- Three built-in profiles: `local-private`, `hybrid-power`, `remote-fast`
- User-defined TOML profile override support
- `SessionRuntime` as the execution boundary
- JSON structured tracing (`ExecutionTrace`, `TraceWriter`)
- Full exception hierarchy (`CanopusError` and ~15 typed subclasses)
- `canopus doctor` health check
- `canopus trace list` / `canopus trace show`

### Phase 2 — Model and reasoning core ✅

Built the reasoning pipeline that all chat/run flows use:

- `ModelProvider` protocol (structural interface, zero vendor lock-in)
- `ModelRequest` / `ModelResponse` Pydantic models
- `EchoProvider` — deterministic offline provider for testing
- `ModelRouter` — profile-driven provider selection
- Planner / Executor / Reflector reasoning pipeline
- `run_pipeline()` entry point used by `canopus run` and `canopus chat`
- Centralized prompt management under `canopus/reasoning/prompts/`

### Phase 3 — Capability system ✅

Built the normalized capability layer that all tools flow through:

- `CapabilitySpec` — metadata model (name, permissions, side-effects, transport)
- `CapabilityRegistry` — global singleton
- `CapabilityExecutor` — invokes registered capabilities
- Native capabilities: `filesystem.list_dir`, `filesystem.read`, `system.now`
- Permission and side-effect enums
- `canopus capability list` / `canopus capability inspect`

### Phase 4A — Legacy plugin system ✅

Drop-in extensibility via plain Python files:

- `PluginLoader` discovers `.py` files from `~/.canopus/plugins/`
- `PluginAdapter` normalizes legacy plugins into the capability registry
- `PluginManager` coordinates loading, validation, registration
- `canopus plugin list` / `canopus plugin doctor`

### Phase 4B — MCP integration ✅

MCP servers as first-class capability sources:

- `McpClient` (stdio / SSE transport)
- `McpAdapter` normalizes MCP tool definitions into `CapabilitySpec`
- `McpManager` manages server lifecycles
- `canopus mcp list` / `canopus mcp status`

### Phase 5A — Memory subsystem ✅

Layered memory with SQLite FTS5:

- `MemoryRecord` model with kind, content, tags, importance, session metadata
- `MemoryStore` — SQLite FTS5 backend with WAL mode
- `MemoryRetriever` — full-text search, tag/kind filters, recency ranking
- `ContextBuilder` — assembles prompt-ready memory context
- `MemoryService` — unified façade
- `canopus memory add`, `list`, `search`, `get`, `forget`, `stats`

### Phase 5B — Workflow engine ✅

YAML-driven multi-step automation:

- Step kinds: `capability`, `model`, `memory_search`, `output`, `set_var`
- Template syntax: `{{ inputs.x }}` / `{{ steps.id.field }}`
- `WorkflowLoader` — YAML discovery and Pydantic validation
- `WorkflowEngine` — full orchestration with `on_failure` policy and trace events
- `canopus workflow list`, `inspect`, `validate`, `run`
- Example workflows: `directory_summary.yaml`, `memory_brief.yaml`

---

## Deferred phases

### Phase 6 — Remote model providers ⏸

What's missing:

- Ollama HTTP provider implementation
- OpenAI / Anthropic / Gemini provider implementations
- Provider-specific retry and error handling
- Streaming response consumption
- Token counting and budget management

The `ModelRouter` and `ModelProvider` protocol are ready to accept these.
`EchoProvider` is the only functional provider in the current codebase.

### Phase 7 — Voice pipeline ⏸

Designed but not implemented:

- Speech-to-text abstraction (`faster-whisper` or equivalent)
- Text-to-speech abstraction (`piper` or equivalent)
- Voice activity detection
- Push-to-talk session runtime
- Integration with the existing chat/run pipeline via the same capability system

### Phase 8 — Hardening and packaging ⏸

- Comprehensive integration test suite
- Performance benchmarks and startup time measurement
- `canopus trace replay` for postmortem debugging
- PyPI packaging and release pipeline
- Conda package (optional)
- Pre-commit hook configuration

### Phase 9 — Advanced workflow features ⏸

- Conditional step branching (`if:` conditions)
- Loop steps (iterate over capability list output)
- Parallel step execution
- Sub-workflow calls
- Workflow scheduling (`cron`-like)
- Artifact persistence

---

## Architecture readiness

| Concern | Ready? |
|---|---|
| Adding a remote model provider | ✅ — implement `ModelProvider` protocol |
| Adding a new native capability | ✅ — register in `register_all()` |
| Adding a legacy plugin | ✅ — drop `.py` file in plugins dir |
| Adding an MCP server | ✅ — add to config, `McpManager` handles the rest |
| Adding a new workflow step kind | ✅ — extend `WorkflowStepKind` + `StepExecutor` |
| Adding voice input | ⏸ — `voice/` modules not yet written |
| Policy enforcement on capabilities | ✅ — permission metadata exists; enforcement hooks present |
| Per-run trace inspection | ✅ — `canopus trace show <run-id>` |
| Memory injection into reasoning | ✅ — `ContextBuilder` + pipeline integration |

---

## Repository health

| Metric | Value |
|---|---|
| Test count | 516 passing, 1 skipped |
| mypy (strict) | 80 source files, zero errors |
| ruff | zero warnings |
| Python version | 3.12+ |
| License | MIT |
| Public release | None yet |
