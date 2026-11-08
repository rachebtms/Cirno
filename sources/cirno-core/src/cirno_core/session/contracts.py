"""Serialized conversation metadata and administrative catalog contracts."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, TypeAlias, TypedDict, TypeVar

_Result = TypeVar("_Result")
CanonicalMessage: TypeAlias = tuple[int, dict[str, Any]]
MessageProjection: TypeAlias = Callable[[dict[str, Any], str | None, Iterable[CanonicalMessage]], _Result]


class SessionPayload(TypedDict):
    key: str
    created_at: str | None
    updated_at: str | None
    metadata: dict[str, Any]
    messages: list[dict[str, Any]]


class SessionMetadataPayload(TypedDict):
    key: str
    created_at: str | None
    updated_at: str | None
    metadata: dict[str, Any]


class SessionInfo(TypedDict):
    key: str
    created_at: str
    updated_at: str
    title: str
    preview: str
    path: str
