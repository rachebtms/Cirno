"""Contracts for durable conversation presentation."""

from __future__ import annotations

import re
from typing import Any, NamedTuple, TypedDict

WEBUI_TRANSCRIPT_SCHEMA_VERSION = 3


WEBUI_FORK_MARKER_EVENT = "fork_marker"


WEBUI_TRANSCRIPT_INCOMPLETE_KEY = "transcript_incomplete"


_DEFAULT_TRANSCRIPT_PAGE_LIMIT = 160


_MAX_TRANSCRIPT_PAGE_LIMIT = 1000


_MAX_TRANSCRIPT_PAGE_RECORDS = 4_000


_MAX_TRANSCRIPT_PAGE_BYTES = 20 * 1024 * 1024


_MAX_INLINE_TRACE_DETAIL_BYTES = 32 * 1024


_WEBUI_TURN_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


WEBUI_REPLAY_IDENTITY_KEY = "_webui_replay_identity"


_WEBUI_PROJECTION_RECEIPTS_KEY = "_webui_projection_receipts"


_WEBUI_TRACE_DETAIL_REF_RE = re.compile(
    r"^(?P<turn>\d{1,12})\.(?P<start>\d{1,12})\.(?P<stop>\d{1,12})\.(?P<generation>[0-9a-f]{20})\.(?P<message>history-[0-9a-f]{20})$"
)


_MARKDOWN_LOCAL_IMAGE_RE = re.compile(
    r"!\[([^\]]*)\]\((<[^>]+>|[^)\s]+)(\s+(?:\"[^\"]*\"|'[^']*'))?\)"
)


_INLINE_MARKDOWN_IMAGE_EXTS: frozenset[str] = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".svg",
    }
)


_INLINE_MARKDOWN_VIDEO_EXTS: frozenset[str] = frozenset(
    {
        ".mp4",
        ".mov",
        ".webm",
    }
)


_INLINE_MARKDOWN_MEDIA_EXTS = _INLINE_MARKDOWN_IMAGE_EXTS | _INLINE_MARKDOWN_VIDEO_EXTS


_TURN_DISPLAY_EVENTS: frozenset[str] = frozenset(
    {
        "reasoning_delta",
        "reasoning_end",
        "delta",
        "stream_end",
        "message",
        "file_edit",
        "turn_end",
    }
)


MAX_SESSION_MENTIONS = 8


_SESSION_MENTION_NAME_RE = re.compile(r"^[\w-]+$")


_SESSION_HANDLE_ID_RE = re.compile(r"^handle_[0-9a-f]{32}$")


class _TranscriptTurnRef(NamedTuple):
    ordinal: int
    records: list[dict[str, Any]]
    start: int = 0
    stop: int = 0
    total: int = 0


class SessionBackfillTurn(NamedTuple):
    user_event: dict[str, Any]
    assistant_signature: tuple[str, ...]
    assistant_records: tuple[dict[str, Any], ...]


class _ProjectionReceipt(TypedDict):
    turn_id: str
    ranges: list[list[int]]


class _DeferredTraceGroup(NamedTuple):
    start: int
    stop: int
    detail_bytes: int
    trace_count: int


class TranscriptReplayStats:
    """Bounded, non-sensitive diagnostics for one history replay."""

    effective_limit: int = 0
    source_bytes: int = 0
    parsed_records: int = 0
    selected_bytes: int = 0
    selected_records: int = 0
    compacted_delta_records: int = 0
    replay_ms: int = 0
    capped_by_bytes: bool = False
    capped_by_records: bool = False
    truncated_oversized_turn: bool = False
