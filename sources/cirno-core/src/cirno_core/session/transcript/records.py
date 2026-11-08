"""Records for durable conversation presentation."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Mapping, Sequence, cast

from cirno_core.bus.events import INBOUND_META_LOCAL_MEDIA
from cirno_core.session.automation_turns import is_automation_kind
from cirno_core.session.session_identity import webui_chat_id
from cirno_core.session.transport_metadata import (
    WEBUI_MESSAGE_SOURCE_METADATA_KEY,
)

from .contracts import (
    _SESSION_HANDLE_ID_RE,
    _SESSION_MENTION_NAME_RE,
    _WEBUI_TURN_ID_RE,
    MAX_SESSION_MENTIONS,
)


def _response_sources(value: object) -> list[dict[str, str | bool]]:
    """Allow only recorded display identity, never settings or credential blobs."""
    if not isinstance(value, list):
        return []
    result: list[dict[str, str | bool]] = []
    keys = ("provider", "model", "preset")
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            return []
        fields = cast(dict[str, object], item)
        if any(not isinstance(fields.get(key), str) or not fields[key] for key in keys):
            return []
        source: dict[str, str | bool] = {key: cast(str, fields[key]) for key in keys}
        # Old records without an explicit fallback flag must not guess from model names.
        source["fallback"] = fields.get("fallback") is True
        if source not in result:
            result.append(source)
    return result


def _sanitize_turn_usage(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    data = cast(dict[object, object], value)
    return {
        key: item
        for key, item in data.items()
        if isinstance(key, str)
        and isinstance(item, int)
        and not isinstance(item, bool)
        and item >= 0
    }


def _record_json_line(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def _records_bytes(records: list[dict[str, Any]]) -> int:
    total = 0
    for record in records:
        total += len(_record_json_line(record).encode("utf-8")) + 1
    return total


def _now_ms() -> int:
    return int(time.time() * 1000)


def valid_created_at_ms(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0 and value < 10_000_000_000_000_000:
        return int(value)
    return None


def _record_for_append(obj: dict[str, Any]) -> dict[str, Any]:
    if valid_created_at_ms(obj.get("created_at_ms")) is not None:
        return obj
    record = dict(obj)
    record["created_at_ms"] = _now_ms()
    return record


def normalize_webui_turn_id(value: Any) -> str:
    if isinstance(value, str):
        candidate = value.strip()
        if _WEBUI_TURN_ID_RE.fullmatch(candidate):
            return candidate
    return str(uuid.uuid4())


def webui_message_source(metadata: dict[str, Any] | None) -> dict[str, str] | None:
    raw = (metadata or {}).get(WEBUI_MESSAGE_SOURCE_METADATA_KEY)
    if not isinstance(raw, dict):
        return None
    source_metadata = cast(dict[str, Any], raw)
    kind = source_metadata.get("kind")
    if not isinstance(kind, str) or not is_automation_kind(kind):
        return None
    source: dict[str, str] = {"kind": kind}
    label = source_metadata.get("label")
    if isinstance(label, str) and label.strip():
        source["label"] = label.strip()
    return source


def _chat_id_from_session_key(session_key: str) -> str | None:
    chat_id = webui_chat_id(session_key)
    if chat_id is None:
        return None
    return chat_id.strip() or None


def normalize_session_mentions_metadata(raw: object) -> list[dict[str, str]]:
    """Validate session-reference metadata crossing a persistence seam."""
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        return []
    normalized: list[dict[str, str]] = []
    for raw_item in cast(Sequence[object], raw)[:MAX_SESSION_MENTIONS]:
        if not isinstance(raw_item, Mapping):
            continue
        item = cast(Mapping[str, object], raw_item)
        name = item.get("name")
        session_key = item.get("session_key")
        title = item.get("title")
        handle_id = item.get("id")
        if not isinstance(name, str) or not isinstance(session_key, str):
            continue
        name = name.strip()[:80]
        session_key = session_key.strip()[:512]
        if not name or not session_key or _SESSION_MENTION_NAME_RE.fullmatch(name) is None:
            continue
        mention = {
            "name": name,
            "session_key": session_key,
            "title": title.strip()[:160] if isinstance(title, str) else "",
        }
        if isinstance(handle_id, str) and _SESSION_HANDLE_ID_RE.fullmatch(handle_id):
            mention["id"] = handle_id
        normalized.append(mention)
    return normalized


def normalize_session_message_ui_metadata(raw: object) -> dict[str, Any] | None:
    """Validate session-message provenance at the transcript-to-WebUI boundary."""
    if not isinstance(raw, Mapping):
        return None
    raw_data = cast(Mapping[str, object], raw)
    session = raw_data.get("session")
    message_id = raw_data.get("message_id")
    if (
        not isinstance(message_id, str)
        or not message_id.strip()
        or not isinstance(session, Mapping)
    ):
        return None
    session_data = cast(Mapping[str, object], session)
    handle_id = session_data.get("id")
    name = session_data.get("name")
    if (
        not isinstance(handle_id, str)
        or _SESSION_HANDLE_ID_RE.fullmatch(handle_id) is None
        or not isinstance(name, str)
        or not name.strip()
    ):
        return None
    handle: dict[str, Any] = {
        "id": handle_id.strip()[:128],
        "name": name.strip()[:80],
    }
    return {
        "message_id": message_id.strip()[:128],
        "session": handle,
    }


def _local_media_paths(record: Mapping[str, Any]) -> list[str]:
    raw = record.get(INBOUND_META_LOCAL_MEDIA)
    return (
        [path for path in cast(list[object], raw) if isinstance(path, str)]
        if isinstance(raw, list)
        else []
    )
