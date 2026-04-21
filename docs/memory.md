# Canopus Memory Subsystem

Canopus has a local-first memory layer that persists meaningful interactions, facts, and decisions across sessions. Memory is designed to be **deterministic, explainable, and inspectable** — there is no hidden magic. You can see everything that is stored and why.

---

## Storage location

All memory data is stored under the Canopus data directory:

```
~/.canopus/memory/
└── memory.db    ← SQLite database (WAL mode)
```

The database is created automatically on first use. No external service is required.

---

## Memory record model

Each stored memory is a `MemoryRecord` with the following fields:

| Field        | Type                | Description                                                       |
|--------------|---------------------|-------------------------------------------------------------------|
| `id`         | `str` (UUID4)       | Unique identifier, auto-generated                                 |
| `kind`       | `MemoryKind`        | Category: `conversation`, `fact`, `summary`, or `system`          |
| `content`    | `str`               | Main text body — the field full-text search runs against          |
| `tags`       | `list[str]`         | Free-form labels for filtering                                    |
| `source`     | `str`               | Where this memory came from: `user`, `conversation`, `run`, etc.  |
| `importance` | `float` (0.0–1.0)   | Relative priority used in retrieval scoring. Default `0.5`.       |
| `session_id` | `str \| None`       | Session that produced this record, if applicable                  |
| `run_id`     | `str \| None`       | Run that produced this record, if applicable                      |
| `metadata`   | `dict`              | Arbitrary structured payload (JSON-serialisable)                  |
| `created_at` | `datetime` (UTC)    | Timestamp of creation                                             |
| `updated_at` | `datetime` (UTC)    | Timestamp of last update                                          |

### Memory kinds

| Kind           | When used                                                   |
|----------------|-------------------------------------------------------------|
| `conversation` | User/assistant exchanges stored by `run` and `chat`         |
| `fact`         | Discrete factual statements stored explicitly by the user   |
| `summary`      | Condensed summaries of a session or topic                   |
| `system`       | Internal bookkeeping (reserved for future use)              |

---

## Retrieval approach (Phase 5A)

This phase uses **lexical + metadata retrieval** — no vector embeddings or external services.

### Storage layer (SQLite FTS5)

The `memories` table stores all records. A linked `memories_fts` virtual table (FTS5 with `unicode61` tokenizer) provides full-text search over the `content` column. Three SQLite triggers keep the FTS index in sync with inserts, updates, and deletes.

### Retrieval ranking

The `MemoryRetriever` applies a combined score:

```
score = (1 - recency_weight) × importance
      + recency_weight × recency_factor
```

The `recency_factor` is an exponential decay with a **7-day half-life**:

```
recency_factor = 2^(−age_days / 7)
```

The default `recency_weight` is `0.3`, so importance accounts for 70% of the score. Both weights are configurable when constructing `ContextBuilder` or `MemoryRetriever`.

### Query parameters (`MemoryQuery`)

| Field            | Description                                                       |
|------------------|-------------------------------------------------------------------|
| `text`           | FTS5 query string. Empty = recency-ordered fallback.              |
| `kinds`          | Filter to specific memory kinds. Empty = all.                     |
| `tags`           | Require at least one matching tag. Empty = no tag filter.         |
| `source`         | Filter by source string. `None` = no filter.                      |
| `session_id`     | Filter to a specific session. `None` = no filter.                 |
| `limit`          | Maximum records returned (default 20).                            |
| `min_importance` | Only return records with importance ≥ this value (default 0.0).   |
| `recency_weight` | Recency factor in ranking (default 0.3).                          |

FTS5 supports:
- Prefix search: `python*`
- Boolean: `python AND design`
- Phrase: `"local first"`
- Negation: `NOT server`

---

## Context builder

The `ContextBuilder` assembles a `MemoryContext` from a user request string, ready to inject into the reasoning pipeline:

```python
from canopus.memory.service import get_service

svc = get_service()
ctx = svc.build_context("tell me about our plugin architecture")
block = ctx.as_prompt_block()   # formatted string for prompt injection
```

The context block looks like:

```
[Memory context]
1. [fact] Decided to use SQLite for memory storage  tags=['db', 'design']
2. [conversation] User: how do plugins work? Assistant: …
```

Context output is bounded by a character budget (`max_chars=4000` by default) to stay within model token limits.

---

## Integration with `run` and `chat`

When `canopus run` or `canopus chat` execute a request:

1. **Before reasoning**: `build_context(request)` retrieves relevant memories. The memory block is injected into the model prompt.
2. **After a successful response**: `remember_exchange(user_input, assistant_response)` stores the exchange as a `conversation` memory record.

Both steps are **best-effort** — a memory failure never interrupts execution.

---

## CLI commands

```sh
# Store a memory manually
canopus memory add "Decided to use SQLite for all local storage" --kind fact --tags "db,decision"

# List recent memories
canopus memory list
canopus memory list --limit 10 --kind fact

# Search memories by text (FTS5)
canopus memory search "SQLite design"
canopus memory search "plugin architecture" --limit 5

# Inspect a single memory record
canopus memory inspect <full-id>
canopus memory inspect <first-8-chars>

# Delete a memory permanently
canopus memory forget <full-id> --yes
```

### `canopus memory add`

| Option         | Description                                          |
|----------------|------------------------------------------------------|
| `--kind`       | `conversation`, `fact`, `summary`, `system`          |
| `--tags`       | Comma-separated tags                                 |
| `--importance` | Float 0.0–1.0 (default `0.5`)                        |
| `--source`     | Source label (default `user`)                        |

### `canopus memory list`

| Option     | Description                              |
|------------|------------------------------------------|
| `--limit`  | Max records to show (default 20)         |
| `--kind`   | Filter by memory kind                    |
| `--source` | Filter by source string                  |

### `canopus memory search`

| Option    | Description               |
|-----------|---------------------------|
| `--limit` | Max results (default 10)  |
| `--kind`  | Filter by memory kind     |

---

## Architecture layers

```
MemoryService          ← primary public interface (service.py)
├── MemoryStore        ← SQLite persistence, schema, FTS triggers (store.py)
├── MemoryRetriever    ← ranking, filtering, search (retrieval.py)
└── ContextBuilder     ← assembles MemoryContext for pipeline injection (context_builder.py)

SqliteStore            ← low-level SQLite helper with WAL, migration, FTS (storage/sqlite.py)
```

Each layer has a single responsibility. The CLI and reasoning pipeline only interact with `MemoryService`. Storage SQL is entirely contained in `MemoryStore`.

---

## Intentionally deferred

The following are **not yet implemented** and are scoped to future phases:

- **Semantic / vector retrieval**: FTS5 is the retrieval baseline. Embedding-based similarity search can be added behind the `MemoryRetriever` interface without changing callers.
- **Memory summarisation**: Auto-summarising long session histories into compact `summary` records.
- **Memory eviction policy**: Currently the store grows unbounded. A TTL or importance-based eviction strategy may be added.
- **Shared / cross-device memory**: Memory is local-only. Sync support is deferred.
- **Structured fact extraction**: The planner does not yet extract discrete facts from model responses automatically.
- **Memory permissions / scoping**: All memories are currently global within the local store.
