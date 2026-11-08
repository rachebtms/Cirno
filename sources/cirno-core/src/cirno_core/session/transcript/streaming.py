"""Streaming for durable conversation presentation."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .contracts import _WEBUI_PROJECTION_RECEIPTS_KEY, _ProjectionReceipt


def _stream_key(record: dict[str, Any], stream: str) -> tuple[str, str, str]:
    raw_turn_id = record.get("turn_id")
    turn_id = raw_turn_id if isinstance(raw_turn_id, str) else ""
    raw_phase = record.get("turn_phase")
    phase = raw_phase if isinstance(raw_phase, str) and raw_phase else stream
    raw_stream_id = record.get("stream_id")
    stream_id = raw_stream_id if isinstance(raw_stream_id, str) else ""
    return turn_id, phase, stream_id


def _projection_receipts(records: Sequence[Mapping[str, Any]]) -> list[_ProjectionReceipt]:
    """Compress actual represented facts by turn, without covering missing sequences."""
    members: dict[str, set[int]] = {}
    for record in records:
        turn_id, sequence = record.get("turn_id"), record.get("turn_seq")
        if (
            isinstance(turn_id, str)
            and turn_id
            and isinstance(sequence, int)
            and not isinstance(sequence, bool)
            and sequence >= 0
        ):
            members.setdefault(turn_id, set()).add(sequence)
    receipts: list[_ProjectionReceipt] = []
    for turn_id, sequences in members.items():
        ranges: list[list[int]] = []
        for sequence in sorted(sequences):
            if ranges and ranges[-1][1] + 1 == sequence:
                ranges[-1][1] = sequence
            else:
                ranges.append([sequence, sequence])
        receipts.append({"turn_id": turn_id, "ranges": ranges})
    return receipts


def _compact_completed_stream_deltas(
    turn: list[dict[str, Any]],
    *,
    include_projection_receipts: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """Fold transport deltas into canonical end records for a completed turn."""
    if not turn or turn[-1].get("event") != "turn_end":
        return turn, 0

    pending: dict[tuple[str, str, str], list[tuple[int, dict[str, Any]]]] = {}
    dropped_indexes: set[int] = set()
    replacements: dict[int, dict[str, Any]] = {}
    for index, record in enumerate(turn):
        event = record.get("event")
        if event in {"delta", "reasoning_delta"}:
            stream = "answer" if event == "delta" else "reasoning"
            pending.setdefault(_stream_key(record, stream), []).append((index, record))
            continue
        if event not in {"stream_end", "reasoning_end"}:
            continue
        stream = "answer" if event == "stream_end" else "reasoning"
        chunks = pending.pop(_stream_key(record, stream), [])
        if not chunks:
            continue
        completed = dict(record)
        text = completed.get("text")
        if not isinstance(text, str) or not text:
            completed["text"] = "".join(str(chunk.get("text") or "") for _, chunk in chunks)
        if include_projection_receipts:
            receipts = _projection_receipts([*(chunk for _, chunk in chunks), record])
            if receipts:
                completed[_WEBUI_PROJECTION_RECEIPTS_KEY] = receipts
        replacements[index] = completed
        dropped_indexes.update(chunk_index for chunk_index, _ in chunks)

    if not dropped_indexes:
        return turn, 0
    return [
        replacements.get(index, record)
        for index, record in enumerate(turn)
        if index not in dropped_indexes
    ], len(dropped_indexes)
