"""Inputs for durable conversation presentation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence, cast

from cirno_core.bus.events import INBOUND_META_LOCAL_MEDIA, INBOUND_META_TURN_ID
from cirno_core.command.builtin.catalog import USER_SHELL_COMMAND
from cirno_core.runtime.context import public_history_message
from cirno_core.session.display_history import (
    HistoryFact,
)
from cirno_core.session.history_visibility import is_hidden_history_message
from cirno_core.session.model import Session
from cirno_core.session.presentation_history import (
    fact_from_record,
)

from .contracts import WEBUI_REPLAY_IDENTITY_KEY, _WEBUI_TURN_ID_RE, SessionBackfillTurn
from .records import (
    _local_media_paths,
    valid_created_at_ms,
    normalize_session_mentions_metadata,
    normalize_session_message_ui_metadata,
)


def build_user_transcript_event(
    chat_id: str,
    text: str,
    *,
    media_paths: list[Any] | None = None,
    local_media_paths: list[str] | None = None,
    cli_apps: list[Any] | None = None,
    mcp_presets: list[Any] | None = None,
    session_mentions: Sequence[Any] | None = None,
) -> dict[str, Any] | None:
    paths = [str(path) for path in (media_paths or []) if path]
    if not text and not paths:
        return None
    event: dict[str, Any] = {
        "event": "user",
        "chat_id": chat_id,
        "text": text,
    }
    if paths:
        event["media_paths"] = paths
        local = [path for path in (local_media_paths or []) if path in paths]
        if local:
            event[INBOUND_META_LOCAL_MEDIA] = local
    apps = [
        dict(cast(Mapping[str, Any], app)) for app in (cli_apps or []) if isinstance(app, Mapping)
    ]
    if apps:
        event["cli_apps"] = apps
    presets = [
        dict(cast(Mapping[str, Any], preset))
        for preset in (mcp_presets or [])
        if isinstance(preset, Mapping)
    ]
    if presets:
        event["mcp_presets"] = presets
    mentions = normalize_session_mentions_metadata(session_mentions)
    if mentions:
        event["session_mentions"] = mentions
    return event


def _is_user_shell_command(message: Mapping[str, Any]) -> bool:
    content = message.get("content")
    return (
        message.get("role") == "user"
        and message.get("_command") is True
        and isinstance(content, str)
        and (content == USER_SHELL_COMMAND or content.startswith(f"{USER_SHELL_COMMAND} "))
    )


def _session_user_event(
    session_key: str,
    message: dict[str, Any],
    *,
    canonical_position: int | None = None,
) -> dict[str, Any] | None:
    if message.get("role") != "user":
        return None
    if is_hidden_history_message(message):
        return None
    message = public_history_message(message)
    content = message.get("content")
    text = content if isinstance(content, str) else ""
    media = message.get("media")
    cli_apps = message.get("cli_apps")
    mcp_presets = message.get("mcp_presets")
    session_mentions = message.get("session_mentions")
    chat_id = session_key.split(":", 1)[1] if ":" in session_key else session_key
    event = build_user_transcript_event(
        chat_id,
        text,
        media_paths=cast(list[Any], media) if isinstance(media, list) else None,
        local_media_paths=_local_media_paths(message),
        cli_apps=cast(list[Any], cli_apps) if isinstance(cli_apps, list) else None,
        mcp_presets=cast(list[Any], mcp_presets) if isinstance(mcp_presets, list) else None,
        session_mentions=(
            cast(list[Any], session_mentions) if isinstance(session_mentions, list) else None
        ),
    )
    if event is None:
        return None
    timestamp = message.get("timestamp")
    created_at_ms = None
    if isinstance(timestamp, str):
        try:
            created_at_ms = valid_created_at_ms(
                datetime.fromisoformat(timestamp).timestamp() * 1000
            )
        except (ValueError, OverflowError, OSError):
            pass
    event["created_at_ms"] = created_at_ms if created_at_ms is not None else 0
    provenance = normalize_session_message_ui_metadata(message.get("session_message"))
    if provenance:
        event["session_message"] = provenance
    if isinstance(origin := message.get("input_origin"), dict):
        event["input_origin"] = origin
    input_id = message.get(INBOUND_META_TURN_ID)
    if isinstance(input_id, str) and _WEBUI_TURN_ID_RE.fullmatch(input_id):
        event["turn_id"] = input_id
        event["turn_phase"] = "user"
        event[WEBUI_REPLAY_IDENTITY_KEY] = f"input:{session_key}:{input_id}"
    elif canonical_position is not None:
        event[WEBUI_REPLAY_IDENTITY_KEY] = f"canonical:{session_key}:message:{canonical_position}"
    return event


def _assistant_text_signature(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _session_assistant_event(
    session_key: str,
    message: dict[str, Any],
) -> dict[str, Any] | None:
    if message.get("role") != "assistant" or is_hidden_history_message(message):
        return None
    message = public_history_message(message)
    content = message.get("content")
    text = content if isinstance(content, str) else ""
    media = message.get("media")
    media_paths = [str(path) for path in cast(list[Any], media)] if isinstance(media, list) else []
    media_paths = [path for path in media_paths if path]
    if not text.strip() and not media_paths:
        return None
    chat_id = session_key.split(":", 1)[1] if ":" in session_key else session_key
    event: dict[str, Any] = {
        "event": "message",
        "chat_id": chat_id,
        "text": text,
    }
    if media_paths:
        event["media"] = media_paths
    if isinstance(message.get("agent_ui"), dict):
        event["agent_ui"] = dict(message["agent_ui"])
    latency_ms = message.get("latency_ms")
    if isinstance(latency_ms, int | float) and latency_ms >= 0:
        event["latency_ms"] = int(latency_ms)
    return event


def session_display_facts(session: Session) -> list[HistoryFact]:
    """Basic projection for a fork whose source has model records but no display facts."""
    return [
        fact_from_record(row)
        for message in session.messages
        if (
            row := _session_user_event(session.key, message)
            or _session_assistant_event(session.key, message)
        )
        is not None
    ]


def session_backfill_turns(
    session_key: str,
    session_messages: list[dict[str, Any]],
) -> list[SessionBackfillTurn]:
    turns: list[SessionBackfillTurn] = []
    current_user: dict[str, Any] | None = None
    assistant_records: list[dict[str, Any]] = []

    def flush() -> None:
        if current_user is None or not assistant_records:
            return
        signature = tuple(
            text
            for record in assistant_records
            if (text := _assistant_text_signature(record.get("text")))
        )
        turns.append(
            SessionBackfillTurn(
                current_user,
                signature,
                tuple(dict(record) for record in assistant_records),
            )
        )

    for position, message in enumerate(session_messages):
        role = message.get("role")
        if role == "user":
            flush()
            current_user = _session_user_event(session_key, message, canonical_position=position)
            assistant_records = []
            continue
        if role == "assistant" and current_user is not None:
            record = _session_assistant_event(session_key, message)
            if record is not None:
                assistant_records.append(record)
    flush()
    return turns
