"""Current session schema initialization and unsupported-schema rejection."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

import cirno.session.sqlite_store as sqlite_store
from cirno.providers.base import ProviderConversationState
from cirno.session.manager import Session
from cirno.session.sqlite_store import SqliteSessionStore


def _session() -> Session:
    return Session(
        key="chat:extensions",
        messages=[{"role": "user", "content": "hello", "extension": {"source": "import"}}],
        metadata={
            "title": "Extended session",
            "extension": {"enabled": True},
            "runtime_checkpoint": {
                "phase": "final_response", "iteration": 1, "model": "gpt-test",
                "assistant_message": {"role": "assistant", "content": "checkpoint answer"},
                "completed_tool_results": [], "pending_tool_calls": [], "extension": {"step": 2},
            },
            "pending_user_followups": [{
                "id": "followup", "sender_id": "user", "chat_id": "extensions", "content": "next",
                "media": [], "metadata": {}, "extension": True,
            }],
        },
        provider_state=ProviderConversationState(
            kind="openai_responses", provider="openai", model="gpt-test", version=1,
            payload={"items": [], "extension": {"cursor": "opaque"}},
            pending_messages=[{"role": "assistant", "content": "pending", "extension": True}],
        ),
    )


def _database_snapshot(path: Path) -> tuple[int, str, str]:
    with closing(sqlite3.connect(path)) as db:
        return (
            db.execute("PRAGMA user_version").fetchone()[0],
            db.execute("PRAGMA journal_mode").fetchone()[0],
            "\n".join(db.iterdump()),
        )


def test_future_schema_is_rejected_without_modifying_database(tmp_path):
    store = SqliteSessionStore(tmp_path)
    store.initialize()
    store.save(_session())
    future_version = sqlite_store._SCHEMA_VERSION + 1
    with closing(sqlite3.connect(store.path)) as db:
        db.execute("PRAGMA journal_mode = DELETE")
        db.execute(f"PRAGMA user_version = {future_version}")
    before = _database_snapshot(store.path)
    before_bytes = store.path.read_bytes()
    before_files = {path.name for path in tmp_path.iterdir()}

    with pytest.raises(RuntimeError, match=f"unsupported session database schema: {future_version}"):
        store.initialize()
    assert _database_snapshot(store.path) == before
    assert store.path.read_bytes() == before_bytes
    assert {path.name for path in tmp_path.iterdir()} == before_files


def test_missing_sqlite_json_support_is_rejected_before_database_changes(tmp_path, monkeypatch):
    store = SqliteSessionStore(tmp_path)
    store.initialize()
    store.save(_session())
    with closing(sqlite3.connect(store.path)) as db:
        db.execute("PRAGMA journal_mode = DELETE")
    before = _database_snapshot(store.path)
    before_bytes = store.path.read_bytes()
    native_connect = sqlite3.connect

    class WithoutJson(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if "json_extract(" in sql:
                raise sqlite3.OperationalError("no such function: json_extract")
            return super().execute(sql, parameters)

    def connect(*args, **kwargs):
        return native_connect(*args, factory=WithoutJson, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", connect)
        with pytest.raises(RuntimeError, match="requires SQLite JSON support"):
            store.initialize()
    assert _database_snapshot(store.path) == before
    assert store.path.read_bytes() == before_bytes


def test_current_schema_initializes_and_reopens_without_changing_records(tmp_path):
    store = SqliteSessionStore(tmp_path)
    store.initialize()
    original = _session()
    store.save(original)
    reopened = SqliteSessionStore(tmp_path)
    reopened.initialize()
    loaded = reopened.load(original.key)
    assert loaded is not None
    assert loaded.messages == original.messages
    assert loaded.metadata == original.metadata
    assert loaded.last_archived == original.last_archived
    assert loaded.provider_state == original.provider_state
    assert _database_snapshot(store.path)[0] == sqlite_store._SCHEMA_VERSION
