# Changelog

All notable changes to this project are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html),
though no public release has been made yet.

> **Development is currently paused.** See [PROJECT-STATUS.md](PROJECT-STATUS.md).

---

## [Unreleased]

This section accumulates all work since the project was started.
No public release has been tagged yet.

### Added — Phase 1: Foundation

- Project scaffolding with `pyproject.toml`, `hatchling` build backend, and `uv`-compatible dependency spec
- CLI entrypoint via `typer` with `canopus` console script
- Command groups: `profile`, `capability`, `trace`, `plugin`, `mcp`, `memory`, `workflow`
- Top-level commands: `chat`, `run`, `doctor`, `version`
- `AppConfig` and `AppPaths` with typed TOML-based configuration loading
- Three built-in runtime profiles: `local-private`, `hybrid-power`, `remote-fast`
- `ProfileSettings` model with `ModelRoutingPreference`, `VoiceSettings`, `NetworkPolicy`, `MemorySettings`
- User-defined TOML profile support (`~/.canopus/config/profiles/`)
- `SessionRuntime` and `RequestMode` execution boundary model
- Structured JSON tracing: `ExecutionTrace`, `TraceEvent`, `TraceWriter`
- `TraceWriter.from_session()` constructor with auto-path from session metadata
- Explicit exception hierarchy: `CanopusError`, `ConfigError`, `ProfileError`, `CapabilityError`, `PluginError`, `McpError`, `MemoryError`, `WorkflowError`, and variants
- `canopus doctor` health check command
- `canopus trace list` and `canopus trace show` commands
- `.gitignore` covering Python, environments, IDE files, secrets, and `~/.canopus/` data

### Added — Phase 2: Model and Reasoning Core

- `ModelProvider` protocol (structural typing, no forced inheritance)
- `ModelRequest` and `ModelResponse` Pydantic models
- `EchoProvider` — deterministic offline provider for development and testing
- `ModelRouter` — profile-driven provider selection (prefers local, optional remote fallback)
- Reasoning pipeline with `Planner`, `Executor`, and `Reflector` stages
- `run_pipeline()` top-level entry point for `canopus run` and `canopus chat`
- `ReflectionResult` with `final_response`, `reasoning_steps`, and `tool_calls`
- Centralized prompt management under `canopus/reasoning/prompts/`
- Streaming-friendly response design (provider interface ready for streaming)

### Added — Phase 3: Capability System

- `CapabilitySpec` model: name, description, tags, permissions, side-effect level, confirmation policy, transport
- `CapabilityResult` model: structured success/failure output
- `CapabilityRegistry` — global singleton with `register()`, `get()`, `get_handler()`, `list_all()`
- `CapabilityExecutor` — invokes capabilities with context, validates existence
- `CapabilityContext` — carries profile and trace writer into handler calls
- Native capabilities: `filesystem.list_dir`, `filesystem.read`, `system.now`
- `register_all()` — registers all native capabilities at CLI startup
- `canopus capability list` and `canopus capability inspect` commands
- `Permission`, `SideEffectLevel`, `ConfirmationPolicy` enums in `canopus.security.permissions`

### Added — Phase 4A: Legacy Plugin System

- `PluginLoader` — discovers `.py` files from `~/.canopus/plugins/`
- `PluginMetadata` — parsed from `CANOPUS_PLUGIN` dict in plugin files
- `PluginAdapter` — wraps legacy plugins as normalized `CapabilitySpec` + handler pairs
- `PluginManager` — coordinates loading, validation, and registration into the capability registry
- `initialize()` singleton factory for the plugin manager
- `canopus plugin list` and `canopus plugin doctor` commands
- Bootstrap integration in `canopus/cli/app.py`

### Added — Phase 4B: MCP Integration

- `McpClient` — connects to MCP servers over stdio or SSE transport
- `McpAdapter` — normalizes MCP tool descriptors into `CapabilitySpec` + handler pairs
- `McpManager` — coordinates client lifecycle and capability registration
- `McpServerConfig` — typed configuration model for server connection settings
- `initialize_mcp()` singleton factory
- `canopus mcp list` and `canopus mcp status` commands
- Bootstrap integration in `canopus/cli/app.py`

### Added — Phase 5A: Memory Subsystem

- `MemoryRecord` — Pydantic model with kind, content, tags, importance, session/run metadata
- `MemoryKind` enum: `conversation`, `fact`, `summary`, `system`
- `MemoryQuery` — typed search parameters with text, kind filter, tag filter, limit
- `MemoryContext` — assembled retrieval context with `as_prompt_block()` for LLM injection
- `MemoryStore` — SQLite FTS5 backend with WAL mode and unicode61 tokenizer
- `MemoryRetriever` — full-text search, recent-list, tag/kind filtering
- `ContextBuilder` — assembles `MemoryContext` from a request string
- `MemoryService` — unified service façade with `remember()`, `search()`, `forget()`, `build_context()`
- Singleton `initialize()` / `get_service()` / `reset_for_testing()` pattern
- `canopus memory add`, `list`, `search`, `get`, `forget`, `stats` commands
- Bootstrap integration in `canopus/cli/app.py`

### Added — Phase 5B: Workflow Engine

- `WorkflowStepKind` enum: `capability`, `model`, `memory_search`, `output`, `set_var`
- `WorkflowStepDef` — typed step definition with per-kind validation via `model_validator`
- `WorkflowDef` — complete workflow definition with unique-ID enforcement
- `WorkflowInputDef` — declared input parameter with required/default support
- `StepResult`, `WorkflowResult`, `WorkflowStatus` — structured execution results
- Template engine: `{{ inputs.<name> }}` and `{{ steps.<id>.<field> }}` resolution
- `WorkflowContext` — mutable run-time state holding inputs, step outputs, subsystem references
- `WorkflowLoader` — YAML discovery, `safe_load` parsing, Pydantic validation, `load_all()`
- `StepExecutor` — per-step dispatcher: capability, model, memory_search, output, set_var
- `WorkflowEngine` — full orchestration: input resolution, `on_failure` policy, trace events
- Trace events: `workflow.started`, `workflow.step.started`, `workflow.step.completed`, `workflow.step.failed`, `workflow.completed`
- `canopus workflow list`, `inspect`, `validate`, `run` commands
- Example workflows: `directory_summary.yaml`, `memory_brief.yaml` under `examples/workflows/`
- Bootstrap integration in `canopus/cli/app.py`
- Workflow documentation: `docs/workflows.md`

### Added — Repository governance

- Enterprise-grade `README.md` with full feature map, commands reference, and docs index
- `CHANGELOG.md` (this file)
- `LICENSE` (MIT)
- `CONTRIBUTING.md` with setup, coding standards, and scope guidance
- `SECURITY.md` with responsible disclosure guidance
- `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1)
- `PROJECT-STATUS.md` with honest phase-by-phase status
- `docs/index.md` — documentation hub
- `.github/ISSUE_TEMPLATE/bug_report.md`
- `.github/ISSUE_TEMPLATE/feature_request.md`
- `.github/pull_request_template.md`

### Fixed

- Import ordering in `canopus/cli/app.py` (`workflow_app` insertion in alphabetical position)
- Unused imports removed from `tests/test_workflows.py`
- `pytest.raises(Exception)` replaced with `pytest.raises(ValueError)` for Pydantic validation tests
- E501 line-length violations in test file corrected

---

[Unreleased]: https://github.com/Gamecooler19/Canopus/compare/HEAD...HEAD
