"""Import workspace-bound v0.1.6 conversation databases into one instance store."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from cirno_core.session.session_identity import webui_chat_id, webui_session_key
from cirno_core.session.sqlite_store import SqliteSessionStore
from cirno_server.maintenance.migrations.plan import MigrationPlan, copy_path

STORE = re.compile(r"^(?:instance|[0-9a-f]{32})$")
TABLES = {"sessions": "key", "messages": "session_key", "checkpoints": "session_key",
          "pending_inputs": "session_key", "history_heads": "session_key", "history_turns": "session_key",
          "history_entries": "session_key", "inbox_receipts": "session_key", "runtime_archives": "session_key"}


def stores_at(root: Path) -> list[Path]:
    if not root.exists():
        return []
    stores = []
    for path in root.iterdir():
        if STORE.fullmatch(path.name) and path.is_dir():
            if path.is_symlink():
                raise ValueError(f"Conversation store must not be a symbolic link: {path}")
            stores.append(path)
    return sorted(stores)


def source_tables(db: sqlite3.Connection) -> set[str]:
    return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def fingerprint(db: sqlite3.Connection, key: str, tables: set[str]) -> str:
    digest = hashlib.sha256()
    for table, owner in TABLES.items():
        if table not in tables:
            continue
        for row in db.execute(f'SELECT * FROM "{table}" WHERE "{owner}"=? ORDER BY rowid', (key,)):
            for value in row:
                digest.update(str(value).encode())
                digest.update(b"\0")
    return digest.hexdigest()


def remap_metadata(value, key_map):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            is_session = key in {"session_key", "sessionKey"} or key.endswith("_session_key") or key.endswith("SessionKey")
            result[key] = key_map.get(item, item) if isinstance(item, str) and is_session else remap_metadata(item, key_map)
        if value.get("channel") == "websocket":
            for field in ("chat_id", "chatId"):
                if isinstance(value.get(field), str):
                    previous = webui_session_key(value[field])
                    result[field] = webui_chat_id(key_map.get(previous, previous))
        return result
    if isinstance(value, list):
        return [remap_metadata(item, key_map) for item in value]
    return value


def _ordered_stores(stores: list[Path], workspace: Path) -> list[Path]:
    def priority(path):
        marker = path / ".workspace"
        root = Path(marker.read_text().strip()).expanduser().resolve() if marker.is_file() else None
        owner = root / ".cirno/workspace-id" if root else None
        active = owner is not None and owner.is_file() and owner.read_text().strip() == path.name
        return (path.name != "instance", root != workspace, not active, path.name)
    return sorted(stores, key=priority)


def _copy_session(src, dst, key, target, key_map, tables, source, final):
    for table, owner in TABLES.items():
        if table not in tables:
            continue
        columns = [row[1] for row in src.execute(f'PRAGMA table_info("{table}")')]
        for raw in src.execute(f'SELECT * FROM "{table}" WHERE "{owner}"=? ORDER BY rowid', (key,)):
            row = dict(zip(columns, raw, strict=True))
            row[owner] = target
            if table == "sessions":
                metadata = remap_metadata(json.loads(row["metadata"]), key_map)
                if key != target:
                    metadata["migration_origin"] = {"session_key": key, "store": source.name}
                    metadata.pop("session_handle", None)
                    title = row["title"] or "Conversation"
                    row["title"] = metadata["title"] = f"{title} (imported from {source.name[:8]})"
                row["metadata"] = json.dumps(metadata, ensure_ascii=False)
            elif table in {"checkpoints", "pending_inputs"}:
                row["record"] = json.dumps(remap_metadata(json.loads(row["record"]), key_map), ensure_ascii=False)
            elif table == "runtime_archives":
                original = (source / row["path"]).resolve()
                if original.is_relative_to(source):
                    original = final / "imported" / source.name / original.relative_to(source)
                row["path"] = os.path.relpath(original, final)
            placeholders = ",".join("?" for _ in columns)
            dst.execute(f'INSERT INTO "{table}" ({",".join(columns)}) VALUES ({placeholders})', list(row.values()))


def stage_sessions(stores: list[Path], instance: Path, workspace: Path, plan: MigrationPlan) -> dict:
    if not stores:
        return {"stores": 0, "conversations": 0, "renamed": []}
    staged = plan.root / "staged" / "sessions"
    staged.mkdir(parents=True)
    SqliteSessionStore(staged).initialize()
    final = instance / "state" / "sessions" / "instance"
    known, occupied, renamed, bindings = {}, set(), [], {}
    for source in _ordered_stores(stores, workspace):
        database = source / "sessions.sqlite3"
        if not database.exists():
            if source != final:
                plan.retire(source)
            continue
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as src:
            if src.execute("PRAGMA user_version").fetchone()[0] != 3:
                raise ValueError(f"Unsupported conversation schema in {database}")
            tables = source_tables(src)
            mapping, imports = {}, []
            for (key,) in src.execute("SELECT key FROM sessions ORDER BY key"):
                signature = (key, fingerprint(src, key, tables))
                if signature in known:
                    mapping[key] = known[signature]
                    continue
                target = key if key not in occupied else webui_session_key("migrated-" + uuid5(NAMESPACE_URL, str(source) + "\n" + key).hex)
                if target != key:
                    renamed.append({"source": str(source), "key": key, "target": target})
                mapping[key], known[signature] = target, target
                occupied.add(target)
                imports.append(key)
            with closing(sqlite3.connect(staged / "sessions.sqlite3")) as dst:
                with dst:
                    for key in imports:
                        _copy_session(src, dst, key, mapping[key], mapping, tables, source, final)
        marker = source / ".workspace"
        if marker.is_file():
            bindings.setdefault(str(Path(marker.read_text().strip()).expanduser().resolve()), mapping)
        for artifact in source.iterdir():
            if artifact.name not in {"sessions.sqlite3", "sessions.sqlite3-wal", "sessions.sqlite3-shm", ".workspace"}:
                copy_path(artifact, staged / "imported" / source.name / artifact.name)
        if source != final:
            plan.retire(source)
    with closing(sqlite3.connect(staged / "sessions.sqlite3")) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Migrated conversation database failed integrity validation")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("Migrated conversation references are invalid")
    plan.install(staged, final)
    selector = final.parent / ".instance-store"
    if selector.exists():
        plan.retire(selector)
    return {"stores": len(stores), "conversations": len(occupied), "renamed": renamed, "bindings": bindings}
