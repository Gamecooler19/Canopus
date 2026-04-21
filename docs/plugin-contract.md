# Canopus Legacy Plugin Contract

Legacy plugins are single Python files you drop into `~/.canopus/plugins/`.
Canopus discovers and loads them automatically on startup, making their
capabilities available to the reasoning engine, CLI, and automation workflows.

---

## Where to put plugins

```
~/.canopus/plugins/
├── hello.py          ← discovered and loaded
├── my_browser.py     ← discovered and loaded
└── _helpers.py       ← skipped (underscore prefix)
```

- Any `.py` file is a candidate.
- Files whose names begin with `_` are **always skipped** (use them for shared
  helpers that you import from another plugin file).
- The load order is alphabetical by filename.

---

## Minimal plugin example

```python
# ~/.canopus/plugins/hello.py

PLUGIN_META = {
    "name": "hello",
    "description": "A friendly greeting plugin.",
}

def greet(inputs, ctx):
    name = inputs.get("name", "world")
    return {"message": f"Hello, {name}!"}

def capabilities():
    return [
        {
            "name": "hello.greet",
            "description": "Greet someone by name.",
            "handler": greet,
        }
    ]
```

That is all that is required. Canopus will:
1. Import the module.
2. Read `PLUGIN_META` for metadata.
3. Call `capabilities()` to discover what the plugin provides.
4. Register each capability into the global capability registry.

---

## `PLUGIN_META` reference

`PLUGIN_META` must be a `dict` at module level.

| Key           | Required | Default   | Description                              |
|---------------|----------|-----------|------------------------------------------|
| `name`        | **yes**  | —         | Unique plugin identifier (slug, no dots) |
| `description` | **yes**  | —         | One-line human-readable description      |
| `version`     | no       | `"0.1.0"` | Semantic version string                  |
| `author`      | no       | `""`      | Author name                              |
| `tags`        | no       | `[]`      | List of string tags for discovery        |

```python
PLUGIN_META = {
    "name": "text_tools",
    "description": "Local text transformation utilities.",
    "version": "1.0.0",
    "author": "Canopus Examples",
    "tags": ["text", "transform"],
}
```

---

## `capabilities()` reference

`capabilities()` must be a callable at module level that returns a **list of
dicts**. Each dict describes one capability.

| Key                  | Required | Default    | Description                                      |
|----------------------|----------|------------|--------------------------------------------------|
| `name`               | **yes**  | —          | Dot-namespaced name: `"<plugin>.<action>"`       |
| `description`        | **yes**  | —          | One-line description of what the capability does |
| `handler`            | **yes**  | —          | Callable — receives `(inputs: dict, ctx)` and returns `dict` |
| `tags`               | no       | `[]`       | List of string tags                              |
| `permissions`        | no       | `[]`       | List of permission strings (see below)           |
| `side_effect_level`  | no       | `"none"`   | `"none"` / `"low"` / `"medium"` / `"high"`      |
| `confirmation_policy`| no       | `"never"`  | `"never"` / `"smart"` / `"always"`              |
| `examples`           | no       | `[]`       | List of example invocation strings               |

### Handler signature

```python
def my_handler(inputs: dict, ctx) -> dict:
    ...
```

- `inputs` — the raw input payload as a dict (schema validated by the planner
  or the caller).
- `ctx` — a `CapabilityContext` object (or `None` in test contexts). Safe to
  ignore for simple plugins.
- Return a **dict** with the operation result. Any JSON-serialisable values
  are acceptable.

### Capability name convention

Use `<plugin_name>.<action>` — e.g. `text_tools.upper`, `hello.greet`.
Names must be globally unique across all registered capabilities.

---

## Permission strings

Declare permissions for any external resources your capability accesses.

| String              | Meaning                        |
|---------------------|--------------------------------|
| `"fs.read"`         | Read from the local filesystem |
| `"fs.write"`        | Write to the local filesystem  |
| `"network.http"`    | Outbound HTTP requests         |
| `"shell.exec"`      | Execute shell commands         |
| `"system.info"`     | Read system information        |
| `"email.read"`      | Access email (read)            |
| `"email.send"`      | Send email                     |
| `"calendar.read"`   | Read calendar data             |
| `"calendar.write"`  | Modify calendar data           |
| `"contacts.read"`   | Read contacts                  |
| `"process.list"`    | List running processes         |

---

## Side-effect levels and confirmation policy

Use these to help Canopus's policy layer decide whether to auto-run a
capability or ask the user first.

**`side_effect_level`**

| Value      | When to use                                              |
|------------|----------------------------------------------------------|
| `"none"`   | Read-only, no observable side effects                    |
| `"low"`    | Minor writes, easily reversible (e.g. append to a log)  |
| `"medium"` | Significant writes or external calls                     |
| `"high"`   | Destructive or irreversible actions                      |

**`confirmation_policy`**

| Value     | Behaviour                                                  |
|-----------|------------------------------------------------------------|
| `"never"` | Never ask the user — run automatically                     |
| `"smart"` | Ask only when the policy engine deems it risky             |
| `"always"`| Always ask the user before running                         |

---

## Full example with all fields

```python
# ~/.canopus/plugins/browser.py

PLUGIN_META = {
    "name": "browser",
    "description": "Open URLs in the default system browser.",
    "version": "1.0.0",
    "author": "me",
    "tags": ["web", "browser"],
}

import subprocess
import sys

def _open_url(inputs, ctx):
    url = inputs.get("url", "")
    if not url:
        return {"error": "No URL provided."}
    if sys.platform == "win32":
        subprocess.run(["start", url], shell=True, check=True)
    else:
        subprocess.run(["xdg-open", url], check=True)
    return {"opened": url}

def capabilities():
    return [
        {
            "name": "browser.open_url",
            "description": "Open a URL in the default system browser.",
            "handler": _open_url,
            "tags": ["browser", "web"],
            "permissions": ["network.http"],
            "side_effect_level": "medium",
            "confirmation_policy": "smart",
            "examples": [
                "open https://example.com in the browser",
                "browse to the Canopus docs",
            ],
        }
    ]
```

---

## Plugin load status

After discovery, each plugin has one of these statuses:

| Status    | Meaning                                                          |
|-----------|------------------------------------------------------------------|
| `loaded`  | All capabilities registered successfully                         |
| `partial` | Some capabilities failed validation; others were registered      |
| `invalid` | Plugin structure is wrong (missing `PLUGIN_META` or bad `capabilities()`) |
| `errored` | Python import failed (syntax error, import error, etc.)          |
| `skipped` | Duplicate plugin name — a file with the same `name` loaded first |

---

## CLI commands for plugins

```sh
# List all discovered plugins and their status
canopus plugin list

# Filter by status
canopus plugin list --status loaded
canopus plugin list --status errored

# Show details for a specific plugin
canopus plugin inspect hello

# Health summary: counts, failed plugins, warnings
canopus plugin doctor
```

---

## Testing a plugin capability

Use `canopus capability invoke` to run a capability interactively:

```sh
# Invoke with no input
canopus capability invoke hello.greet

# Invoke with a JSON input payload
canopus capability invoke hello.greet --input-json '{"name": "Alice"}'

# Compact output (no Syntax highlighting)
canopus capability invoke text_tools.upper --input-json '{"text": "hello"}' --raw
```

---

## Validation rules

Canopus validates every plugin on load. A plugin is rejected (or partially
loaded) if:

- `PLUGIN_META` is missing.
- `PLUGIN_META["name"]` or `PLUGIN_META["description"]` is missing.
- `capabilities` is not a callable.
- `capabilities()` does not return a list.
- A capability dict is missing `"name"`, `"description"`, or `"handler"`.
- `"handler"` is not callable.
- `"permissions"` contains an unknown permission string.
- `"side_effect_level"` or `"confirmation_policy"` has an invalid value.
- The capability name conflicts with an already-registered capability.

Validation errors are surfaced via `canopus plugin doctor` and written to the
trace log — they never crash the Canopus runtime.

---

## What is deferred

The following are **not yet implemented** and are planned for later phases:

- **MCP plugins** (`canopus/plugins/mcp/`) — Phase 4B.
- **Remote plugin install** (`canopus plugin install <url>`) — Phase 7.
- **Plugin sandboxing** — future hardening work.
- **Hot-reload** without restarting Canopus.
- **Plugin dependency declarations** (e.g. requiring a Python package).
