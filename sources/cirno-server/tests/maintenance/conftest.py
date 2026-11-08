"""Released v0.1.6 instances built without the current storage implementation."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

DDL = (Path(__file__).parent / "fixtures" / "v016.sql").read_text()


def old_store(instance, workspace, name, *, text="Research progress", key="websocket:research", parent=None):
    folder = instance / "state" / "sessions" / name
    folder.mkdir(parents=True)
    (folder / ".workspace").write_text(str(workspace))
    marker = workspace / ".cirno" / "workspace-id"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(name)
    metadata = {"title": "Research", "model_preset": "research", "workspace_scope": {"project_path": str(workspace)}}
    if parent:
        metadata["parent_session_key"] = parent
    message = {"role": "user", "content": text, "timestamp": "2026-11-01T00:00:00"}
    fact = {"kind": "input", "content": {"text": text}, "turn_id": "turn1", "phase": None, "sequence": 1, "created_at_ms": 1000}
    record = json.dumps(fact)
    with closing(sqlite3.connect(folder / "sessions.sqlite3")) as db, db:
        db.executescript(DDL)
        db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            key, "2026-11-01T00:00:00", "2026-11-01T00:00:00", json.dumps(metadata), None, 0, 2, "generation", "Research", text[:80], None,
        ))
        db.execute("INSERT INTO messages VALUES (?,?,?)", (key, 0, json.dumps(message)))
        db.execute("INSERT INTO checkpoints VALUES (?,?)", (key, json.dumps({"session_key": key, "iteration": 7})))
        db.execute("INSERT INTO pending_inputs VALUES (?,?,?,?)", (key, "pending_user_followups", 0, json.dumps({"session_key": key, "content": "Keep going"})))
        db.execute("INSERT INTO history_heads VALUES (?,?,?,?,?)", (key, 1, 1000, text[:80], text[:80]))
        db.execute("INSERT INTO history_turns VALUES (?,?,?,?,?,?)", (key, 1, 1, len(record.encode()), 1, 1))
        db.execute("INSERT INTO history_entries VALUES (?,?,?,?,?)", (key, 1, 0, "input", record))
        db.execute("INSERT INTO inbox_receipts VALUES (?,?,?,?,?,?)", (key, "generation", "input1", "journal1", "digest", 0))
    return folder


@pytest.fixture
def released(tmp_path):
    instance = tmp_path / "instance"
    workspace = instance / "workspace"
    workspace.mkdir(parents=True)
    data = {"agents": {"defaults": {"workspace": str(workspace), "modelPreset": "research"}},
            "modelPresets": {"research": {"model": "deepseek-chat", "provider": "deepseek"}}}
    path = instance / "config.json"
    path.write_text(json.dumps(data))
    for name, value in {"home/SOUL.md": "Snow", "home/memory/MEMORY.md": "Verified result",
                        "home/skills/physics/SKILL.md": "Read physics",
                        "workspace/AGENTS.md": "Project instructions", "workspace/result.md": "Scientific result"}.items():
        item = instance / name
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_text(value)
    # The released account schema and scrypt parameters are independent of the
    # current AccountStore. A placeholder text file cannot prove login survival.
    salt = b"released-owner-salt"
    hashed = hashlib.scrypt(b"Old-owner-pass!", salt=salt, n=16384, r=8, p=1)
    (instance / "state").mkdir()
    with closing(sqlite3.connect(instance / "state/webui-auth.sqlite3")) as db, db:
        db.executescript("""
            CREATE TABLE owner (id INTEGER PRIMARY KEY CHECK (id=1), username TEXT NOT NULL,
                salt BLOB NOT NULL, password_hash BLOB NOT NULL, onboarded INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE sessions (token_hash TEXT PRIMARY KEY, expires_at REAL NOT NULL);
        """)
        db.execute("INSERT INTO owner VALUES (1, ?, ?, ?, 0)", ("old-owner", salt, hashed))
    return instance, workspace, path


@pytest.fixture
def released_store():
    return old_store
