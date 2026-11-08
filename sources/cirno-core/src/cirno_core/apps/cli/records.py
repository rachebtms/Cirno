"""Installed records and rebuildable registry cache files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from cirno_core.apps.cli.contracts import CliAppError
from cirno_core.utils.atomic_file import atomic_write_text
from filelock import FileLock
from loguru import logger


def _as_object_dict(value: object) -> dict[str, Any] | None:
    """Narrow a JSON-like object to the string-keyed mapping used by this module."""
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        logger.warning("Could not read CLI App catalog cache {}: {}", path, exc)
        return None
    return _as_object_dict(data)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False))


class InstalledApps:
    """Commit one app's record without overwriting concurrent changes to others."""

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CliAppError(f"Could not read installed CLI Apps at {self.path}: {exc}") from exc
        if (
            not isinstance(data, dict)
            or data.get("schema_version") != 1
            or not isinstance(data.get("apps"), dict)
        ):
            raise CliAppError(
                f"Invalid installed CLI Apps record at {self.path}: expected schema_version 1 and an apps object"
            )
        return data["apps"]

    def replace(self, apps: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.path) + ".lock", timeout=10):
            _write_json(self.path, {"schema_version": 1, "apps": apps})

    def put(self, name: str, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.path) + ".lock", timeout=10):
            apps = self.read()
            apps[name] = entry
            _write_json(self.path, {"schema_version": 1, "apps": apps})

    def remove(self, name: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.path) + ".lock", timeout=10):
            apps = self.read()
            apps.pop(name, None)
            _write_json(self.path, {"schema_version": 1, "apps": apps})
