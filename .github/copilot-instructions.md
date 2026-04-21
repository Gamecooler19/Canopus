# Copilot Instructions for Canopus

## Mission

You are helping build **Canopus**, a **Python-only, CLI-native, plugin-based, voice-capable personal AI assistant runtime**.

This is **not** a web app, **not** a desktop GUI, and **not** a toy chatbot wrapper.

Canopus must feel like:

- a serious command-line assistant
- a local-first AI runtime
- an automation engine
- a plugin host
- a voice-enabled orchestration layer

The code must be written with the quality bar of a product that is both:

1. **portfolio-grade and technically impressive**, and
2. **real enough to be used by actual users**.

Use these instructions as the default source of truth when generating code, refactors, tests, or project structure.

---

## Core Product Identity

Canopus is being rebuilt as the modern successor to an earlier assistant with these defining traits:

- voice control
- task automation
- intelligent context management
- plugin-based extensibility
- support for both local and remote LLMs
- CLI/run-based interaction only

The new version must go beyond a normal assistant project by combining:

- **legacy drop-in Python plugins**
- **MCP integration**
- **local-first execution**
- **strong memory and context assembly**
- **policy-controlled actions**
- **deep observability and tracing**

---

## Non-Negotiable Constraints

### Hard requirements

- Use **Python 3.12+**
- Build a **CLI-first** application
- No frontend framework
- No browser UI
- No React, Electron, Tauri, Flask UI, Django UI, or web dashboard
- Keep the architecture modular and enterprise-grade
- Prefer async-friendly design where appropriate
- Prefer interfaces / protocols / adapters over direct vendor coupling
- Keep local and remote model providers pluggable
- Preserve support for **simple one-file legacy plugins**
- Add support for **MCP-based tools/services**
- Design for maintainability, testing, and observability from the beginning

### Do not do these things

- Do not collapse everything into one `main.py`
- Do not hardcode one model provider
- Do not hardcode prompt strings across random files
- Do not make tool execution bypass policy checks
- Do not mix CLI rendering logic with core business logic
- Do not make plugin APIs inconsistent across providers
- Do not build fragile “agent magic” without deterministic control boundaries
- Do not introduce unnecessary frameworks or microservices
- Do not create placeholder architecture that cannot actually be implemented

---

## The Architectural Standard

When making decisions, align to this architecture:

- **CLI runtime** for interactive and non-interactive use
- **session runtime** as execution boundary
- **reasoning engine** using planner → executor → reflector stages
- **model router** that chooses local or remote model providers
- **capability registry** as the normalized tool surface
- **dual plugin architecture**:
  - legacy Python file plugins
  - MCP adapters
- **memory subsystem** with layered memory
- **workflow engine** for multi-step automations
- **policy and permission layer** for risky actions
- **trace and observability layer** for every run
- **voice pipeline** as a transport over the same orchestration core

If code generation conflicts with this direction, prefer the architecture over speed.

---

## What Canopus Is

Canopus is a **command-line AI operating layer**.

It should support flows like:

- `canopus chat`
- `canopus run "summarize the latest notes and draft an email"`
- `canopus voice`
- `canopus workflow run morning-brief`
- `canopus plugin list`
- `canopus memory search "what did I decide yesterday about plugins?"`
- `canopus trace show <run_id>`

This means the codebase must support:

- normal chat-like interactions
- one-shot action execution
- reusable workflows
- memory retrieval
- voice sessions
- plugin discovery and tool execution
- traceable, permission-aware side effects

---

## Engineering Philosophy

### 1. Local-first, cloud-optional
Default architecture should work locally. Cloud providers are optional enhancements, not the foundation.

### 2. Deterministic execution around nondeterministic reasoning
LLMs may choose intentions or plans, but deterministic code must control:

- tool invocation
- validation
- permission checks
- retries
- side effects
- logging

### 3. Capability-oriented system design
Everything is a capability.

Examples:
- file read/write
- shell execution
- browser access
- note retrieval
- calendar operations
- email draft/send
- speech-to-text
- text-to-speech
- memory search

Legacy plugins, MCP tools, and native tools must all normalize into the same capability layer.

### 4. Ports and adapters
Core logic must not depend on one vendor. Use clean abstractions.

### 5. Traceability by default
Every serious run should be inspectable after execution.

---

## Expected Repository Shape

Use and preserve a structure close to this:

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

Do not introduce large deviations without a very strong reason.

---

## Implementation Order

When asked to build features, prefer this order unless the task explicitly says otherwise.

### Phase 1: foundation
- project scaffolding
- CLI entrypoint
- configuration loading
- profiles
- runtime/session model
- structured tracing
- error hierarchy

### Phase 2: model and reasoning core
- provider interfaces
- model router
- planner/executor/reflector skeleton
- prompt management
- streaming response pipeline

### Phase 3: capability system
- capability spec model
- capability registry
- native capability execution
- permission metadata
- confirmation policies

### Phase 4: plugin architecture
- legacy plugin loader
- legacy plugin adapters
- MCP client/adapters
- capability normalization across all sources

### Phase 5: memory and workflows
- memory store
- retrieval/context builder
- workflow definitions and engine
- artifact persistence

### Phase 6: voice
- STT abstraction
- TTS abstraction
- session integration
- push-to-talk runtime

### Phase 7: hardening
- tests
- diagnostics
- performance improvements
- replayable traces
- packaging polish

---

## Coding Standards

### Style
- Use clear, production-grade Python
- Prefer readability over cleverness
- Keep functions focused
- Keep modules cohesive
- Use meaningful type names
- Use type hints everywhere practical
- Use docstrings for public interfaces and non-obvious modules
- Prefer composition over inheritance unless inheritance is clearly superior

### Tooling
Use or prepare for:
- `uv`
- `ruff`
- `mypy`
- `pytest`
- `pre-commit`

### Typing
- Use `Protocol` and `ABC` for stable interfaces where needed
- Use `TypedDict`, `dataclass`, or `pydantic` models where appropriate
- Avoid untyped dict soup for important contracts

### Async
- Use async for I/O-heavy components
- Do not force async onto everything if it complicates local logic needlessly
- Keep sync/async boundaries explicit and clean

### Errors
Create explicit exception hierarchies for:
- configuration errors
- model provider errors
- capability registration errors
- plugin loading errors
- policy violations
- workflow execution errors

---

## Preferred Libraries

Use these unless there is a strong reason not to:

- `typer` for CLI
- `rich` for terminal rendering
- `pydantic` for validated configuration and models
- `httpx` for HTTP clients
- `anyio` or `asyncio` for concurrency
- `pytest` for tests

Possible optional additions:
- `prompt_toolkit` for REPL polish
- `faster-whisper` for local STT
- `piper` or similar for local TTS
- `sqlalchemy` or a lightweight SQLite abstraction for persistence

Avoid adding libraries casually. Keep the dependency graph intentional.

---

## Config and Profiles

Canopus must support runtime profiles such as:

- `local-private`
- `hybrid-power`
- `remote-fast`

These profiles should control:
- model routing
- provider selection
- speech engine selection
- capability policy
- network allowance
- memory behavior

Config should be explicit, typed, and discoverable.

Expected local data layout:

```text
~/.canopus/
├── config/
│   ├── profiles/
│   ├── policies/
│   └── secrets.toml
├── plugins/
├── memory/
├── traces/
├── workflows/
├── cache/
└── logs/
```

Do not scatter hidden state across arbitrary folders.

---

## Reasoning Engine Guidance

The reasoning system should be split into roles, not one blob.

### Planner
Responsible for:
- interpreting user intent
- choosing whether capabilities are needed
- proposing an execution plan
- estimating risk and side effects

### Executor
Responsible for:
- running the approved plan deterministically
- invoking capabilities
- gathering structured outputs
- handling retries and tool failures

### Reflector
Responsible for:
- checking if the result satisfies the goal
- deciding whether more steps are needed
- identifying safe next actions or missing information

### Router
Responsible for:
- selecting local vs remote provider
- selecting small vs large models
- selecting embedding provider if needed

Do not implement a vague “agent loop” with no structure. Keep these responsibilities explicit.

---

## Prompt Management Guidance

Prompt strings must not be randomly hardcoded across the codebase.

Do this instead:
- centralize prompt assets under `reasoning/prompts/`
- version important prompts
- keep prompt-building functions explicit
- separate system prompts, planning prompts, reflection prompts, and summarization prompts

If prompt templates require dynamic fields, make the parameters explicit and typed where practical.

---

## Capability System Requirements

The capability layer is one of the most important parts of Canopus.

Every capability must expose structured metadata similar to:

- name
- description
- tags
- input schema
- output schema
- permission requirements
- side-effect level
- confirmation policy
- source transport (`native`, `legacy_plugin`, `mcp`)

Capabilities should be easy for:
- the planner to discover
- the executor to invoke
- the policy layer to govern
- the trace system to log

### Treat these as first-class capabilities
- files
- shell
- browser/search
- memory search
- notes/documents
- calendar
- email
- clipboard
- workflows
- voice I/O

---

## Legacy Plugin System Requirements

This is a signature feature. Preserve the magic.

A user should be able to drop in something like:

```text
~/.canopus/plugins/browser.py
```

and have Canopus discover it.

### Design goals for legacy plugins
- very low friction
- one-file plugin possible
- optional metadata manifest
- simple registration contract
- safe loading and validation
- compatibility with the same capability registry used elsewhere

### Do not make legacy plugins second-class
They may be simple, but they must still integrate cleanly with:
- policy checks
- capability discovery
- tracing
- error reporting

### Provide developer ergonomics
Include good plugin examples and validation tools.

---

## MCP Integration Requirements

MCP support should be first-class, not an afterthought.

### Expectations
- MCP servers can be registered/configured
- exposed tools are normalized into capabilities
- capability metadata is preserved where possible
- transport-specific details stay behind adapters

### Important rule
The rest of the system should not need to care whether a capability came from:
- native code
- legacy Python plugin
- MCP server

That distinction belongs in adapters and metadata, not in core execution logic.

---

## Memory System Requirements

Canopus should use layered memory, not naive infinite chat history.

### Memory layers
1. session context
2. recent/working memory
3. long-term structured memory
4. knowledge/retrieval index

### Memory design goals
- retrieval should be explainable
- memory should be permission-aware
- stored facts should be useful and intentional
- long-term state should not become undocumented clutter

### Storage direction
- structured local store for memory metadata
- optional semantic retrieval index
- artifact/transcript storage on disk

When implementing retrieval, prioritize clean interfaces over committing too early to one vector backend.

---

## Workflow Engine Requirements

Workflows are reusable, multi-step automations.

They should support:
- manual execution
- composable steps
- deterministic sequencing
- conditional branching later if needed
- human confirmation for risky actions

Keep workflow representation simple and inspectable.

Do not hide critical execution logic only inside prompts.

---

## Voice System Requirements

Voice is an input/output transport over the same core runtime.

### Important rule
Voice must not create a separate assistant implementation.

The voice pipeline should reuse:
- the same session runtime
- the same reasoning engine
- the same capability system
- the same memory and tracing system

### Voice design goals
- push-to-talk first
- local STT/TTS possible
- interruptible sessions later
- transcript and action trace stored together

---

## Policy, Permissions, and Safety

Canopus may perform real actions. The system must be trustworthy.

### Every capability should declare
- permissions
- side-effect level
- confirmation policy
- optional sensitivity labels

### Examples of permissions
- `fs.read`
- `fs.write`
- `network.http`
- `shell.exec`
- `calendar.read`
- `calendar.write`
- `email.read`
- `email.send`

### Behavioral rules
- read-only actions can often auto-run
- risky write actions need confirmation or explicit policy permission
- shell execution must be guarded tightly
- model-generated instructions must never bypass policy
- traces must redact secrets and sensitive content when appropriate

Do not optimize away the policy layer.

---

## Observability Requirements

Enterprise-grade means excellent introspection.

### Each important run should record
- run/session ID
- user request
- selected model/provider
- retrieved context sources
- capability calls
- permissions checked
- confirmations requested
- timing/latency
- errors
- final result summary

### The trace system must support
- human-readable inspection
- structured machine-readable logs
- replay or postmortem potential later

Do not leave this for the end. Build trace hooks early.

---

## Testing Requirements

When generating code, include tests where reasonable.

### Required test categories over time
- unit tests for core models and registries
- plugin contract tests
- adapter tests for providers
- integration tests for workflows
- policy enforcement tests
- trace generation tests
- CLI command tests

### Important principle
If a component defines a contract, test the contract.

Examples:
- plugin metadata validation
- capability registration behavior
- policy confirmation behavior
- model router selection rules

---

## File-by-File Expectations

When creating files, make them substantial and intentional.

### Good file creation behavior
- include meaningful classes/functions
- add docstrings to public interfaces
- add typed models where needed
- wire modules into the package cleanly
- create tests alongside important modules

### Bad file creation behavior
- creating empty placeholder files with no useful behavior
- generating huge files that mix unrelated responsibilities
- stubbing large amounts of fake logic with TODOs only

TODOs are acceptable only when paired with real structure and clear boundaries.

---

## Refactoring Rules

When asked to refactor:
- preserve behavior unless explicitly changing it
- improve modularity and typing
- reduce vendor coupling
- keep public interfaces stable where possible
- add or update tests when behavior is important

Do not perform cosmetic refactors that damage the architecture.

---

## Documentation Rules

When adding documentation:
- keep it accurate to the actual code
- prefer concise but high-signal explanations
- explain extension points clearly
- document plugin and workflow examples well
- keep README-level docs practical

Good documentation is part of the product quality bar.

---

## What “Perfectly” Means for This Project

For this repository, “perfectly” means:

- architecture-first implementation
- modular, testable Python
- elegant CLI ergonomics
- local + remote model abstraction
- unified capabilities across native, legacy plugin, and MCP sources
- strong policy boundaries
- excellent traceability
- practical implementation, not gimmicks
- code that looks like a serious long-term project, not a hackathon demo

---

## If You Need to Choose Between Two Options

Prefer the option that is:

1. more modular
2. more typed
3. easier to test
4. less vendor-coupled
5. more aligned with CLI-native operation
6. more consistent with the capability-registry architecture
7. safer for real actions

---

## Default Build Behavior for Copilot Agent Mode

When implementing tasks in this repository, follow this workflow:

1. inspect relevant existing files first
2. preserve architecture consistency
3. create or update the smallest coherent set of files needed
4. wire code properly, not partially
5. add tests for important logic
6. keep docs in sync when architecture or developer workflows change
7. avoid speculative overengineering beyond the current task

---

## Final Instruction

Build Canopus like it is the flagship CLI assistant runtime in this portfolio.

It should feel:
- deeply engineered
- modern but not trend-chasing
- extensible without chaos
- intelligent without being magical
- safe enough to trust
- simple enough to hack on

When in doubt, make the codebase cleaner, more modular, more explainable, and more aligned with the architecture above.
