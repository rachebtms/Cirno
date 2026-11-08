"""Identities for durable conversation presentation."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from cirno_core.session.display_history import (
    HistoryReader,
)

from .contracts import WEBUI_REPLAY_IDENTITY_KEY


def webui_transcript_revision(
    session_key: str,
    *,
    history: HistoryReader,
    variant: Mapping[str, Any] | None = None,
) -> str | None:
    revision = history.revision
    if revision is None:
        return None
    encoded = json.dumps(
        (revision, variant), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]


def _records_with_replay_identity(
    records: list[dict[str, Any]],
    *,
    turn_ordinal: int,
) -> list[dict[str, Any]]:
    return [
        {
            **record,
            WEBUI_REPLAY_IDENTITY_KEY: record.get(
                WEBUI_REPLAY_IDENTITY_KEY, f"turn:{turn_ordinal}:record:{record_index}"
            ),
        }
        for record_index, record in enumerate(records)
    ]


def _split_transcript_turns(lines: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    turns: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for rec in lines:
        current.append(rec)
        if rec.get("event") == "turn_end":
            turns.append(current)
            current = []
    if current:
        turns.append(current)
    return turns


def _stable_record_digest(record: dict[str, Any]) -> str:
    persisted = {key: value for key, value in record.items() if key != WEBUI_REPLAY_IDENTITY_KEY}
    raw = json.dumps(
        persisted,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _ensure_replay_identities(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Give backfilled/recovered rows a stable identity beside persisted rows."""
    annotated: list[dict[str, Any]] = []
    for fallback_turn_index, turn in enumerate(_split_transcript_turns(lines)):
        anchor = next(
            (
                value
                for record in turn
                if isinstance(
                    value := record.get(WEBUI_REPLAY_IDENTITY_KEY),
                    str,
                )
                and value
            ),
            None,
        )
        if anchor and ":record:" in anchor:
            turn_identity = anchor.rsplit(":record:", 1)[0]
        else:
            turn_digest = hashlib.sha256(
                "\n".join(_stable_record_digest(record) for record in turn).encode("ascii")
            ).hexdigest()[:16]
            turn_identity = f"legacy:{fallback_turn_index}:{turn_digest}"
        synthetic_occurrences: dict[str, int] = {}
        for record in turn:
            identity = record.get(WEBUI_REPLAY_IDENTITY_KEY)
            if isinstance(identity, str) and identity:
                annotated.append(record)
                continue
            digest = _stable_record_digest(record)
            occurrence = synthetic_occurrences.get(digest, 0)
            synthetic_occurrences[digest] = occurrence + 1
            annotated.append(
                {
                    **record,
                    WEBUI_REPLAY_IDENTITY_KEY: (
                        f"{turn_identity}:synthetic:{digest}:{occurrence}"
                    ),
                }
            )
    return annotated


def _record_position(record: Mapping[str, Any]) -> tuple[int, int] | None:
    identity = record.get(WEBUI_REPLAY_IDENTITY_KEY)
    match = (
        re.fullmatch(r"turn:(\d+):record:(\d+)", identity) if isinstance(identity, str) else None
    )
    return (int(match[1]), int(match[2])) if match else None


def _history_generation(history: HistoryReader) -> str:
    revision = history.revision
    return hashlib.sha256(str(revision[0] if revision else "").encode()).hexdigest()[:20]


def client_projection_event_id(record: Mapping[str, Any]) -> str:
    identity = record.get(WEBUI_REPLAY_IDENTITY_KEY)
    if not isinstance(identity, str) or not identity:
        identity = _stable_record_digest(dict(record))
    digest = hashlib.sha256(f"event\0{identity}".encode("utf-8")).hexdigest()[:20]
    return f"history-{digest}"
