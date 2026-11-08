"""Prompts for durable conversation presentation."""

from __future__ import annotations

import threading
from bisect import bisect_left
from collections import OrderedDict
from collections.abc import Iterator
from itertools import groupby
from pathlib import Path
from typing import Any, Callable, NamedTuple, TypedDict

from cirno_core.session.display_history import (
    HistoryReader,
)
from cirno_core.session.presentation_history import (
    record_from_fact,
)

from .answer_digest import AnswerDigest, assistant_signature_identity
from .answers import visit_transcript_answers
from .contracts import WEBUI_REPLAY_IDENTITY_KEY, SessionBackfillTurn
from .identities import client_projection_event_id, webui_transcript_revision
from .paging import decode_transcript_cursor, encode_page_cursor
from .records import normalize_session_message_ui_metadata, valid_created_at_ms


class PromptSummary(TypedDict):
    id: str
    preview: str
    answerPreview: str
    createdAt: int
    cursor: str
    turnId: str


class _BackfillCandidate(NamedTuple):
    ordinal: int
    signature: str
    answer_preview: str
    has_user: bool


class _ChunkPromptView(NamedTuple):
    prompts: tuple[PromptSummary, ...]
    candidates: tuple[_BackfillCandidate, ...]


class _PromptView(NamedTuple):
    prompts: tuple[PromptSummary, ...]
    backfilled_users: dict[int, dict[str, Any]]
    needs_canonical: bool


def prompt_index_revision(
    session_key: str, session_version: tuple[str, int] | None = None, *, history: HistoryReader
) -> str | None:
    """Validate display inputs without reading canonical history or constructing a view."""
    return webui_transcript_revision(
        session_key, history=history, variant={"session_version": session_version}
    )


def _text_preview(value: object, limit: int) -> str:
    text = str(value or "")
    start, end = 0, len(text)
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return text[start : min(end, start + limit)]


def _prompt_summary(record: dict[str, Any], ordinal: int, answer: str) -> PromptSummary:
    return {
        "id": client_projection_event_id(record),
        "preview": _text_preview(record.get("text"), 320),
        "answerPreview": answer,
        "createdAt": valid_created_at_ms(record.get("created_at_ms")) or 0,
        "cursor": encode_page_cursor(ordinal),
        "turnId": str(record.get("turn_id") or ""),
    }


def _history_prompt_summaries(history: HistoryReader) -> _ChunkPromptView:
    result: list[PromptSummary] = []
    candidates: list[_BackfillCandidate] = []
    for ordinal, entries in groupby(history.navigation(), key=lambda entry: entry[0]):
        digest = AnswerDigest()
        has_user = False
        seen_turns: set[str] = set()
        seen_messages: set[str] = set()
        pending: PromptSummary | None = None

        def records() -> Iterator[dict[str, Any]]:
            nonlocal has_user, pending
            for _, position, fact in entries:
                record = record_from_fact(fact, history.key)
                record[WEBUI_REPLAY_IDENTITY_KEY] = f"turn:{ordinal}:record:{position}"
                if record.get("event") == "user":
                    has_user = True
                    pending = None
                    turn_id = str(record.get("turn_id") or "")
                    provenance = normalize_session_message_ui_metadata(record.get("session_message"))
                    duplicate = False
                    if provenance:
                        message_id = str(provenance["message_id"])
                        duplicate = message_id in seen_messages
                        seen_messages.add(message_id)
                    elif turn_id:
                        duplicate = turn_id in seen_turns
                    if not duplicate:
                        if turn_id:
                            seen_turns.add(turn_id)
                        pending = _prompt_summary(record, ordinal, "")
                        result.append(pending)
                elif pending is not None and record.get("event") in {"message", "stream_end"} and not record.get("kind"):
                    preview = _text_preview(record.get("text"), 240)
                    if preview:
                        pending["answerPreview"] = preview
                        pending = None
                yield record

        visit_transcript_answers(records(), digest.append, digest.replace, digest.finish)
        candidates.append(_BackfillCandidate(ordinal, digest.identity(), digest.first_preview, has_user))
    return _ChunkPromptView(tuple(result), tuple(candidates))


def _build_prompt_view(
    *,
    history: HistoryReader,
    session_turns_loader: Callable[[], list[SessionBackfillTurn]] | None = None,
) -> _PromptView:
    chunk = _history_prompt_summaries(history)
    raw_prompts = list(chunk.prompts)
    candidates = list(chunk.candidates)
    session_turns = None
    needs_canonical = any(
        not candidate.has_user and candidate.signature for candidate in candidates
    )
    if needs_canonical and session_turns_loader is not None:
        session_turns = session_turns_loader()
    entries: list[tuple[int, PromptSummary, dict[str, Any] | None]] = [
        (decode_transcript_cursor(prompt["cursor"]) or 0, prompt, None) for prompt in raw_prompts
    ]
    session_cursor = 0
    signature_positions: dict[str, list[int]] = {}
    for position, turn in enumerate(session_turns or []):
        signature_positions.setdefault(
            assistant_signature_identity(turn.assistant_signature), []
        ).append(position)
    for candidate in candidates:
        if not session_turns:
            break
        positions = signature_positions.get(candidate.signature)
        if not candidate.signature or not positions:
            continue
        # Preserve unique-in-suffix matching without rescanning canonical history
        # for each transcript turn. Ambiguous answers still cannot backfill a user.
        offset = bisect_left(positions, session_cursor)
        if offset != len(positions) - 1:
            continue
        match = positions[offset]
        session_cursor = match + 1
        if candidate.has_user:
            continue
        user = dict(session_turns[match].user_event)
        summary = _prompt_summary(user, candidate.ordinal, candidate.answer_preview)
        entries.append((candidate.ordinal, summary, user))
    prompts: list[PromptSummary] = []
    backfilled_users: dict[int, dict[str, Any]] = {}
    for ordinal, prompt, user in sorted(entries, key=lambda entry: entry[0]):
        prompts.append(prompt)
        if user is not None:
            backfilled_users[ordinal] = user
    return _PromptView(tuple(prompts), backfilled_users, needs_canonical)


_PROMPT_SNAPSHOTS: OrderedDict[tuple[Path, str, str], _PromptView] = OrderedDict()


_PROMPT_SNAPSHOT_LOCK = threading.Lock()
_PROMPT_CACHE_MAX_PROMPTS = 25000


def prompt_view_snapshot(
    session_key: str,
    *,
    history: HistoryReader,
    session_turns_loader: Callable[[], list[SessionBackfillTurn]] | None = None,
    session_version_loader: Callable[[], tuple[str, int] | None] | None = None,
) -> tuple[_PromptView, str | None]:
    path = history.storage_path

    def read_revision() -> str | None:
        version = session_version_loader() if session_version_loader is not None else None
        return prompt_index_revision(session_key, version, history=history)

    revision = read_revision()
    cache_key = (path, session_key, revision) if revision else None
    if cache_key:
        with _PROMPT_SNAPSHOT_LOCK:
            cached = _PROMPT_SNAPSHOTS.get(cache_key)
            if cached is not None and (
                not cached.needs_canonical or session_version_loader is not None
            ):
                _PROMPT_SNAPSHOTS.move_to_end(cache_key)
                return cached, revision
    view = _build_prompt_view(history=history, session_turns_loader=session_turns_loader)
    # A caller supplying only messages cannot validate canonical changes, so a
    # recovered view needs a version loader before it can be reused.
    if (view.needs_canonical and session_version_loader is None) or revision != read_revision():
        return view, None
    if cache_key:
        with _PROMPT_SNAPSHOT_LOCK:
            _PROMPT_SNAPSHOTS[cache_key] = view
            _PROMPT_SNAPSHOTS.move_to_end(cache_key)
            while len(_PROMPT_SNAPSHOTS) > 8 or sum(len(cached.prompts) for cached in _PROMPT_SNAPSHOTS.values()) > _PROMPT_CACHE_MAX_PROMPTS:
                _PROMPT_SNAPSHOTS.popitem(last=False)
    return view, revision
