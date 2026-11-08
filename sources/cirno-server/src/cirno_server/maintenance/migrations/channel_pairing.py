"""Retire generic channel pairing; Telegram keeps its dedicated owner PIN binding."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from cirno_server.maintenance.migrations.plan import MigrationPlan, copy_path


def stage_pairing_retirement(instance: Path, plan: MigrationPlan) -> int:
    plan.retire(instance / "state" / "pairing.json")
    directory = instance / "state" / "notifications"
    database = directory / "inbox.sqlite3"
    if not database.exists():
        return 0
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
        count = source.execute("SELECT count(*) FROM notices WHERE kind='pairing'").fetchone()[0]
        if not count:
            return 0
        staged = plan.root / "staged" / "notifications"
        staged.mkdir(parents=True, mode=0o700)
        # Keep notification artifacts together. Replacing the directory also keeps
        # the old database's WAL beside its original main file in the archive.
        for item in directory.iterdir():
            if item.name not in {"inbox.sqlite3", "inbox.sqlite3-wal", "inbox.sqlite3-shm"}:
                copy_path(item, staged / item.name)
        target = staged / database.name
        target.touch(mode=0o600)
        with closing(sqlite3.connect(target)) as snapshot, snapshot:
            source.backup(snapshot)
            snapshot.execute("DELETE FROM telegram_pending WHERE notice_id IN (SELECT id FROM notices WHERE kind='pairing')")
            snapshot.execute(
                "UPDATE notices SET category='system', kind='migration', status='resolved', body=? WHERE kind='pairing'",
                ("Legacy channel pairing was retired. Bind your personal Telegram account in Settings → Telegram.",),
            )
    plan.install(staged, directory)
    return count
