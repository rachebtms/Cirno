"""Router identity migration changes ownership references, not archived payloads."""

import hashlib
import json
import sqlite3
from contextlib import closing

import pytest
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_server.maintenance.migrations.cirno_identity import migrate_cirno_identity


@pytest.mark.parametrize("field", ["content", "arguments", "result", "text", "body", "quote", "evidence", "provider_state"])
def test_nested_payload_fields_are_not_rewritten(tmp_path, field):
    path = tmp_path / "state/sessions.sqlite3"
    path.parent.mkdir()
    literal = {"key": "websocket:global", "is_global": True, "websocket:cirno": {"session_key": "websocket:global"}}
    record = {"source_session_key": "websocket:global", field: literal}
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE messages(session_key TEXT, record TEXT)")
        db.execute("INSERT INTO messages VALUES (?,?)", ("websocket:global", json.dumps(record)))
    assert migrate_cirno_identity(tmp_path)
    with closing(sqlite3.connect(path)) as db:
        owner, raw = db.execute("SELECT session_key,record FROM messages").fetchone()
    assert owner == ROUTER_SESSION_KEY
    assert json.loads(raw) == {"source_session_key": ROUTER_SESSION_KEY, field: literal}


@pytest.mark.parametrize("column", ["text", "content", "provider_state"])
def test_json_looking_literal_sql_columns_remain_byte_exact(tmp_path, column):
    (tmp_path / "state").mkdir()
    path = tmp_path / "home/memory/search.sqlite3"
    path.parent.mkdir(parents=True)
    raw = '{ "source": "websocket:global", "is_global": true }'
    with closing(sqlite3.connect(path)) as db, db:
        db.execute(f'CREATE TABLE chunks(session_key TEXT, "{column}" TEXT)')
        db.execute('INSERT INTO chunks VALUES (?,?)', ("websocket:global", raw))
    assert migrate_cirno_identity(tmp_path)
    with closing(sqlite3.connect(path)) as db:
        owner, saved = db.execute(f'SELECT session_key,"{column}" FROM chunks').fetchone()
    assert owner == ROUTER_SESSION_KEY
    assert saved == raw


def test_structured_memory_body_updates_ownership_without_changing_content(tmp_path):
    (tmp_path / "state").mkdir()
    path = tmp_path / "home/memory/catalog.sqlite3"
    path.parent.mkdir(parents=True)
    content = '{"source":"websocket:global","is_global":true}'
    record = {"session_key": "websocket:global", "content": content, "content_hash": hashlib.sha256(content.encode()).hexdigest()}
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE memories(session_key TEXT, body TEXT)")
        db.execute("INSERT INTO memories VALUES (?,?)", ("websocket:global", json.dumps(record)))
    assert migrate_cirno_identity(tmp_path)
    with closing(sqlite3.connect(path)) as db:
        owner, saved = db.execute("SELECT session_key,body FROM memories").fetchone()
    assert owner == ROUTER_SESSION_KEY
    assert json.loads(saved) == {**record, "session_key": ROUTER_SESSION_KEY}
    assert json.loads(saved)["content_hash"] == hashlib.sha256(json.loads(saved)["content"].encode()).hexdigest()


@pytest.mark.parametrize("other", [ROUTER_SESSION_KEY, "websocket:cirno"])
@pytest.mark.parametrize("other_value", [False, 1])
def test_conflicting_reference_map_keys_stop_before_live_publication(tmp_path, other, other_value):
    path = tmp_path / "state/sessions.sqlite3"
    path.parent.mkdir()
    record = {"owners": {"websocket:global": {"ready": True}, other: {"ready": other_value}}}
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE sessions(key TEXT PRIMARY KEY, metadata TEXT)")
        db.execute("INSERT INTO sessions VALUES (?,?)", ("websocket:global", json.dumps(record)))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Conflicting Router identity"):
        migrate_cirno_identity(tmp_path)
    assert path.read_bytes() == before


def test_identical_reference_map_entries_may_coalesce(tmp_path):
    path = tmp_path / "state/sessions.sqlite3"
    path.parent.mkdir()
    record = {"owners": {"websocket:global": {"ready": True}, ROUTER_SESSION_KEY: {"ready": True}}}
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE sessions(key TEXT PRIMARY KEY, metadata TEXT)")
        db.execute("INSERT INTO sessions VALUES (?,?)", ("websocket:global", json.dumps(record)))
    assert migrate_cirno_identity(tmp_path)
    with closing(sqlite3.connect(path)) as db:
        saved = json.loads(db.execute("SELECT metadata FROM sessions").fetchone()[0])
    assert saved == {"owners": {ROUTER_SESSION_KEY: {"ready": True}}}
