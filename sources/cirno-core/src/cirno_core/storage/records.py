"""Read versioned JSON record collections without replacing unreadable originals."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar, cast

T = TypeVar("T")


class RecordStoreError(RuntimeError):
    """A persisted collection cannot be decoded; its original is unchanged."""


def decode_record(content: str | bytes) -> dict[str, Any]:
    """Decode one stored object; invalid records must reach their caller as errors."""
    value: object = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError("Stored record must be a JSON object")
    return cast(dict[str, Any], value)


def read_records(path: Path, collection: str, decode: Callable[[dict[str, Any]], T]) -> list[T]:
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    try:
        payload = decode_record(content)
        if payload.get("version") != 1:
            raise ValueError("expected a version 1 record collection")
        rows = payload.get(collection)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in cast(list[object], rows)):
            raise ValueError(f"{collection} must be a list of objects")
        return [decode(cast(dict[str, Any], row)) for row in cast(list[object], rows)]
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise RecordStoreError(f"Cannot load corrupt {collection} store at {path}: {error}. Correct or restore {path.name}; the original is unchanged.") from error
