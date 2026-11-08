"""One server-owned preference document; field patches preserve other devices' edits."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from cirno_core.config.paths import get_data_dir
from cirno_core.profile.appearance import BUILTIN_THEMES, Preferences


class PreferenceConflictError(ValueError):
    pass


class PreferencesRepository:
    def __init__(self, path: Path | None = None):
        self.path = path or get_data_dir() / "preferences.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        with self._open() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS preferences (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, body TEXT NOT NULL)"
            )
            db.execute(
                "INSERT OR IGNORE INTO preferences VALUES (1,0,?)",
                (Preferences().model_dump_json(by_alias=True),),
            )
        self.path.chmod(0o600)

    @contextmanager
    def _open(self):
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _snapshot(db) -> dict:
        revision, body = db.execute("SELECT revision,body FROM preferences WHERE id=1").fetchone()
        return {
            "revision": revision,
            "values": Preferences.model_validate_json(body).model_dump(by_alias=True),
            "themes": [theme.model_dump(by_alias=True) for theme in BUILTIN_THEMES],
        }

    def read(self) -> dict:
        with self._open() as db:
            return self._snapshot(db)

    def update(self, patch: dict, expected_revision: int | None = None) -> dict:
        with self.lock, self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self._snapshot(db)
            if expected_revision is not None and expected_revision != current["revision"]:
                raise PreferenceConflictError(
                    "Preferences changed on another device. Reload before saving this theme."
                )
            values = Preferences.model_validate({**current["values"], **patch})
            builtins = {theme.id for theme in BUILTIN_THEMES}
            custom_ids = [theme.id for theme in values.custom_themes]
            if len(set(custom_ids)) != len(custom_ids) or builtins.intersection(custom_ids):
                raise ValueError("Each custom theme needs a unique name and identifier")
            if values.theme_id not in builtins.union(custom_ids):
                raise ValueError("Choose an existing theme")
            db.execute(
                "UPDATE preferences SET revision=revision+1,body=? WHERE id=1",
                (values.model_dump_json(by_alias=True),),
            )
            return self._snapshot(db)
