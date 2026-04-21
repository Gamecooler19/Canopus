# Canopus Documentation

This directory contains the technical reference documentation for Canopus subsystems.

For project overview and governance, see the top-level files:

| Document | Description |
|---|---|
| [../README.md](../README.md) | Project overview, quick start, command reference |
| [../architecture.md](../architecture.md) | Full system architecture and design principles |
| [../PROJECT-STATUS.md](../PROJECT-STATUS.md) | Current development status and roadmap |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Development setup and contribution guide |
| [../SECURITY.md](../SECURITY.md) | Vulnerability reporting and security guidance |
| [../CHANGELOG.md](../CHANGELOG.md) | Change history |

---

## Subsystem references

| Document | Description |
|---|---|
| [plugin-contract.md](plugin-contract.md) | Legacy Python plugin API: metadata, `run()`, registration |
| [mcp.md](mcp.md) | MCP server integration: configuration, tool normalization |
| [memory.md](memory.md) | Memory subsystem: store, retrieval, context builder, service |
| [workflows.md](workflows.md) | Workflow engine: YAML schema, step types, template syntax, CLI |

---

## Architecture overview

Canopus is organized into these layers (see [architecture.md](../architecture.md) for full detail):

```
CLI (typer + rich)
  └─ commands: chat, run, profile, capability, plugin, mcp, memory, workflow, trace
Core runtime
  └─ config, profiles, session, tracing, error hierarchy
Reasoning pipeline
  └─ planner → executor → reflector
  └─ model router (local / remote)
Capability registry
  └─ native capabilities
  └─ legacy plugin adapter
  └─ MCP adapter
Memory subsystem
  └─ SQLite FTS5 store
  └─ retrieval + context builder
Workflow engine
  └─ YAML loader → executor → engine
Security layer
  └─ permissions, policies, secrets, redaction
```

---

## What is and is not implemented

See [PROJECT-STATUS.md](../PROJECT-STATUS.md) for the complete breakdown.

**Implemented:** CLI, profiles, tracing, model abstraction, reasoning pipeline,
capability registry, native capabilities, legacy plugins, MCP integration, memory
subsystem, workflow engine.

**Not yet implemented:** Remote model providers (Ollama, OpenAI, etc.), voice
pipeline (STT/TTS), workflow scheduling, production packaging.
