"""Rename the preview router identity with staged, resumable instance replacements."""
from __future__ import annotations

import json
import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

from cirno_server.maintenance.migrations.plan import MigrationPlan

from cirno_core.session.keys import ROUTER_CHAT_ID, ROUTER_SESSION_KEY

OLD_KEYS = ("websocket:global", "websocket:cirno")
NEW = ROUTER_SESSION_KEY
OLD_HANDLES = tuple("handle_" + hashlib.sha256(key.encode()).hexdigest()[:32] for key in OLD_KEYS)
NEW_HANDLE = "handle_" + hashlib.sha256(NEW.encode()).hexdigest()[:32]
_REFERENCE_FIELDS = {"key", "session", "source", "target", "delegated_by", "parent", "returnKey", "activeKey"}


def remap(value, field=""):
    """Change structured references, leaving prose, evidence and tool output intact."""
    if isinstance(value, dict):
        result = {NEW if key in OLD_KEYS else key: remap(item, key) for key, item in value.items() if key != "is_global"}
        if value.get("is_global") is True:
            result["role"] = "router"
        return result
    if isinstance(value, list):
        return [remap(item, field) for item in value]
    if isinstance(value, str):
        if field in {"notifications", "_telegram_category"} and value == "cirno":
            return "router"
        reference = field in _REFERENCE_FIELDS or field.lower().endswith(("session_key", "sessionkey", "_keys", "_ids"))
        if value in OLD_HANDLES and (reference or field in {"id", "handle_id", "handleId"}):
            return NEW_HANDLE
        if reference and value in OLD_KEYS:
            return NEW
        if field in {"chat_id", "chatId"} and value in {"global", "cirno"}:
            return ROUTER_CHAT_ID
        if field.endswith(("turn_id", "turnId")):
            for old in OLD_KEYS:
                if value.startswith(old + ":"):
                    return NEW + value[len(old):]
    return value


def _rewrite_database(path: Path) -> bool:
    changed = False
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE")
        db.execute("PRAGMA defer_foreign_keys=ON")
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            columns = list(db.execute(f"PRAGMA table_info({quoted})"))
            for column in columns:
                name, kind = column[1], column[2].upper()
                if "TEXT" not in kind:
                    continue
                field = '"' + name.replace('"', '""') + '"'
                needles = (*OLD_KEYS, *OLD_HANDLES, '"cirno"', "is_global", '"global"')
                condition = " OR ".join(f"instr({field},?)>0" for _ in needles)
                rows = db.execute(f"SELECT rowid,{field} FROM {quoted} WHERE {condition}", needles).fetchall()
                for rowid, raw in rows:
                    if raw in OLD_HANDLES and (name in _REFERENCE_FIELDS or name in {"id", "handle_id", "handleId"}):
                        updated = NEW_HANDLE
                    elif raw in OLD_KEYS and (name in _REFERENCE_FIELDS or name.endswith("session_key")):
                        updated = NEW
                    else:
                        try:
                            value = json.loads(raw)
                        except json.JSONDecodeError:
                            continue  # Plain prose is deliberately preserved.
                        revised = remap(value)
                        if revised == value:
                            continue
                        updated = json.dumps(revised, ensure_ascii=False, separators=(",", ":"))
                    db.execute(f"UPDATE {quoted} SET {field}=? WHERE rowid=?", (updated, rowid))
                    changed = True
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError(f"Cirno identity migration left an invalid reference in {path.name}")
    return changed


def _migrate_cirno_identity(instance: Path) -> bool:
    state = instance / "state"
    if not state.exists():
        return False
    root = state / "migrations" / "router-identity-v020"
    if (root / "completed").exists():
        return False
    from cirno_server.maintenance.startup import require_stopped_instance
    require_stopped_instance(instance / "config.json")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    plan = MigrationPlan(root)
    # Include memory references, but never scan a workspace or old migration backups.
    databases = sorted(path for base in (state, instance / "home" / "memory") for path in base.rglob("*.sqlite3")
                       if "migrations" not in path.relative_to(base).parts)
    for index, database in enumerate(databases):
        staged = root / "staged" / f"{index}.sqlite3"
        staged.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source, closing(sqlite3.connect(staged)) as target:
            source.backup(target)
        if _rewrite_database(staged):
            plan.install(staged, database)
        else:
            staged.unlink()
    # Durable schedules also refer to their owning conversation.
    for directory in (state / "cron", state / "triggers"):
        for path in directory.rglob("*.json"):
            original = json.loads(path.read_text())
            revised = remap(original)
            if revised != original:
                staged = root / "staged" / path.relative_to(state)
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_text(json.dumps(revised, ensure_ascii=False, indent=2) + "\n")
                plan.install(staged, path)
    # This structural rename has no user notification separate from the version import.
    (root / "notified").touch(mode=0o600)
    plan.save()
    plan.apply()
    return bool(plan.installs)


def migrate_cirno_identity(instance: Path) -> bool:
    state = instance / "state"
    if not state.exists():
        return False
    from filelock import FileLock
    directory = state / "migrations"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with FileLock(str(directory / ".lock"), timeout=30):
        root = directory / "router-identity-v020"
        if (root / "plan.json").exists() and not (root / "completed").exists():
            from cirno_server.maintenance.startup import require_stopped_instance
            require_stopped_instance(instance / "config.json")
            MigrationPlan.load(root).apply()
            return True
        return _migrate_cirno_identity(instance)
