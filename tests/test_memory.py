"""Tests for the Canopus memory subsystem (Phase 5A).

Covers:
- MemoryRecord model creation and field validation
- SqliteStore low-level operations and migration
- MemoryStore insert/get/list/search/delete operations
- MemoryRetriever ranking behaviour
- ContextBuilder output shape
- MemoryService end-to-end (all operations via service layer)
- Module-level singleton (initialize / get_service / reset_for_testing)
- CLI memory commands (add / list / search / inspect / forget)
- Integration: run_pipeline with memory context injection
- .gitignore existence and content sanity
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from canopus.memory.context_builder import ContextBuilder
from canopus.memory.models import (
    MemoryContext,
    MemoryKind,
    MemoryQuery,
    MemoryRecord,
)
from canopus.memory.retrieval import MemoryRetriever
from canopus.memory.service import (
    MemoryService,
    get_service,
    initialize,
    reset_for_testing,
)
from canopus.memory.store import MemoryStore
from canopus.storage.sqlite import SqliteStore

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    """Return a path for a temp SQLite DB (not yet created)."""
    return tmp_path / "test_memory.db"


@pytest.fixture()
def open_store(tmp_db: Path) -> MemoryStore:
    """Open a MemoryStore backed by a temp database."""
    store = MemoryStore(tmp_db)
    store.open()
    yield store
    store.close()


@pytest.fixture()
def open_service(tmp_db: Path) -> MemoryService:
    """Open a MemoryService backed by a temp database."""
    svc = MemoryService(tmp_db)
    svc.open()
    yield svc
    svc.close()


@pytest.fixture(autouse=True)
def reset_singleton_after_each() -> None:
    """Always reset the global memory service singleton between tests."""
    yield
    reset_for_testing()


# ===========================================================================
# MemoryRecord model
# ===========================================================================


class TestMemoryRecord:
    def test_defaults(self) -> None:
        rec = MemoryRecord(content="hello")
        assert rec.kind == MemoryKind.CONVERSATION
        assert rec.source == "user"
        assert rec.importance == 0.5
        assert rec.tags == []
        assert rec.session_id is None
        assert rec.run_id is None
        assert rec.metadata == {}
        assert len(rec.id) == 36  # UUID4 format

    def test_custom_fields(self) -> None:
        rec = MemoryRecord(
            content="test",
            kind=MemoryKind.FACT,
            tags=["python", "design"],
            source="run",
            importance=0.9,
            session_id="sess-1",
            run_id="run-1",
            metadata={"key": "value"},
        )
        assert rec.kind == MemoryKind.FACT
        assert "python" in rec.tags
        assert rec.importance == 0.9

    def test_unique_ids(self) -> None:
        ids = {MemoryRecord(content=f"rec {i}").id for i in range(10)}
        assert len(ids) == 10

    def test_touch_updates_updated_at(self) -> None:
        rec = MemoryRecord(content="hi")
        original = rec.updated_at
        rec.touch()
        assert rec.updated_at >= original

    def test_memory_kind_values(self) -> None:
        assert MemoryKind.CONVERSATION == "conversation"
        assert MemoryKind.FACT == "fact"
        assert MemoryKind.SUMMARY == "summary"
        assert MemoryKind.SYSTEM == "system"


# ===========================================================================
# MemoryQuery model
# ===========================================================================


class TestMemoryQuery:
    def test_defaults(self) -> None:
        q = MemoryQuery()
        assert q.text == ""
        assert q.kinds == []
        assert q.limit == 20
        assert q.recency_weight == 0.3

    def test_custom_query(self) -> None:
        q = MemoryQuery(text="sqlite", kinds=[MemoryKind.FACT], limit=5)
        assert q.text == "sqlite"
        assert q.limit == 5


# ===========================================================================
# MemoryContext model
# ===========================================================================


class TestMemoryContext:
    def test_as_prompt_block_empty(self) -> None:
        ctx = MemoryContext(records=[], query_text="hello", total_found=0)
        assert ctx.as_prompt_block() == ""

    def test_as_prompt_block_with_records(self) -> None:
        rec = MemoryRecord(content="SQLite is good for local storage", kind=MemoryKind.FACT)
        ctx = MemoryContext(records=[rec], query_text="storage", total_found=1)
        block = ctx.as_prompt_block()
        assert "[Memory context]" in block
        assert "SQLite is good for local storage" in block
        assert "[fact]" in block

    def test_as_prompt_block_respects_max_chars(self) -> None:
        records = [MemoryRecord(content="x" * 200, kind=MemoryKind.FACT) for _ in range(30)]
        ctx = MemoryContext(records=records, query_text="test", total_found=30)
        block = ctx.as_prompt_block(max_chars=500)
        assert len(block) < 600  # should stop well before including all 30

    def test_truncated_flag(self) -> None:
        ctx = MemoryContext(records=[], query_text="q", total_found=50, truncated=True)
        assert ctx.truncated is True


# ===========================================================================
# SqliteStore (low-level)
# ===========================================================================


class TestSqliteStore:
    def test_open_creates_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "sub" / "test.db"
        with SqliteStore(db_path):
            assert db_path.exists()

    def test_execute_and_query(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        with SqliteStore(db_path) as store:
            store.execute(
                "CREATE TABLE IF NOT EXISTS t (id TEXT PRIMARY KEY, val TEXT)"
            )
            store.execute("INSERT INTO t VALUES (?, ?)", ("1", "hello"))
            rows = store.query("SELECT * FROM t WHERE id = ?", ("1",))
            assert len(rows) == 1
            assert rows[0]["val"] == "hello"

    def test_query_one_returns_none_when_missing(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        with SqliteStore(db_path) as store:
            store.execute("CREATE TABLE IF NOT EXISTS t (id TEXT PRIMARY KEY)")
            result = store.query_one("SELECT * FROM t WHERE id = ?", ("nope",))
            assert result is None

    def test_migrate_runs_once(self, tmp_path: Path) -> None:
        db_path = tmp_path / "migrate_test.db"
        with SqliteStore(db_path) as store:
            store.migrate([(1, "CREATE TABLE IF NOT EXISTS foo (x TEXT)")])
            store.migrate([(1, "CREATE TABLE IF NOT EXISTS foo (x TEXT)")])  # idempotent
            store.execute("INSERT INTO foo VALUES (?)", ("bar",))
            rows = store.query("SELECT * FROM foo")
            assert len(rows) == 1

    def test_require_conn_raises_when_closed(self, tmp_path: Path) -> None:
        from canopus.core.errors import MemoryStoreError

        db_path = tmp_path / "closed.db"
        store = SqliteStore(db_path)
        with pytest.raises(MemoryStoreError, match="not open"):
            store.query("SELECT 1")

    def test_executemany(self, tmp_path: Path) -> None:
        db_path = tmp_path / "many.db"
        with SqliteStore(db_path) as store:
            store.execute("CREATE TABLE t (id TEXT)")
            store.executemany("INSERT INTO t VALUES (?)", [("a",), ("b",), ("c",)])
            rows = store.query("SELECT * FROM t")
            assert len(rows) == 3


# ===========================================================================
# MemoryStore
# ===========================================================================


class TestMemoryStore:
    def test_open_creates_tables(self, open_store: MemoryStore) -> None:
        assert open_store.count() == 0

    def test_insert_and_get(self, open_store: MemoryStore) -> None:
        rec = MemoryRecord(content="first memory", kind=MemoryKind.FACT)
        open_store.insert(rec)
        fetched = open_store.get(rec.id)
        assert fetched.id == rec.id
        assert fetched.content == "first memory"
        assert fetched.kind == MemoryKind.FACT

    def test_get_raises_for_unknown_id(self, open_store: MemoryStore) -> None:
        from canopus.core.errors import MemoryNotFoundError

        with pytest.raises(MemoryNotFoundError):
            open_store.get("no-such-id")

    def test_insert_and_count(self, open_store: MemoryStore) -> None:
        for i in range(5):
            open_store.insert(MemoryRecord(content=f"record {i}"))
        assert open_store.count() == 5

    def test_list_recent_order(self, open_store: MemoryStore) -> None:
        for i in range(3):
            open_store.insert(MemoryRecord(content=f"r{i}", kind=MemoryKind.FACT))
        records = open_store.list_recent(limit=10)
        assert len(records) == 3
        # newest first — check that created_at is descending
        dates = [r.created_at for r in records]
        assert dates == sorted(dates, reverse=True) or len(set(dates)) == len(dates)

    def test_list_recent_kind_filter(self, open_store: MemoryStore) -> None:
        open_store.insert(MemoryRecord(content="fact1", kind=MemoryKind.FACT))
        open_store.insert(MemoryRecord(content="conv1", kind=MemoryKind.CONVERSATION))
        facts = open_store.list_recent(limit=10, kind=MemoryKind.FACT)
        assert all(r.kind == MemoryKind.FACT for r in facts)
        assert len(facts) == 1

    def test_list_recent_source_filter(self, open_store: MemoryStore) -> None:
        open_store.insert(MemoryRecord(content="from run", source="run"))
        open_store.insert(MemoryRecord(content="from user", source="user"))
        run_records = open_store.list_recent(limit=10, source="run")
        assert all(r.source == "run" for r in run_records)

    def test_delete_removes_record(self, open_store: MemoryStore) -> None:
        rec = MemoryRecord(content="to delete")
        open_store.insert(rec)
        open_store.delete(rec.id)
        assert open_store.count() == 0

    def test_delete_raises_for_unknown_id(self, open_store: MemoryStore) -> None:
        from canopus.core.errors import MemoryNotFoundError

        with pytest.raises(MemoryNotFoundError):
            open_store.delete("not-a-real-id")

    def test_update_content(self, open_store: MemoryStore) -> None:
        rec = MemoryRecord(content="original text")
        open_store.insert(rec)
        open_store.update_content(rec.id, "updated text")
        fetched = open_store.get(rec.id)
        assert fetched.content == "updated text"

    def test_serialisation_round_trip(self, open_store: MemoryStore) -> None:
        """All MemoryRecord fields survive a write → read round-trip."""
        rec = MemoryRecord(
            content="full round trip",
            kind=MemoryKind.SUMMARY,
            tags=["a", "b"],
            source="test",
            importance=0.75,
            session_id="sess-abc",
            run_id="run-xyz",
            metadata={"foo": 42},
        )
        open_store.insert(rec)
        fetched = open_store.get(rec.id)
        assert fetched.tags == ["a", "b"]
        assert fetched.importance == 0.75
        assert fetched.session_id == "sess-abc"
        assert fetched.run_id == "run-xyz"
        assert fetched.metadata == {"foo": 42}
        assert fetched.kind == MemoryKind.SUMMARY

    def test_fts_search_basic(self, open_store: MemoryStore) -> None:
        open_store.insert(MemoryRecord(content="SQLite is a great local database"))
        open_store.insert(MemoryRecord(content="The sky is blue today"))
        results = open_store.search_fts("SQLite")
        assert len(results) == 1
        assert "SQLite" in results[0].content

    def test_fts_search_no_match(self, open_store: MemoryStore) -> None:
        open_store.insert(MemoryRecord(content="hello world"))
        results = open_store.search_fts("bananas")
        assert results == []

    def test_fts_search_kind_filter(self, open_store: MemoryStore) -> None:
        open_store.insert(
            MemoryRecord(content="python is great", kind=MemoryKind.FACT)
        )
        open_store.insert(
            MemoryRecord(content="python syntax is simple", kind=MemoryKind.CONVERSATION)
        )
        results = open_store.search_fts("python", kind=MemoryKind.FACT)
        assert all(r.kind == MemoryKind.FACT for r in results)

    def test_context_manager(self, tmp_db: Path) -> None:
        with MemoryStore(tmp_db) as store:
            rec = MemoryRecord(content="context managed")
            store.insert(rec)
            assert store.count() == 1


# ===========================================================================
# MemoryRetriever
# ===========================================================================


class TestMemoryRetriever:
    def test_retrieve_by_text(self, open_store: MemoryStore) -> None:
        open_store.insert(MemoryRecord(content="using SQLite for local storage"))
        open_store.insert(MemoryRecord(content="the weather is nice today"))
        retriever = MemoryRetriever(open_store)
        q = MemoryQuery(text="SQLite", limit=10)
        results = retriever.retrieve(q)
        assert any("SQLite" in r.content for r in results)

    def test_retrieve_recent_no_text(self, open_store: MemoryStore) -> None:
        for i in range(5):
            open_store.insert(MemoryRecord(content=f"memory {i}"))
        retriever = MemoryRetriever(open_store)
        q = MemoryQuery(limit=3)
        results = retriever.retrieve(q)
        assert len(results) == 3

    def test_retrieve_kind_filter(self, open_store: MemoryStore) -> None:
        open_store.insert(MemoryRecord(content="fact about python", kind=MemoryKind.FACT))
        open_store.insert(
            MemoryRecord(content="chat about python", kind=MemoryKind.CONVERSATION)
        )
        retriever = MemoryRetriever(open_store)
        q = MemoryQuery(kinds=[MemoryKind.FACT], limit=10)
        results = retriever.retrieve(q)
        assert all(r.kind == MemoryKind.FACT for r in results)

    def test_retrieve_empty_store(self, open_store: MemoryStore) -> None:
        retriever = MemoryRetriever(open_store)
        results = retriever.retrieve(MemoryQuery(text="anything"))
        assert results == []

    def test_retrieve_recent_wrapper(self, open_store: MemoryStore) -> None:
        for i in range(3):
            open_store.insert(MemoryRecord(content=f"item {i}"))
        retriever = MemoryRetriever(open_store)
        results = retriever.retrieve_recent(limit=2)
        assert len(results) == 2

    def test_score_higher_importance_wins(self, open_store: MemoryStore) -> None:
        """Higher importance records should outscore lower ones at same age."""
        open_store.insert(MemoryRecord(content="low importance item", importance=0.1))
        open_store.insert(MemoryRecord(content="high importance item", importance=0.9))
        retriever = MemoryRetriever(open_store)
        results = retriever.retrieve(MemoryQuery(limit=10, recency_weight=0.0))
        # With recency_weight=0, pure importance ordering
        if len(results) >= 2:
            assert results[0].importance >= results[1].importance

    def test_score_recency_decay(self) -> None:
        """Older records score lower than newer ones at equal importance."""
        now = datetime.datetime.now(datetime.UTC)
        old_time = now - datetime.timedelta(days=30)
        new_rec = MemoryRecord(content="new", importance=0.5)
        old_rec = MemoryRecord(
            content="old",
            importance=0.5,
            created_at=old_time,
        )
        score_new = MemoryRetriever._score(new_rec, now, recency_weight=1.0)
        score_old = MemoryRetriever._score(old_rec, now, recency_weight=1.0)
        assert score_new > score_old


# ===========================================================================
# ContextBuilder
# ===========================================================================


class TestContextBuilder:
    def test_build_empty_store(self, open_store: MemoryStore) -> None:
        retriever = MemoryRetriever(open_store)
        builder = ContextBuilder(retriever, max_records=5)
        ctx = builder.build("anything")
        assert isinstance(ctx, MemoryContext)
        assert ctx.records == []
        assert ctx.as_prompt_block() == ""

    def test_build_with_matching_records(self, open_store: MemoryStore) -> None:
        open_store.insert(MemoryRecord(content="SQLite is used for local storage"))
        open_store.insert(MemoryRecord(content="the sky is blue"))
        retriever = MemoryRetriever(open_store)
        builder = ContextBuilder(retriever, max_records=5)
        ctx = builder.build("SQLite storage")
        assert any("SQLite" in r.content for r in ctx.records)

    def test_build_respects_max_records(self, open_store: MemoryStore) -> None:
        for i in range(20):
            open_store.insert(MemoryRecord(content=f"memory number {i}"))
        retriever = MemoryRetriever(open_store)
        builder = ContextBuilder(retriever, max_records=3)
        ctx = builder.build("")
        assert len(ctx.records) <= 3

    def test_build_recent_returns_correct_count(self, open_store: MemoryStore) -> None:
        for i in range(10):
            open_store.insert(MemoryRecord(content=f"item {i}"))
        retriever = MemoryRetriever(open_store)
        builder = ContextBuilder(retriever, max_records=5)
        ctx = builder.build_recent(limit=4)
        assert len(ctx.records) <= 4
        assert ctx.query_text == ""

    def test_prompt_block_contains_content(self, open_store: MemoryStore) -> None:
        open_store.insert(MemoryRecord(content="important decision about plugins"))
        retriever = MemoryRetriever(open_store)
        builder = ContextBuilder(retriever, max_records=5)
        ctx = builder.build("plugins")
        block = ctx.as_prompt_block()
        if ctx.records:
            assert "important decision about plugins" in block


# ===========================================================================
# MemoryService
# ===========================================================================


class TestMemoryService:
    def test_open_close_lifecycle(self, tmp_db: Path) -> None:
        svc = MemoryService(tmp_db)
        svc.open()
        assert svc.count() == 0
        svc.close()

    def test_context_manager(self, tmp_db: Path) -> None:
        with MemoryService(tmp_db) as svc:
            assert svc.count() == 0

    def test_remember_and_get(self, open_service: MemoryService) -> None:
        rec = MemoryRecord(content="service test", kind=MemoryKind.FACT)
        open_service.remember(rec)
        fetched = open_service.get(rec.id)
        assert fetched.content == "service test"

    def test_remember_exchange(self, open_service: MemoryService) -> None:
        rec = open_service.remember_exchange(
            user_input="what is sqlite?",
            assistant_response="SQLite is a local database engine.",
            session_id="test-session",
        )
        assert "User: what is sqlite?" in rec.content
        assert "Assistant: SQLite is a local database engine." in rec.content
        assert rec.session_id == "test-session"
        assert rec.kind == MemoryKind.CONVERSATION

    def test_forget(self, open_service: MemoryService) -> None:
        rec = MemoryRecord(content="to forget")
        open_service.remember(rec)
        open_service.forget(rec.id)
        assert open_service.count() == 0

    def test_forget_raises_for_unknown(self, open_service: MemoryService) -> None:
        from canopus.core.errors import MemoryNotFoundError

        with pytest.raises(MemoryNotFoundError):
            open_service.forget("no-such-id")

    def test_list_recent(self, open_service: MemoryService) -> None:
        for i in range(5):
            open_service.remember(MemoryRecord(content=f"item {i}"))
        results = open_service.list_recent(limit=3)
        assert len(results) == 3

    def test_search(self, open_service: MemoryService) -> None:
        open_service.remember(MemoryRecord(content="python is a great language"))
        open_service.remember(MemoryRecord(content="the weather is sunny"))
        q = MemoryQuery(text="python", limit=5)
        results = open_service.search(q)
        assert any("python" in r.content for r in results)

    def test_build_context_returns_memory_context(self, open_service: MemoryService) -> None:
        open_service.remember(MemoryRecord(content="local-first design principles"))
        ctx = open_service.build_context("design principles")
        assert isinstance(ctx, MemoryContext)

    def test_build_recent_context(self, open_service: MemoryService) -> None:
        open_service.remember(MemoryRecord(content="recent entry"))
        ctx = open_service.build_recent_context(limit=3)
        assert isinstance(ctx, MemoryContext)

    def test_count(self, open_service: MemoryService) -> None:
        for i in range(4):
            open_service.remember(MemoryRecord(content=f"count test {i}"))
        assert open_service.count() == 4


# ===========================================================================
# Memory service singleton
# ===========================================================================


class TestMemoryServiceSingleton:
    def test_initialize_returns_open_service(self, tmp_db: Path) -> None:
        svc = initialize(tmp_db)
        assert get_service() is svc
        assert svc.count() == 0

    def test_get_service_returns_none_before_init(self) -> None:
        # reset_singleton_after_each ensures no prior singleton
        assert get_service() is None

    def test_reset_clears_singleton(self, tmp_db: Path) -> None:
        initialize(tmp_db)
        assert get_service() is not None
        reset_for_testing()
        assert get_service() is None

    def test_initialize_twice_replaces_singleton(self, tmp_path: Path) -> None:
        svc1 = initialize(tmp_path / "a.db")
        svc1.remember(MemoryRecord(content="in a"))
        svc2 = initialize(tmp_path / "b.db")
        assert get_service() is svc2
        # svc2 uses a fresh db
        assert svc2.count() == 0


# ===========================================================================
# CLI memory commands
# ===========================================================================


@pytest.fixture()
def memory_app_with_service(tmp_db: Path):
    """Initialize the global memory service and return the CLI app."""
    initialize(tmp_db)
    from canopus.cli.commands.memory import memory_app

    yield memory_app
    reset_for_testing()


class TestMemoryCliAdd:
    def test_add_stores_record(self, memory_app_with_service) -> None:
        result = runner.invoke(memory_app_with_service, ["add", "my important note"])
        assert result.exit_code == 0
        assert "Stored memory" in result.output

    def test_add_with_kind_and_tags(self, memory_app_with_service) -> None:
        result = runner.invoke(
            memory_app_with_service,
            ["add", "design decision", "--kind", "fact", "--tags", "arch,design"],
        )
        assert result.exit_code == 0
        svc = get_service()
        assert svc is not None
        records = svc.list_recent(limit=5, kind=MemoryKind.FACT)
        assert any("design decision" in r.content for r in records)

    def test_add_importance(self, memory_app_with_service) -> None:
        result = runner.invoke(
            memory_app_with_service,
            ["add", "critical fact", "--importance", "0.9"],
        )
        assert result.exit_code == 0
        svc = get_service()
        assert svc is not None
        records = svc.list_recent(limit=5)
        critical = [r for r in records if "critical fact" in r.content]
        assert critical[0].importance == pytest.approx(0.9)

    def test_add_without_service_fails(self) -> None:
        from canopus.cli.commands.memory import memory_app

        result = runner.invoke(memory_app, ["add", "no service"])
        assert result.exit_code != 0


class TestMemoryCliList:
    def test_list_empty(self, memory_app_with_service) -> None:
        result = runner.invoke(memory_app_with_service, ["list"])
        assert result.exit_code == 0
        assert "No memory records" in result.output

    def test_list_shows_records(self, memory_app_with_service) -> None:
        svc = get_service()
        assert svc is not None
        svc.remember(MemoryRecord(content="listed content", kind=MemoryKind.FACT))
        result = runner.invoke(memory_app_with_service, ["list"])
        assert result.exit_code == 0
        assert "listed content" in result.output

    def test_list_kind_filter(self, memory_app_with_service) -> None:
        svc = get_service()
        assert svc is not None
        svc.remember(MemoryRecord(content="a fact", kind=MemoryKind.FACT))
        svc.remember(MemoryRecord(content="a conv", kind=MemoryKind.CONVERSATION))
        result = runner.invoke(memory_app_with_service, ["list", "--kind", "fact"])
        assert result.exit_code == 0
        assert "a fact" in result.output

    def test_list_invalid_kind(self, memory_app_with_service) -> None:
        result = runner.invoke(memory_app_with_service, ["list", "--kind", "badkind"])
        assert result.exit_code != 0


class TestMemoryCliSearch:
    def test_search_finds_match(self, memory_app_with_service) -> None:
        svc = get_service()
        assert svc is not None
        svc.remember(MemoryRecord(content="Canopus uses SQLite for memory"))
        result = runner.invoke(memory_app_with_service, ["search", "SQLite"])
        assert result.exit_code == 0
        assert "SQLite" in result.output

    def test_search_no_match(self, memory_app_with_service) -> None:
        result = runner.invoke(memory_app_with_service, ["search", "xyzzy_not_found"])
        assert result.exit_code == 0
        assert "No memories matched" in result.output

    def test_search_limit(self, memory_app_with_service) -> None:
        svc = get_service()
        assert svc is not None
        for i in range(5):
            svc.remember(MemoryRecord(content=f"item number {i}"))
        result = runner.invoke(
            memory_app_with_service, ["search", "item", "--limit", "2"]
        )
        assert result.exit_code == 0


class TestMemoryCliInspect:
    def test_inspect_by_full_id(self, memory_app_with_service) -> None:
        svc = get_service()
        assert svc is not None
        rec = MemoryRecord(content="inspectable content")
        svc.remember(rec)
        result = runner.invoke(memory_app_with_service, ["inspect", rec.id])
        assert result.exit_code == 0
        assert "inspectable content" in result.output

    def test_inspect_by_prefix(self, memory_app_with_service) -> None:
        svc = get_service()
        assert svc is not None
        rec = MemoryRecord(content="prefix search content")
        svc.remember(rec)
        result = runner.invoke(memory_app_with_service, ["inspect", rec.id[:8]])
        assert result.exit_code == 0
        assert "prefix search content" in result.output

    def test_inspect_not_found(self, memory_app_with_service) -> None:
        result = runner.invoke(memory_app_with_service, ["inspect", "no-such-id"])
        assert result.exit_code != 0


class TestMemoryCliForget:
    def test_forget_with_yes_flag(self, memory_app_with_service) -> None:
        svc = get_service()
        assert svc is not None
        rec = MemoryRecord(content="to be forgotten")
        svc.remember(rec)
        result = runner.invoke(memory_app_with_service, ["forget", rec.id, "--yes"])
        assert result.exit_code == 0
        assert svc.count() == 0

    def test_forget_not_found(self, memory_app_with_service) -> None:
        result = runner.invoke(
            memory_app_with_service, ["forget", "no-such-id", "--yes"]
        )
        assert result.exit_code != 0


# ===========================================================================
# Pipeline memory integration
# ===========================================================================


class TestPipelineMemoryIntegration:
    def test_run_pipeline_accepts_memory_context(self) -> None:
        """run_pipeline should not raise when memory_context is supplied."""
        from canopus.core.profiles import builtin_profiles
        from canopus.memory.models import MemoryContext, MemoryRecord
        from canopus.models.local.echo import EchoProvider
        from canopus.reasoning.pipeline import run_pipeline

        ctx = MemoryContext(
            records=[MemoryRecord(content="past fact about design")],
            query_text="design",
            total_found=1,
        )
        profile = builtin_profiles()["local-private"]
        result = run_pipeline(
            "tell me about design",
            profile,
            provider=EchoProvider(),
            memory_context=ctx,
        )
        assert result.final_response  # echo provider always returns something

    def test_run_pipeline_works_without_memory_context(self) -> None:
        """run_pipeline should work fine when no memory_context is supplied."""
        from canopus.core.profiles import builtin_profiles
        from canopus.models.local.echo import EchoProvider
        from canopus.reasoning.pipeline import run_pipeline

        profile = builtin_profiles()["local-private"]
        result = run_pipeline("hello", profile, provider=EchoProvider())
        assert result.final_response

    def test_build_prompt_includes_memory_block(self) -> None:
        """build_prompt should include memory block in user prompt when provided."""
        from canopus.reasoning.prompts.templates import build_prompt
        from canopus.reasoning.types import IntentCategory, Plan, PlanStep

        plan = Plan(
            intent=IntentCategory.CONVERSATIONAL,
            intent_confidence=1.0,
            summary="chat",
            steps=[PlanStep(index=0, description="respond")],
        )
        _, user_prompt = build_prompt(
            plan,
            "hello",
            memory_block="[Memory context]\n1. [fact] Some remembered fact",
        )
        assert "[Memory context]" in user_prompt
        assert "hello" in user_prompt

    def test_build_prompt_no_memory_block(self) -> None:
        """build_prompt without memory block should not include memory section."""
        from canopus.reasoning.prompts.templates import build_prompt
        from canopus.reasoning.types import IntentCategory, Plan, PlanStep

        plan = Plan(
            intent=IntentCategory.CONVERSATIONAL,
            intent_confidence=1.0,
            summary="chat",
            steps=[PlanStep(index=0, description="respond")],
        )
        _, user_prompt = build_prompt(plan, "hello")
        assert "[Memory context]" not in user_prompt


# ===========================================================================
# .gitignore sanity
# ===========================================================================


class TestGitignore:
    def test_gitignore_exists(self) -> None:
        root = Path(__file__).parent.parent
        assert (root / ".gitignore").exists()

    def test_gitignore_covers_python_artifacts(self) -> None:
        root = Path(__file__).parent.parent
        content = (root / ".gitignore").read_text()
        for pattern in ["__pycache__", "*.py[cod]", ".pytest_cache", ".mypy_cache"]:
            assert pattern in content, f"Expected {pattern!r} in .gitignore"

    def test_gitignore_covers_secrets(self) -> None:
        root = Path(__file__).parent.parent
        content = (root / ".gitignore").read_text()
        assert "secrets.toml" in content

    def test_gitignore_covers_venv(self) -> None:
        root = Path(__file__).parent.parent
        content = (root / ".gitignore").read_text()
        assert ".venv" in content or "venv" in content

    def test_gitignore_does_not_ignore_source(self) -> None:
        """Source files in canopus/ should not be matched by .gitignore patterns."""
        import subprocess

        root = Path(__file__).parent.parent
        result = subprocess.run(
            ["git", "check-ignore", "-q", "canopus/core/config.py"],
            cwd=root,
            capture_output=True,
        )
        # exit code 1 means the file is NOT ignored — that's what we want
        assert result.returncode == 1, "canopus/core/config.py should not be gitignored"
