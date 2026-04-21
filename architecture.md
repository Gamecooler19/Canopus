# Canopus Architecture

## 1. Executive Summary

**Canopus** is a Python-first, CLI-native, plugin-driven personal AI assistant designed to operate as a serious local-first automation runtime rather than a chat wrapper.

It combines:

- **Voice control** for hands-free operation
- **Task automation** through deterministic tools and workflows
- **Intelligent context management** across conversations, tasks, files, and system state
- **Dual model execution** with both **local LLMs** and **remote LLM providers**
- **Two extensibility layers**:
  - **MCP-compatible tools/services** for modern interoperability
  - **Legacy file-based plugins** for dead-simple user extensibility

The relaunch should position Canopus not as “another assistant,” but as an **AI operating layer for the command line**: programmable, modular, privacy-aware, auditable, and capable of moving fluidly between simple commands, conversational reasoning, and multi-step automation.

The core idea is this:

> Canopus should feel like a local shell, an AI agent runtime, a plugin host, and a voice-enabled automation engine fused into one cohesive system.

---

## 2. Product Goals

### Primary goals

1. **CLI-first excellence**
   - No GUI dependency
   - Fast startup
   - Scriptable from terminals, shells, cron jobs, SSH sessions, and containers

2. **Model abstraction without lock-in**
   - Users choose local or remote models per task, profile, or policy
   - Same assistant behavior regardless of provider where possible

3. **Best-in-class extensibility**
   - Easy plugin development with a single Python file for simple cases
   - Richer capability model through MCP servers and structured tool contracts

4. **Operational trust**
   - Strong observability
   - Clear permissions
   - Reproducible actions
   - Safe automation boundaries

5. **Portfolio-grade technical ambition**
   - Architecture that is impressive, modern, and forward-looking
   - Strong enough to scale from solo developer demo to real-user deployment

### Non-goals

- Desktop UI
- Browser-based frontend
- Heavy cloud dependency for core flows
- Monolithic hardcoded tool system

---

## 3. High-Level Design Principles

### 3.1 Local-first, cloud-optional
Canopus should run fully on a local machine for privacy-sensitive users, while optionally enabling cloud models and cloud services for stronger reasoning, search, or collaboration.

### 3.2 Event-driven core
Internally, Canopus should behave like a small operating system. Components publish and consume typed events rather than directly entangling business logic.

Examples:
- `voice.transcript.ready`
- `intent.detected`
- `tool.invocation.requested`
- `memory.context.loaded`
- `workflow.step.completed`
- `safety.policy.denied`

This reduces coupling and makes tracing, testing, and future distributed execution easier.

### 3.3 Capability-oriented architecture
Everything Canopus can do should be represented as a **capability** rather than a special-case feature.

Examples:
- Browser access
- File system access
- Calendar access
- Email send/read
- Shell execution
- Knowledge retrieval
- Voice synthesis

Both MCP integrations and legacy plugins should be normalized into the same internal capability graph.

### 3.4 Deterministic execution around nondeterministic reasoning
LLMs may decide *what* should happen, but deterministic subsystems must control *how* it happens.

- LLM decides: “search notes, summarize, email result”
- Orchestrator decides: tool permissions, call ordering, retries, logging, confirmation thresholds

### 3.5 Security by isolation, not trust
Plugins and tools should not be trusted simply because they exist. Every capability should declare:
- permissions
- side effects
- required confirmation level
- local/remote execution constraints
- data sensitivity classification

---

## 4. Reference Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│                           Canopus CLI                              │
│   chat / run / voice / workflow / plugin / doctor / profile cmds   │
└─────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Session Runtime                            │
│  session state • config • event bus • context loader • tracing     │
└─────────────────────────────────────────────────────────────────────┘
                │
      ┌─────────┼─────────┬───────────────┬──────────────┐
      ▼         ▼         ▼               ▼              ▼
┌──────────┐┌──────────┐┌───────────┐┌──────────────┐┌──────────────┐
│ Voice I/O││ Reasoning││ Capability││ Memory & RAG ││ Workflow Eng.│
│ Pipeline ││ Engine   ││ Registry  ││ Layer        ││              │
└──────────┘└──────────┘└───────────┘└──────────────┘└──────────────┘
                  │           │               │              │
                  ▼           ▼               ▼              ▼
             ┌────────────────────────────────────────────────────┐
             │              Policy & Safety Layer                │
             │ authz • confirmations • redaction • guardrails    │
             └────────────────────────────────────────────────────┘
                                  │
                                  ▼
                     ┌─────────────────────────────┐
                     │ Tool / Plugin Execution Bus │
                     └─────────────────────────────┘
                         │                   │
                 ┌───────┴───────┐   ┌──────┴────────┐
                 ▼               ▼   ▼               ▼
           ┌──────────┐    ┌─────────────┐    ┌─────────────┐
           │MCP Tools │    │Legacy Plugin│    │Native Core  │
           │/ Servers │    │Adapters     │    │Capabilities │
           └──────────┘    └─────────────┘    └─────────────┘
```

---

## 5. Core Subsystems

## 5.1 CLI Runtime Layer

The CLI is the only user-facing surface. It should support both interactive and non-interactive operation.

### Command groups

```bash
canopus chat
canopus run "summarize my notes from today"
canopus voice
canopus workflow run morning-brief
canopus plugin list
canopus plugin doctor
canopus profile use local-private
canopus memory search "meeting with devops"
canopus trace show <run_id>
```

### Responsibilities
- Argument parsing and shell UX
- Interactive REPL mode
- Non-interactive one-shot mode
- Streaming output
- Voice session control
- Operator/debug/admin commands

### Recommended libraries
- `typer` for CLI ergonomics
- `rich` for terminal rendering
- `prompt_toolkit` for interactive shell experience

---

## 5.2 Session Runtime

Each invocation of Canopus should create a **session runtime**. This is the execution boundary for state, logs, permissions, and traceability.

### Responsibilities
- Load profile/configuration
- Resolve active model routing policy
- Initialize event bus
- Create run/session IDs
- Load context window and memory scope
- Maintain tool budget / token budget / latency budget
- Persist execution trace

### Key entities
- `UserProfile`
- `SessionContext`
- `RuntimePolicy`
- `ExecutionTrace`
- `CapabilityBindings`

This layer is the “kernel” of Canopus.

---

## 5.3 Reasoning Engine

The reasoning engine should be model-agnostic and centered around a **planner-executor-reflector** pattern.

### Recommended internal stages
1. **Interpretation**
   - parse user request
   - detect command vs question vs workflow
2. **Planning**
   - identify goals, required capabilities, safety level
3. **Execution**
   - invoke tools/workflows/plugins deterministically
4. **Reflection**
   - validate completeness, errors, or next actions
5. **Response synthesis**
   - format final answer for CLI/voice

### Why this matters
This creates a far more impressive architecture than a single “chat completion” loop. It shows Canopus as an **agentic runtime with control boundaries**, not just a chatbot.

### Model router
The reasoning engine should not hardcode any model vendor. Instead use a router that can choose:
- local small model for classification / intent detection
- larger local model for private reasoning
- remote premium model for high-complexity requests
- fallback remote model if local fails

### Providers to abstract
- local: Ollama, llama.cpp, vLLM-backed local endpoints
- remote: OpenAI-compatible APIs, Anthropic-style adapters, Groq/OpenRouter-style providers

### Internal interface

```python
class ModelProvider(Protocol):
    async def complete(self, request: ModelRequest) -> ModelResponse: ...
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...
```

---

## 5.4 Voice Pipeline

Voice is a first-class runtime, not a bolt-on.

### Stages
1. Wake/activation strategy
   - push-to-talk for v1
   - optional wake-word later
2. Speech-to-text
3. Utterance segmentation
4. Intent classification
5. Reasoning + action execution
6. Text-to-speech response

### Architecture rules
- Voice must feed the exact same session runtime as text input
- Voice should be interruptible
- Transcript and action trace should be stored together
- Voice mode should support local-private operation

### Provider abstraction
- STT providers: local Whisper/faster-whisper, remote APIs
- TTS providers: Piper, Coqui, system TTS, remote APIs

### Key design choice
Voice should not create a separate assistant path. It should simply become another **input/output transport** for the same orchestration core.

---

## 5.5 Capability Registry

The **capability registry** is the heart of extensibility.

Every native function, legacy plugin, and MCP tool becomes a normalized capability with metadata.

### Capability metadata example

```python
@dataclass
class CapabilitySpec:
    name: str
    description: str
    input_schema: dict
    output_schema: dict
    side_effect_level: Literal["none", "low", "medium", "high"]
    confirmation_policy: Literal["never", "smart", "always"]
    permissions: list[str]
    transport: Literal["native", "legacy_plugin", "mcp"]
    tags: list[str]
```

### Why this matters
This allows the planner to reason over tools uniformly and lets policy enforcement remain centralized.

---

## 5.6 Plugin System: Dual-Layer Extensibility

Canopus should support **two plugin systems** simultaneously.

### A. Legacy file-based plugins
A plugin can be as simple as a Python file dropped into a directory.

Example:
```text
~/.canopus/plugins/browser.py
```

This preserves the original magic of Canopus: *drop in one file, gain a power.*

#### Legacy plugin contract
- minimal manifest inferred from module exports
- optional explicit `PLUGIN_META`
- one or more callable tools exposed
- optional lifecycle hooks

Example:

```python
PLUGIN_META = {
    "name": "browser",
    "version": "1.0.0",
    "permissions": ["network"],
}

def capabilities():
    return [SearchWeb(), FetchPage()]
```

### B. MCP integration layer
Modern Canopus should also support MCP servers as first-class capability providers.

#### Why MCP matters
- standardized ecosystem interoperability
- external tool hosting
- future-proof integrations
- easier compatibility with emerging agent tooling ecosystems

### Unified adapter model
Both plugin types are converted into `CapabilitySpec + CapabilityExecutor` pairs.

```text
Legacy Plugin -> Legacy Adapter -> Capability Registry
MCP Server    -> MCP Adapter    -> Capability Registry
Native Tools  -> Native Adapter -> Capability Registry
```

### Plugin management commands
```bash
canopus plugin install ./my_plugin.py
canopus plugin list
canopus plugin inspect browser
canopus plugin enable browser
canopus plugin disable browser
canopus plugin sandbox browser
canopus mcp add filesystem http://localhost:4000
```

---

## 5.7 Native Core Capabilities

Some capabilities should be built-in and maintained as first-party modules.

### Suggested first-party modules
- `filesystem`
- `shell`
- `notes`
- `memory`
- `search`
- `browser`
- `calendar`
- `email`
- `clipboard`
- `scheduler`
- `knowledge`
- `notifications`

These should be implemented with the same interface as plugins so that the system remains coherent.

---

## 5.8 Memory and Context Architecture

This is one of the defining areas where Canopus should exceed expectations.

Canopus should use **layered memory**, not one giant history dump.

### Memory layers

#### 1. Ephemeral session context
- current conversation
- current tool results
- runtime decisions
- active task state

#### 2. Short-term working memory
- recent sessions
- unresolved tasks
- current project context
- temporary preferences

#### 3. Long-term structured memory
- user preferences
- recurring entities
- workflows
- stable facts explicitly stored

#### 4. Knowledge index / RAG memory
- documents
- notes
- files
- transcripts
- command histories
- plugin outputs

### Memory storage strategy
- SQLite or DuckDB for structured metadata
- local vector index for semantic retrieval
- filesystem-backed artifacts for transcripts and traces

### Context assembly pipeline
When a request arrives:
1. classify intent
2. determine context budget
3. retrieve relevant memory slices
4. retrieve relevant knowledge chunks
5. merge with active session state
6. redact sensitive content if required by policy
7. hand packaged context to reasoning engine

### Memory philosophy
Canopus should not “remember everything.” It should remember **what is useful, explainable, and permitted**.

---

## 5.9 Workflow Engine

Canopus should support reusable automations beyond ad hoc tool calls.

### Workflow types
- single-step command workflows
- multi-step declarative automations
- conditional flows
- scheduled routines
- human-in-the-loop approval flows

### Example workflow
```yaml
name: morning-brief
triggers:
  - type: manual
steps:
  - use: calendar.get_today
  - use: email.summarize_priority
  - use: notes.fetch_recent
  - use: model.summarize
  - use: tts.speak
```

### Why this matters
This turns Canopus into a reusable productivity engine, not just a conversational endpoint.

---

## 5.10 Policy, Safety, and Permissions Layer

Because Canopus can act on the user’s machine and accounts, policy enforcement is critical.

### Required controls
- per-capability permission declarations
- user approval for sensitive actions
- dry-run mode
- execution scopes
- secret isolation
- content redaction in logs
- side-effect risk classification

### Permission examples
- `fs.read`
- `fs.write`
- `network.http`
- `email.send`
- `calendar.write`
- `shell.exec`
- `contacts.read`

### Confirmation rules
- low-risk read operations: auto
- moderate-risk changes: smart confirmation
- high-risk external side effects: always confirm

### Example
A workflow that drafts an email may auto-run, but sending it should require confirmation unless policy explicitly allows otherwise.

---

## 5.11 Observability and Tracing

Enterprise-grade architecture requires world-class introspection.

### Every run should capture
- session ID
- request
- model used
- retrieved context sources
- tool calls
- latency per phase
- tokens/costs if remote
- errors
- final result
- approval prompts and decisions

### Outputs
- JSON structured logs
- human-readable traces
- replayable action history

### Commands
```bash
canopus trace show <run_id>
canopus trace export <run_id>
canopus doctor
```

This makes the system debuggable and portfolio-impressive.

---

## 6. Deployment and Runtime Modes

## 6.1 Runtime Profiles

Users should choose profiles instead of manually reconfiguring every subsystem.

### Example profiles
- `local-private`
  - local STT
  - local LLM
  - local TTS
  - no networked tools

- `hybrid-power`
  - local classifier
  - remote reasoning model
  - local memory
  - MCP tools enabled

- `remote-fast`
  - remote model and speech stack
  - lightweight local runtime

### Why profiles matter
Profiles make Canopus feel polished and production-grade while preserving flexibility.

---

## 6.2 Packaging Strategy

### Recommended distribution
- Python package via `uv`/`pip`
- optional standalone binary packaging later using PyInstaller or Nuitka
- optional Docker image for server mode or remote session hosting

### Entry points
```bash
pip install canopus-assistant
canopus --help
```

---

## 6.3 Data Layout

```text
~/.canopus/
├── config/
│   ├── profiles/
│   ├── policies/
│   └── secrets.toml
├── plugins/
│   ├── browser.py
│   └── notes.py
├── memory/
│   ├── memory.db
│   ├── vectors/
│   └── artifacts/
├── traces/
├── workflows/
├── cache/
└── logs/
```

---

## 7. Recommended Codebase Structure

```text
canopus/
├── cli/
│   ├── app.py
│   ├── commands/
│   └── renderers/
├── core/
│   ├── runtime.py
│   ├── events.py
│   ├── config.py
│   ├── profiles.py
│   ├── policies.py
│   └── tracing.py
├── reasoning/
│   ├── planner.py
│   ├── executor.py
│   ├── reflector.py
│   ├── router.py
│   └── prompts/
├── models/
│   ├── base.py
│   ├── local/
│   └── remote/
├── memory/
│   ├── store.py
│   ├── retrieval.py
│   ├── embeddings.py
│   └── context_builder.py
├── voice/
│   ├── stt.py
│   ├── tts.py
│   ├── vad.py
│   └── session.py
├── capabilities/
│   ├── registry.py
│   ├── specs.py
│   ├── executor.py
│   └── native/
├── plugins/
│   ├── legacy/
│   │   ├── loader.py
│   │   └── adapter.py
│   └── mcp/
│       ├── client.py
│       └── adapter.py
├── workflows/
│   ├── engine.py
│   ├── parser.py
│   └── scheduler.py
├── security/
│   ├── permissions.py
│   ├── sandbox.py
│   ├── secrets.py
│   └── redaction.py
├── storage/
│   ├── sqlite.py
│   ├── files.py
│   └── cache.py
└── tests/
```

---

## 8. Architectural Patterns to Use

## 8.1 Hexagonal architecture
Business logic should not depend directly on vendor SDKs.

- core logic depends on ports/interfaces
- adapters implement OpenAI, Ollama, Whisper, MCP, etc.

This is essential for keeping Canopus elegant over time.

## 8.2 Event bus pattern
Use a lightweight async event bus internally for decoupling and observability.

## 8.3 Strategy pattern
Use strategy selection for model routing, retrieval, and confirmation behavior.

## 8.4 Registry pattern
Use registries for capabilities, workflows, providers, and voice engines.

## 8.5 Policy-as-code
Permissions and action rules should live in structured policy files, not random if-statements.

---

## 9. Security Model

### Trust boundaries
1. User input
2. Model output
3. Plugin code
4. External tools/services
5. Local filesystem and secrets

### Core rules
- Never execute model-generated shell commands without policy checks
- Treat plugin outputs as untrusted until validated
- Store secrets separately from general config
- Redact secrets from traces
- Support offline-only mode
- Add plugin signature support later for trusted distribution

### Sandbox direction
For v1, sandbox by policy and subprocess isolation where practical.
For later versions, add stricter sandboxing for risky plugins.

---

## 10. Performance Strategy

### Design targets
- sub-second startup for CLI command mode where possible
- low-latency local intent classification
- streaming model output
- lazy load heavy providers
- cache embeddings and repeated retrieval
- parallelize retrieval + lightweight planning where safe

### Practical optimizations
- plugin manifest cache
- model capability cache
- prompt template cache
- optional background indexing service for large knowledge stores

---

## 11. Testing Strategy

### Test layers
- unit tests for providers, registry, policies
- contract tests for plugins and MCP adapters
- integration tests for workflows
- golden tests for prompt-driven planning behavior
- voice pipeline tests with fixtures
- trace replay tests

### Critical contract tests
Any plugin or MCP integration should be testable against a fixed capability contract.

---

## 12. Recommended Tech Stack

### Core
- Python 3.12+
- `typer`
- `rich`
- `pydantic`
- `anyio` or `asyncio`
- `httpx`
- `sqlalchemy` or lightweight SQLite layer

### Local AI
- `ollama` client and/or OpenAI-compatible local endpoint support
- `llama-cpp-python` optional
- `faster-whisper`
- `piper` or equivalent TTS

### Retrieval
- SQLite / DuckDB
- pluggable vector backend

### Packaging / tooling
- `uv`
- `pytest`
- `ruff`
- `mypy`
- `pre-commit`

---

## 13. Suggested Capability Lifecycle

1. Discover capability source
2. Validate manifest/contract
3. Normalize into internal spec
4. Register permissions and policy requirements
5. Expose to planner
6. Execute via adapter
7. Validate output
8. Trace result
9. Persist relevant memory/artifacts

This lifecycle should be identical whether the capability came from a first-party module, a `browser.py` file, or an MCP server.

---

## 14. Example Request Flow

### User request
```bash
canopus run "Open the latest project notes, summarize blockers, and draft an email to my team"
```

### Execution flow
1. CLI creates session runtime
2. Context builder loads recent project memory
3. Planner detects required capabilities:
   - notes access
   - summarization
   - email drafting
4. Policy layer marks email send as high side-effect, draft as medium
5. Notes capability retrieves artifacts
6. Model summarizes blockers
7. Email capability produces draft
8. Reflection checks whether the user asked to send or draft
9. Final response returns draft path + summary
10. Trace is written to disk

This is the experience Canopus should deliver consistently.

---

## 15. Architecture Decisions That Make Canopus Stand Out

### 15.1 Treat the assistant as an operating layer
Not a chatbot. Not a shell script launcher. A real orchestration runtime.

### 15.2 Unify old-school plugins with modern MCP
This creates a rare and compelling bridge between hacker simplicity and modern agent ecosystems.

### 15.3 Layered memory instead of naive chat history
This is how Canopus becomes genuinely assistant-like.

### 15.4 Policy-first automation
Strong control makes the system trustworthy enough for real-world actions.

### 15.5 CLI-native, not web-wrapper-first
This gives it a sharp identity and makes it feel engineered, not trend-following.

---

## 16. Phased Build Plan

## Phase 1: Core runtime foundation
- CLI shell
- session runtime
- config/profiles
- model router
- structured tracing

## Phase 2: Capability system
- native capability registry
- legacy plugin loader
- permission framework
- basic policies

## Phase 3: Memory + workflows
- structured memory store
- retrieval pipeline
- workflow engine
- artifact persistence

## Phase 4: Voice runtime
- STT/TTS abstractions
- push-to-talk mode
- voice session tracing

## Phase 5: MCP interoperability
- MCP client/adapter
- external server registration
- capability normalization

## Phase 6: hardening
- replayable traces
- plugin validation tools
- packaging polish
- performance tuning

---

## 17. Final Recommendation

Canopus should be built as a **modular AI runtime for command-line life**.

The strongest architecture is:

- **Python-only**
- **CLI-native**
- **event-driven core**
- **planner/executor/reflection orchestration**
- **dual model routing: local + remote**
- **unified capability registry**
- **MCP + legacy plugin adapters**
- **layered memory and retrieval**
- **policy-controlled automation**
- **deep tracing and observability**

That combination gives Canopus a distinct identity:

> a serious, hacker-friendly, enterprise-grade personal assistant runtime that feels years ahead of typical assistant demos.

