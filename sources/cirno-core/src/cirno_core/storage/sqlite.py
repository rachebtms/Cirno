"""Consistent on-disk SQLite copies, including committed WAL contents."""

import sqlite3
from contextlib import closing
from pathlib import Path


def snapshot_database(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
    target.chmod(source.stat().st_mode & 0o777)
