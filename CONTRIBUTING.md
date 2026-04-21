# Contributing to Canopus

> **Development is currently paused.** This guide documents the conventions used during
> active development and will apply again when work resumes.

Thank you for your interest in Canopus. This document explains how to set up the
development environment, what the coding standards are, and how contributions are
expected to be structured.

---

## Development environment setup

**Requirements:** Python 3.12+, `conda` or `uv`.

### With conda (recommended for development)

```bash
conda create -n canopus python=3.12
conda activate canopus
git clone https://github.com/Gamecooler19/Canopus.git
cd Canopus
pip install -e ".[dev]"
```

### With uv

```bash
git clone https://github.com/Gamecooler19/Canopus.git
cd Canopus
uv pip install -e ".[dev]"
```

Verify your setup:

```bash
canopus doctor
pytest
```

---

## Running the checks

All three must pass before any PR is merged.

```bash
# Tests
pytest

# Lint (ruff)
ruff check .

# Type-check (mypy strict)
mypy canopus

# Equivalent one-liner
ruff check . && mypy canopus && pytest
```

With conda:

```bash
conda run -n canopus python -m pytest
conda run -n canopus python -m ruff check .
conda run -n canopus python -m mypy canopus
```

---

## Coding standards

### Language and version

- Python 3.12+ only
- `from __future__ import annotations` at the top of every source file
- `datetime.UTC` instead of `datetime.timezone.utc`
- `StrEnum` for string enumerations

### Style and formatting

- Line length: **100 characters** (`ruff` enforces this)
- Import sorting: `ruff` enforces isort-compatible ordering
- No unused imports
- All `pytest.raises` calls must name a specific exception, not `Exception`

### Typing

- Type hints on all function signatures and return types
- Use `Protocol` for structural interfaces
- Use `pydantic.BaseModel` for validated data contracts
- Use `TypedDict` or `dataclass` where appropriate
- `TYPE_CHECKING` guards for circular imports
- `mypy` strict mode must pass with no errors

### Error handling

- All subsystems have explicit exception subclasses in their respective `errors.py`
- Errors are never swallowed silently in non-bootstrap code
- Bootstrap functions (CLI startup) catch and suppress to avoid crashing the CLI

### Naming

- Modules: `snake_case`
- Classes: `PascalCase`
- Functions and variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`

---

## Architecture discipline

Before making changes, read [architecture.md](architecture.md) and
[.github/copilot-instructions.md](.github/copilot-instructions.md).

**Hard rules:**

- All capabilities — whether native, legacy plugin, or MCP — must register into the
  `CapabilityRegistry`. Nothing bypasses it.
- The CLI must never contain business logic. Rendering and routing only.
- Core modules must not import from CLI modules.
- Plugin loading errors must never crash the CLI.
- Prompt strings must live under `canopus/reasoning/prompts/`, not scattered in files.
- The policy and permission layer must not be bypassed for risky actions.
- Tracing must be added alongside new execution paths, not as an afterthought.

**Do not:**

- Add frameworks not already in the dependency graph without discussing first
- Add a feature without a test
- Add a public interface without a docstring
- Hardcode one model provider anywhere in the codebase

---

## Adding a new capability

1. Create a handler function: `def my_capability(inputs: dict, ctx: CapabilityContext) -> dict`
2. Create a `CapabilitySpec` with name, description, permissions, and side-effect level
3. Register it in `canopus/capabilities/native/register.py` via `registry.register(spec, handler)`
4. Add tests in `tests/test_capabilities.py`

See existing native capabilities in `canopus/capabilities/native/` for reference.

---

## Adding a legacy plugin (for testing or examples)

Drop a `.py` file with a `CANOPUS_PLUGIN` dict and a `run()` function.
See [docs/plugin-contract.md](docs/plugin-contract.md) for the full contract.

---

## Adding a workflow

Add a `.yaml` file to `examples/workflows/` or document it in `docs/workflows.md`.
See [docs/workflows.md](docs/workflows.md) for the YAML schema.

---

## Tests

- All new modules must have corresponding tests
- Test files live in `tests/`, named `test_<module>.py`
- Use `pytest` fixtures and `tmp_path` for filesystem tests
- Use `MagicMock` for external service dependencies
- Use `EchoProvider` from `canopus.models.local.echo` for model-dependent tests
- Do not write tests that require network access or external services

---

## Branch and PR expectations

- Work on a feature branch: `feat/<name>`, `fix/<name>`, `docs/<name>`
- Keep PRs focused — one logical change per PR
- All checks must pass before requesting review
- Update `CHANGELOG.md` under `[Unreleased]` for any user-visible change
- Reference the relevant architecture phase in the PR description if applicable

---

## Reporting issues

Use [GitHub Issues](https://github.com/Gamecooler19/Canopus/issues).

For bugs, include:
- OS and Python version
- Full command and output
- Relevant config or plugin files (redact secrets)

For feature requests, describe the use case, not just the feature. Explain how it fits
the CLI-native, local-first, capability-oriented model.

For security issues, see [SECURITY.md](SECURITY.md).

---

## Scope discipline

Canopus has a deliberately narrow and deep focus. Before proposing changes, consider
whether the work:

1. Belongs in the CLI runtime (not a web service, not a GUI)
2. Works locally without requiring cloud credentials
3. Respects the capability registry as the single execution surface
4. Adds to the deterministic control layer, not to "agent magic"
5. Is testable and observable by default

When in doubt, a simpler, more modular, more typed solution is preferred.
