import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from cirno_server.maintenance.migrations.cirno_identity import migrate_cirno_identity


def test_identity_migration_preserves_history_references_and_originals(tmp_path):
    path = tmp_path / "state/sessions/instance/sessions.sqlite3"
    path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE sessions(key TEXT PRIMARY KEY, metadata TEXT)")
        db.execute("CREATE TABLE messages(session_key TEXT REFERENCES sessions(key), record TEXT)")
        db.execute("INSERT INTO sessions VALUES (?,?)", ("websocket:global", json.dumps({"is_global": True, "session_handle": "cirno"})))
        db.execute("INSERT INTO sessions VALUES (?,?)", ("websocket:worker", json.dumps({"delegated_by": "websocket:global"})))
        db.execute("INSERT INTO messages VALUES (?,?)", ("websocket:global", json.dumps({"content": "literal websocket:global", "source_session_key": "websocket:global"})))
    assert migrate_cirno_identity(tmp_path)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT key FROM sessions ORDER BY key").fetchall() == [("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb",), ("websocket:worker",)]
        metadata = json.loads(db.execute("SELECT metadata FROM sessions WHERE key='websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb'").fetchone()[0])
        assert metadata == {"role": "router", "session_handle": "cirno"}
        owner, raw = db.execute("SELECT session_key,record FROM messages").fetchone()
        assert owner == "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"
        assert json.loads(raw) == {"content": "literal websocket:global", "source_session_key": "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"}
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert list((tmp_path / "state/migrations/router-identity-v020/originals").iterdir())
    assert not migrate_cirno_identity(tmp_path)


def test_identity_collision_does_not_replace_live_database(tmp_path):
    path = tmp_path / "state/sessions/instance/sessions.sqlite3"
    path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE sessions(key TEXT PRIMARY KEY, metadata TEXT)")
        db.executemany("INSERT INTO sessions VALUES (?,?)", [("websocket:global", "{}"), ("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", "{}")])
    before = path.read_bytes()
    with pytest.raises(sqlite3.IntegrityError):
        migrate_cirno_identity(tmp_path)
    assert path.read_bytes() == before


def test_uuid_migration_keeps_a_previously_chosen_display_alias(tmp_path):
    from cirno_core.session.keys import ROUTER_SESSION_KEY, ROUTER_CHAT_ID
    path = tmp_path / "state/example.sqlite3"
    path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE sessions(key TEXT PRIMARY KEY, metadata TEXT)")
        db.execute("INSERT INTO sessions VALUES (?,?)", ("websocket:cirno", json.dumps({"session_handle": "snow_9", "pending": {"chat_id": "cirno"}, "text": "literal websocket:cirno"})))
    assert migrate_cirno_identity(tmp_path)
    with closing(sqlite3.connect(path)) as db:
        key, raw = db.execute("SELECT key,metadata FROM sessions").fetchone()
        assert key == ROUTER_SESSION_KEY
        assert json.loads(raw) == {"session_handle": "snow_9", "pending": {"chat_id": ROUTER_CHAT_ID}, "text": "literal websocket:cirno"}


@pytest.mark.parametrize("interrupted", [False, True])
def test_identity_migration_retires_crashed_wal_with_the_original_database(tmp_path, monkeypatch, interrupted):
    import subprocess
    import sys
    from cirno_core.session.keys import ROUTER_SESSION_KEY
    path = tmp_path / "state/sessions.sqlite3"
    path.parent.mkdir(parents=True)
    # An abnormal shutdown leaves committed frames outside the main database file.
    subprocess.run([sys.executable, "-c", """
import os, sqlite3, sys
c=sqlite3.connect(sys.argv[1]); c.execute('PRAGMA journal_mode=WAL')
c.execute('CREATE TABLE sessions(key TEXT PRIMARY KEY, metadata TEXT)');c.commit()
c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
c.execute('INSERT INTO sessions VALUES (?,?)',('websocket:global','{}'));c.commit()
os._exit(0)
""", str(path)], check=True)
    assert Path(str(path) + "-wal").stat().st_size > 0
    if interrupted:
        rename = Path.rename
        def fail_install(source, target):
            if source.parent.name == "staged" and target == path:
                raise OSError("Interrupted after retiring old WAL")
            return rename(source, target)
        with monkeypatch.context() as patch:
            patch.setattr(Path, "rename", fail_install)
            with pytest.raises(OSError, match="Interrupted after"):
                migrate_cirno_identity(tmp_path)
        assert not path.exists()
    assert migrate_cirno_identity(tmp_path)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT key FROM sessions").fetchall() == [(ROUTER_SESSION_KEY,)]
    original = tmp_path / "state/migrations/router-identity-v020/originals/target-0"
    with closing(sqlite3.connect(original)) as db:
        assert db.execute("SELECT key FROM sessions").fetchall() == [("websocket:global",)]
