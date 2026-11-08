"""Bounded history reads during long turns and after an instance restart."""

import pytest

from cirno_core.session.display_history import HistoryFact, HistoryReader
from cirno_core.session.manager import SessionManager
from cirno_core.session.presentation_history import fact_from_record
from cirno_core.session.transcript import (
    build_webui_trace_detail_response,
    has_unfinished_transcript_tail,
)


def test_trace_expansion_and_recovery_do_not_decode_the_entire_turn(history, monkeypatch):
    key = "websocket:long-research"
    events = [{"event": "user", "text": "Run a long research task"}]
    for index in range(5000):
        events.append(
            {"event": "message", "kind": "progress", "text": f"step_{index}(" + "x" * 1100 + ")"}
        )
    history.sessions.append_history(key, [fact_from_record(event) for event in events])
    payload = history.build(key)
    assert payload["page"]["truncated_oversized_turn"]
    reference = next(
        event["trace_detail"]["ref"] for event in payload["events"] if "trace_detail" in event
    )

    # Expansion must not fall back to the unbounded whole-turn reader.
    def forbidden(*args, **kwargs):
        raise AssertionError("Whole-turn read during detail expansion or recovery")

    monkeypatch.setattr(HistoryReader, "read_entries", forbidden)
    decoded = 0
    original_decode = HistoryFact.decode

    def decode(record):
        nonlocal decoded
        decoded += 1
        return original_decode(record)

    monkeypatch.setattr(HistoryFact, "decode", decode)
    detail = history.trace(key, reference)
    assert 0 < len(detail["events"]) < 5000
    assert decoded == len(detail["events"])
    decoded = 0
    pending = history.sessions.project_history(
        key, lambda reader: has_unfinished_transcript_tail(key, history=reader)
    )
    assert pending
    assert decoded == 1
    # Reopening the instance preserves the exact range and its identity.
    reopened = SessionManager(
        history.sessions.workspace, sessions_root=history.sessions.sessions_dir.parent
    )
    replayed = reopened.project_history(
        key, lambda reader: build_webui_trace_detail_response(key, reference, history=reader)
    )
    assert replayed == detail


@pytest.mark.asyncio
async def test_old_trace_reference_is_rejected_after_clearing_conversation(history):
    key = "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"

    def seed(text):
        history.append(key, {"event": "user", "text": "question"})
        history.append(key, {"event": "message", "kind": "progress", "text": text * 40000})

    seed("a")
    reference = history.build(key)["events"][1]["trace_detail"]["ref"]
    await history.sessions.state.reset(key)
    # Runtime mutations use the admitted state owner after it has been bound.
    await history.sessions.state.append_history(
        key,
        [
            fact_from_record(event)
            for event in (
                {"event": "user", "text": "new question"},
                {"event": "message", "kind": "progress", "text": "b" * 40000},
            )
        ],
        expected_generation=None,
    )
    assert (
        await history.sessions.state.project_history(
            key, lambda reader: build_webui_trace_detail_response(key, reference, history=reader)
        )
        is None
    )


@pytest.mark.parametrize(
    "events,expected",
    [
        ([{"event": "user", "text": "question"}], False),
        (
            [
                {"event": "message", "kind": "progress", "text": "tool"},
                {"event": "context_compaction", "phase": "succeeded"},
            ],
            True,
        ),
        ([{"event": "message", "text": "answer"}, {"event": "turn_end"}], False),
        ([{"event": "turn_end", "transcript_incomplete": True}], True),
    ],
)
def test_recovery_tail_preserves_completion_and_incomplete_semantics(history, events, expected):
    key = "websocket:recover"
    history.sessions.append_history(key, [fact_from_record(event) for event in events])
    assert (
        history.sessions.project_history(
            key, lambda reader: has_unfinished_transcript_tail(key, history=reader)
        )
        is expected
    )


@pytest.mark.parametrize("count,width,byte_limit", [(12_000, 0, None), (42, 1100, 4096)])
def test_every_record_of_one_long_turn_can_be_paged_in_both_directions(history, monkeypatch, count, width, byte_limit):
    from cirno_core.session.transcript.paging import _select_transcript_page
    key = "websocket:one-long-turn"
    events = [{"event": "user", "text": "Research"}]
    if byte_limit is not None:
        monkeypatch.setattr("cirno_core.session.transcript.paging._MAX_TRANSCRIPT_PAGE_BYTES", byte_limit)
    events.extend({"event": "message", "kind": "progress", "text": f"step_{i}" + "x" * width} for i in range(count))
    events.append({"event": "turn_end"})
    history.sessions.append_history(key, [fact_from_record(event) for event in events])

    def page(**cursor):
        return history.sessions.project_history(key, lambda reader: _select_transcript_page(
            history=reader, limit=1000, **cursor,
        ))

    def positions(records):
        return {int(record["_webui_replay_identity"].rsplit(":", 1)[-1]) for record in records}

    records, metadata = page(before=None)
    seen, cursors = positions(records), set()
    oldest = metadata
    assert metadata["has_more_before"]
    while metadata["has_more_before"]:
        cursor = metadata["before_cursor"]
        assert cursor not in cursors
        cursors.add(cursor)
        records, metadata = page(before=cursor)
        assert len(records) <= 4000
        assert 0 in positions(records), "original input must anchor each slice"
        seen |= positions(records)
        oldest = metadata
    assert seen == set(range(len(events)))
    # Traverse forward from the oldest slice, using its independent frontier.
    forward, metadata = positions(records), oldest
    while metadata["has_more_after"]:
        records, metadata = page(before=None, after=metadata["after_cursor"])
        assert len(records) <= 4000
        forward |= positions(records)
    assert forward == seen
