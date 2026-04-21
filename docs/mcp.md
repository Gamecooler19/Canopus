# Canopus MCP Support

Canopus supports **MCP (Model Context Protocol) servers** as a first-class capability source alongside native capabilities and legacy Python plugins. MCP tools are normalized into the central capability registry, so the planner, executor, and CLI work identically regardless of whether a capability came from native code, a legacy plugin, or an MCP server.

---

## MCP config model

MCP servers are declared in `~/.canopus/config/config.toml` under the `[[mcp_servers]]` array:

```toml
[[mcp_servers]]
name        = "mock"
enabled     = true
transport   = "mock"
description = "Built-in mock server for development and testing."

[[mcp_servers]]
name        = "my-tools"
enabled     = true
transport   = "stdio"
command     = "/usr/local/bin/my-mcp-server"
args        = ["--verbose"]
env         = { MY_KEY = "value" }
description = "My custom MCP server."
```

### Field reference

| Field         | Required | Default   | Description                                                         |
|---------------|----------|-----------|---------------------------------------------------------------------|
| `name`        | **yes**  | —         | Unique identifier, also used as the capability namespace prefix     |
| `enabled`     | no       | `true`    | When `false`, server is skipped at startup                          |
| `transport`   | no       | `"mock"`  | Transport type: `"mock"` (in-process) or `"stdio"` (future)        |
| `command`     | no       | `null`    | Executable path for `stdio` transport                               |
| `args`        | no       | `[]`      | Additional CLI arguments for the server process                     |
| `env`         | no       | `{}`      | Extra environment variables for the server process                  |
| `description` | no       | `""`      | Human-readable summary shown in `canopus mcp list`                  |

---

## Transport strategy

All communication with MCP servers goes through the `McpTransport` protocol defined in `canopus/plugins/mcp/transports/__init__.py`. The protocol exposes three methods:

```
list_tools()         → list[McpToolSpec]
call_tool(name, args) → dict
close()
```

### Currently supported transports

| Value    | Status      | Description                                                  |
|----------|-------------|--------------------------------------------------------------|
| `"mock"` | **Working** | In-process transport for development/testing (no subprocess) |
| `"stdio"`| Stub        | External process via JSON-RPC over stdin/stdout (not yet implemented) |

The manager creates one transport per enabled server via `create_transport(config)`. Adding a new transport only requires adding a class that satisfies the `McpTransport` protocol and a new branch in `create_transport`.

---

## Mock/in-process transport

The `mock` transport (`canopus/plugins/mcp/transports/mock.py`) is the reference implementation and the real working baseline for this phase. It exposes three deterministic, side-effect-free tools:

| Tool name    | Description                                        | Key outputs                      |
|--------------|----------------------------------------------------|----------------------------------|
| `echo`       | Return the input text unchanged                    | `text`                           |
| `word_count` | Count words, characters, and lines in input text   | `words`, `characters`, `lines`, `non_empty_lines` |
| `now`        | Return the current UTC timestamp                   | `utc_iso`, `unix_timestamp`      |

Once a mock server named `"mock"` is configured, these become the capabilities `mock.echo`, `mock.word_count`, and `mock.now` in the registry.

---

## How MCP tools become capabilities

When the MCP manager initializes a server, it follows this pipeline:

```
McpServerConfig
    → create_transport(config)      # create the right transport type
    → McpClient(name, transport)    # wrap transport with error normalization
    → client.list_tools()           # get tool inventory
    → [for each tool]
        adapt(tool_spec, server_name, client)  # normalize into CapabilitySpec + handler
    → registry.register(spec, handler)         # register in central capability registry
```

After this, MCP tools are indistinguishable from native capabilities in the registry:

```python
spec = registry.get("mock.echo")
assert spec.transport == "mcp"   # only difference from "native"

handler = registry.get_handler("mock.echo")
result = handler({"text": "hello"}, ctx)  # same calling convention
```

The `McpToolSpec` (output of `list_tools`) maps to `CapabilitySpec` fields:

| `McpToolSpec` field    | `CapabilitySpec` field    | Notes                                             |
|------------------------|---------------------------|---------------------------------------------------|
| `name`                 | `name`                    | Prefixed: `"<server>.<tool>"`                     |
| `description`          | `description`             | Passed through                                    |
| `tags`                 | `tags`                    | Passed through                                    |
| `permissions`          | `permissions`             | Parsed from strings to `Permission` enum values   |
| `side_effect_level`    | `side_effect_level`       | Parsed from string to `SideEffectLevel` enum      |
| `confirmation_policy`  | `confirmation_policy`     | Parsed from string to `ConfirmationPolicy` enum   |
| `examples`             | `examples`                | Passed through                                    |
| —                      | `transport`               | Always `"mcp"` for MCP-sourced capabilities       |

---

## Inspecting MCP status from the CLI

```sh
# List all configured MCP servers and their connection status
canopus mcp list

# Filter by status
canopus mcp list --status connected
canopus mcp list --status failed

# Show details for a specific server (transport, tools, errors, warnings)
canopus mcp inspect mock

# Health summary: server counts, failures, warnings
canopus mcp doctor
```

Since MCP tools are normalized into the capability registry, they also appear in:

```sh
# Show all capabilities including MCP-sourced ones
canopus capability list

# Invoke an MCP-backed capability directly
canopus capability invoke mock.echo --input-json '{"text": "hello"}'
canopus capability invoke mock.word_count --input-json '{"text": "one two three"}'
```

---

## Server fault isolation

One failing MCP server never prevents other servers from loading. Each server's outcome is captured in an `McpServerRecord`:

| Status       | Meaning                                                              |
|--------------|----------------------------------------------------------------------|
| `connected`  | Server initialized and all tools registered successfully             |
| `partial`    | Server connected but some tools failed to normalize or register      |
| `failed`     | Server could not be connected (transport error, bad config, etc.)    |
| `disabled`   | Server is in config but `enabled = false`                            |

Run `canopus mcp doctor` to see which servers failed and why.

---

## Implementing the stdio transport (future)

The `StdioMcpTransport` class in `canopus/plugins/mcp/transports/stdio.py` is a well-documented stub. To implement it:

1. Launch the server process via `subprocess.Popen` with piped stdin/stdout.
2. Send a JSON-RPC `initialize` request and read the response.
3. Send a `tools/list` request to populate the tool inventory.
4. For `call_tool`, send a `tools/call` JSON-RPC request and parse the result.
5. On `close()`, send a `shutdown` notification and terminate the process.

The transport boundary means only `stdio.py` needs to change — no other file needs modification.

---

## What is deferred

- **Stdio transport implementation** — the stub is ready; the JSON-RPC wire protocol is not yet implemented.
- **MCP server auto-discovery** — servers must currently be declared explicitly in `config.toml`.
- **MCP server authentication** — no auth flow is implemented.
- **Tool schema validation** — `McpToolSpec` accepts tool definitions as-is; JSON Schema input validation is not enforced.
- **Streaming/async MCP calls** — the current execution model is synchronous.
