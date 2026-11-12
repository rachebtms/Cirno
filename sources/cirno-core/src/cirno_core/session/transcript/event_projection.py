"""Event projection for durable conversation presentation."""

from __future__ import annotations

from typing import Any, Callable, Mapping, cast

from cirno_core.session.automation_turns import is_automation_kind

from .activity import _normalize_tool_events
from .contracts import _WEBUI_PROJECTION_RECEIPTS_KEY
from .identities import client_projection_event_id
from .media import _media_from_signed_urls
from .records import (
    _local_media_paths,
    _response_sources,
    _sanitize_turn_usage,
    valid_created_at_ms,
    normalize_session_mentions_metadata,
    normalize_session_message_ui_metadata,
)


def _client_projection_turn_fields(record: Mapping[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    turn_id = record.get("turn_id")
    if isinstance(turn_id, str) and turn_id:
        fields["turn_id"] = turn_id
    turn_phase = record.get("turn_phase")
    if isinstance(turn_phase, str) and turn_phase in {
        "user",
        "reasoning",
        "activity",
        "answer",
        "complete",
    }:
        fields["turn_phase"] = turn_phase
    turn_seq = record.get("turn_seq")
    if isinstance(turn_seq, int | float) and not isinstance(turn_seq, bool):
        fields["turn_seq"] = int(turn_seq)
    return fields


def _client_projection_common_fields(record: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "chat_id": str(record.get("chat_id") or ""),
        "projection_id": client_projection_event_id(record),
        **_client_projection_turn_fields(record),
    }
    created_at_ms = valid_created_at_ms(record.get("created_at_ms"))
    if created_at_ms is not None:
        fields["created_at_ms"] = created_at_ms
    receipts = record.get(_WEBUI_PROJECTION_RECEIPTS_KEY)
    if receipts:
        fields["projection_receipts"] = receipts
    return fields


def _client_projection_source(record: dict[str, Any]) -> dict[str, Any] | None:
    source = record.get("source")
    if not isinstance(source, dict):
        return None
    source_data = cast(dict[str, Any], source)
    kind = source_data.get("kind")
    if not isinstance(kind, str) or not is_automation_kind(kind):
        return None
    projected: dict[str, Any] = {"kind": kind}
    label = source_data.get("label")
    if isinstance(label, str) and label.strip():
        projected["label"] = label.strip()
    return projected


def _client_projection_event(
    record: dict[str, Any],
    *,
    augment_user_media: Callable[[list[str], list[str]], list[dict[str, Any]]] | None,
    augment_assistant_media: Callable[[list[str]], list[dict[str, Any]]] | None,
    augment_assistant_text: Callable[[str], str] | None,
) -> dict[str, Any] | None:
    event = record.get("event")
    common = _client_projection_common_fields(record)
    if event in {"delta", "stream_end", "message"} and "response_sources" in record:
        common["response_sources"] = _response_sources(record["response_sources"])
    if event == "user":
        projected: dict[str, Any] = {
            "event": "user_message",
            **common,
            "text": record.get("text") if isinstance(record.get("text"), str) else "",
            "starts_turn": True,
        }
        raw_paths = record.get("media_paths")
        paths = (
            [str(path) for path in cast(list[Any], raw_paths) if path]
            if isinstance(raw_paths, list)
            else []
        )
        if paths and augment_user_media is not None:
            media = augment_user_media(paths, _local_media_paths(record))
            if media:
                projected["media_urls"] = media
        for source_key, target_key in (
            ("cli_apps", "cli_apps"),
            ("mcp_presets", "mcp_presets"),
        ):
            value = record.get(source_key)
            if isinstance(value, list):
                rows = [
                    dict(cast(dict[str, Any], row))
                    for row in cast(list[Any], value)
                    if isinstance(row, dict)
                ]
                if rows:
                    projected[target_key] = rows
        mentions = normalize_session_mentions_metadata(record.get("session_mentions"))
        if mentions:
            projected["session_mentions"] = mentions
        session_message = normalize_session_message_ui_metadata(record.get("session_message"))
        if session_message:
            projected["provenance"] = {"session_message": session_message}
        if isinstance(record.get("input_origin"), dict):
            projected.setdefault("provenance", {})["input_origin"] = record["input_origin"]
        return projected

    if event in {"delta", "stream_end", "reasoning_delta", "reasoning_end"}:
        projected = {"event": event, **common}
        stream_id = record.get("stream_id")
        if isinstance(stream_id, str) and stream_id:
            projected["stream_id"] = stream_id
        text = record.get("text")
        if isinstance(text, str):
            if event == "stream_end" and augment_assistant_text is not None:
                text = augment_assistant_text(text)
            projected["text"] = text
        if event == "stream_end":
            if record.get("resuming") is True:
                projected["resuming"] = True
            if record.get("merge_next") is True:
                projected["merge_next"] = True
            source = _client_projection_source(record)
            if source:
                projected["source"] = source
        return projected

    if event == "message":
        text = record.get("text")
        content = text if isinstance(text, str) else ""
        render_as_text = record.get("render_as") == "text"
        if not render_as_text and augment_assistant_text is not None:
            content = augment_assistant_text(content)
        projected = {"event": "message", **common, "text": content}
        if render_as_text:
            projected["render_as"] = "text"
        if isinstance(record.get("agent_ui"), dict):
            projected["agent_ui"] = dict(record["agent_ui"])
        kind = record.get("kind")
        if kind in {"tool_hint", "progress", "reasoning"}:
            projected["kind"] = kind
        tool_events = _normalize_tool_events(record.get("tool_events"))
        if tool_events:
            projected["tool_events"] = tool_events
        raw_media = record.get("media")
        media_paths = (
            [path for path in cast(list[Any], raw_media) if isinstance(path, str) and path]
            if isinstance(raw_media, list)
            else []
        )
        media = (
            augment_assistant_media(media_paths)
            if media_paths and augment_assistant_media is not None
            else []
        )
        if not media and (not media_paths or augment_assistant_media is None):
            media = _media_from_signed_urls(record.get("media_urls"))
        if media:
            projected["media_urls"] = media
        latency_ms = record.get("latency_ms")
        if isinstance(latency_ms, int | float) and latency_ms >= 0:
            projected["latency_ms"] = int(latency_ms)
        source = _client_projection_source(record)
        if source:
            projected["source"] = source
        return projected

    if event == "file_edit":
        raw_edits = record.get("edits")
        edits = (
            [
                dict(cast(dict[str, Any], edit))
                for edit in cast(list[Any], raw_edits)
                if isinstance(edit, dict)
            ]
            if isinstance(raw_edits, list)
            else []
        )
        return {"event": "file_edit", **common, "edits": edits}

    if event == "context_compaction":
        compaction_id = record.get("compaction_id")
        phase = record.get("phase")
        if (
            not isinstance(compaction_id, str)
            or not compaction_id
            or not isinstance(phase, str)
            or phase not in {"started", "succeeded", "failed", "cancelled"}
        ):
            return None
        projected = {
            "event": "context_compaction",
            **common,
            "compaction_id": compaction_id,
            "phase": phase,
        }
        reason = record.get("reason")
        if isinstance(reason, str) and reason in {
            "idle",
            "context_pressure",
            "manual",
            "provider_native",
        }:
            projected["reason"] = reason
        error = record.get("error")
        if isinstance(error, str) and error:
            projected["error"] = error
        for field in ("context_tokens", "context_window_tokens"):
            value = record.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                projected[field] = value
        if record.get("evidence_checkpoint") is True:
            projected["evidence_checkpoint"] = True
        if isinstance(record.get("learning_failure"), dict):
            projected["learning_failure"] = record["learning_failure"]
        if isinstance(record.get("learning_retry"), dict):
            projected["learning_retry"] = record["learning_retry"]
        estimated = record.get("context_estimated")
        if isinstance(estimated, bool):
            projected["context_estimated"] = estimated
        return projected

    if event == "turn_end":
        projected = {"event": "turn_end", **common}
        latency_ms = record.get("latency_ms")
        if isinstance(latency_ms, int | float) and latency_ms >= 0:
            projected["latency_ms"] = int(latency_ms)
        usage = _sanitize_turn_usage(record.get("usage"))
        if usage:
            projected["usage"] = usage
        raw_round_usages = record.get("round_usages")
        if isinstance(raw_round_usages, list):
            round_usages = [
                sanitized
                for item in cast(list[object], raw_round_usages)
                if (sanitized := _sanitize_turn_usage(item)) is not None
            ]
            if round_usages:
                projected["round_usages"] = round_usages
        context_window = record.get("context_window_tokens")
        if isinstance(context_window, int | float) and context_window >= 0:
            projected["context_window_tokens"] = int(context_window)
        for key in ("outcome", "failure_kind", "failure_error_kind", "failure_message"):
            if isinstance(value := record.get(key), str):
                projected[key] = value
        if isinstance(attempts := record.get("failure_attempts"), int) and not isinstance(
            attempts, bool
        ):
            projected["failure_attempts"] = attempts
        if isinstance(goal := record.get("goal_state"), dict):
            projected["goal_state"] = goal
        return projected
    return None
