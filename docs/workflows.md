# Canopus Workflows

Workflows are reusable, multi-step automations in Canopus. Each workflow is a
YAML file that declares inputs and an ordered list of steps. The workflow
engine executes the steps in sequence, threading outputs from earlier steps
into later ones via a simple template syntax.

---

## Workflow file location

Workflow files live in:

```text
~/.canopus/workflows/
```

Files must have a `.yaml` or `.yml` extension. The filename stem (without
extension) is the workflow name used in CLI commands.

For development and examples, additional workflows ship under:

```text
examples/workflows/
```

---

## YAML format

```yaml
name: directory_summary          # Workflow name (defaults to filename stem)
description: Short description.  # Shown in `workflow list` and `workflow inspect`
tags:                            # Free-form labels for filtering
  - filesystem
  - summarisation

inputs:                          # Declared input parameters
  - name: path
    description: Directory path to summarise.
    required: true               # Workflow refuses to run without this
  - name: limit
    description: Max number of entries.
    required: false
    default: "50"                # Used when --input limit= is not supplied

steps:
  - id: list_dir                 # Unique step identifier (used in templates)
    kind: capability             # Step type (see below)
    description: List directory contents.
    capability: filesystem.list_dir
    inputs:
      path: "{{ inputs.path }}"  # Template expression
    on_failure: abort            # abort (default) or continue

  - id: summarise
    kind: model
    description: Summarise the listing.
    prompt: |
      Summarise this directory:
      {{ steps.list_dir.text }}
    on_failure: abort

  - id: result
    kind: output
    description: Final output.
    value: "{{ steps.summarise.text }}"
```

---

## Step types

### `capability`

Invokes a registered Canopus capability by name.

```yaml
- id: list_dir
  kind: capability
  capability: filesystem.list_dir   # Required: registered capability name
  inputs:                           # Resolved capability inputs
    path: "{{ inputs.path }}"
  on_failure: abort
```

The capability's output dict is stored under the step ID and accessible in
templates as `{{ steps.list_dir.<key> }}`. A convenience `text` key is
automatically added if not present in the capability's output.

### `model`

Runs a prompt through the active model provider (determined by the profile).

```yaml
- id: summarise
  kind: model
  prompt: |
    Summarise this content:
    {{ steps.previous_step.text }}
  on_failure: abort
```

Output keys:
- `text` — generated text
- `provider` — provider name (e.g. `"echo"`, `"ollama"`)
- `model` — model identifier
- `latency_ms` — generation time

### `memory_search`

Retrieves records from the Canopus memory store.

```yaml
- id: recall
  kind: memory_search
  query: "{{ inputs.topic }}"   # Optional search query
  on_failure: continue          # Don't abort if memory is empty
```

Output keys:
- `records` — list of raw memory record dicts
- `count` — number of records returned
- `block` — formatted prompt block ready for injection into a model step
- `text` — same as `block`

### `output`

Marks the workflow's final output. The `value` is resolved and stored as
`WorkflowResult.final_output`.

```yaml
- id: result
  kind: output
  value: "{{ steps.summarise.text }}"
```

### `set_var`

Resolves a template and stores the result. Useful for computing intermediate
values from earlier step outputs.

```yaml
- id: label
  kind: set_var
  value: "Summary for {{ inputs.name }}"
  output_key: title             # Optional: override the context key
```

Output keys:
- `value` — the resolved string
- `text` — same as `value`

---

## Template syntax

Templates are `{{ ... }}` expressions embedded in string fields:
- `prompt`
- `value`
- `query`
- `inputs.*` values in capability steps

### Supported expressions

| Expression | Resolves to |
|---|---|
| `{{ inputs.<name> }}` | A declared workflow input value |
| `{{ steps.<id>.<key> }}` | A key inside a previous step's output dict |
| `{{ steps.<id>.output }}` | The entire output dict (as string) |

### Rules

- Templates are resolved at step execution time, not at parse time.
- A step can only reference outputs of steps that have already run.
- An unknown input or step reference raises `WorkflowTemplatingError`.
- No `eval` or arbitrary Python is executed — resolution is purely dict lookup.

---

## Input passing

Inputs declared in the `inputs:` section can be:

- Passed via `--input key=value` on the CLI
- Left to use the declared `default` value
- Omitted if `required: false` and no default is needed

Required inputs without a value cause a `WorkflowValidationError` before any
steps execute.

---

## on_failure policy

Each step has an `on_failure` field:

| Value | Behaviour |
|---|---|
| `abort` (default) | Stop the workflow, record `WorkflowStatus.FAILED` |
| `continue` | Record the failure, proceed to next step, final status is `PARTIAL` |

Steps with `on_failure: continue` that fail do not contribute to the step
output context, so templates referencing their keys will raise a
`WorkflowTemplatingError` in subsequent steps.

---

## CLI commands

### `canopus workflow list`

Lists all discovered workflows in the configured directory.

```
canopus workflow list
```

### `canopus workflow inspect <name>`

Shows the full definition of a workflow: metadata, inputs, and step table.

```
canopus workflow inspect directory_summary
```

### `canopus workflow validate <name>`

Validates a workflow definition and reports any errors. Exits 0 if valid.

```
canopus workflow validate directory_summary
```

### `canopus workflow run <name>`

Runs a workflow. Accepts `--input key=value` pairs and an optional `--profile`.

```
canopus workflow run directory_summary --input path=/home/user/notes
canopus workflow run memory_brief --input query="Python architecture decisions"
canopus workflow run my_wf --input x=hello --input y=world --profile hybrid-power
```

---

## Example workflows

Two example workflows ship with Canopus:

### `directory_summary`

Lists a directory via the `filesystem.list_dir` capability, then asks the
model to summarise the contents.

```
canopus workflow run examples/workflows/directory_summary.yaml \
  --input path=/home/user/projects
```

Or if copied to `~/.canopus/workflows/`:

```
canopus workflow run directory_summary --input path=/home/user/projects
```

### `memory_brief`

Searches the memory store for relevant records and produces a concise daily brief.

```
canopus workflow run memory_brief --input query="recent decisions"
```

---

## Tracing

When a `TraceWriter` is provided (e.g. during a CLI session), the following
trace events are emitted:

| Event | Payload |
|---|---|
| `workflow.started` | `workflow_name`, `run_id`, `inputs` |
| `workflow.step.started` | `step_id`, `kind` |
| `workflow.step.completed` | `step_id`, `latency_ms` |
| `workflow.step.failed` | `step_id`, `error` |
| `workflow.completed` | `workflow_name`, `run_id`, `status`, `latency_ms` |

Traces are inspectable via `canopus trace show <run_id>`.

---

## Programmatic use

```python
from canopus.capabilities.registry import registry
from canopus.core.profiles import ProfileLoader
from canopus.models.router import ModelRouter
from canopus.workflows import WorkflowEngine, WorkflowLoader

profile = ProfileLoader().load("local-private")
provider = ModelRouter().get_provider(profile)
loader = WorkflowLoader(Path.home() / ".canopus" / "workflows")
wf = loader.load("directory_summary")

engine = WorkflowEngine(registry=registry, provider=provider)
result = engine.run(wf, inputs={"path": "/tmp/notes"}, profile=profile)

print(result.status)        # WorkflowStatus.COMPLETED
print(result.final_output)  # AI-generated summary text
print(result.latency_ms)    # Total execution time
```

---

## Deferred features

The following items are planned but not yet implemented:

- **Conditional branching** — `if:` conditions on steps
- **Loops** — iterating over a list capability output
- **Workflow scheduling** — cron-like triggers (`canopus workflow schedule`)
- **Parallel steps** — running independent steps concurrently
- **Sub-workflows** — calling one workflow from another
- **Artifact persistence** — saving step outputs to disk automatically
