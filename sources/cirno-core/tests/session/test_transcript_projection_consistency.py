"""Paged transcript projections must preserve canonical answer/input semantics."""

import pytest
from cirno_core.session.display_history import HistoryFact, HistoryKind
from cirno_core.session.transcript.recovery import transcript_turn_signature


@pytest.mark.parametrize("delta,end", [("delta", "stream_end"), ("reasoning_delta", "reasoning_end")])
@pytest.mark.parametrize("snapshot", ["", None])
def test_folded_stream_keeps_an_explicit_empty_snapshot_and_only_falls_back_when_absent(history, delta, end, snapshot):
    key = "websocket:snapshot"
    for sequence, row in enumerate([
        {"event": "user", "text": "Question"},
        {"event": delta, "text": "Provisional content", "stream_id": "stream"},
        {"event": end, "text": snapshot, "stream_id": "stream"},
        {"event": "turn_end"},
    ]):
        history.append(key, {**row, "turn_id": "turn", "turn_seq": sequence})
    original = history.read(key)
    page = history.build(key)
    assert page is not None
    segment = next(event for event in page["events"] if event["event"] == end)
    assert segment["text"] == ("Provisional content" if snapshot is None else "")
    assert not any(event["event"] == delta for event in page["events"])
    if end == "stream_end":
        assert transcript_turn_signature(original) == transcript_turn_signature(page["events"])
    assert history.read(key) == original


@pytest.mark.parametrize("kind", ["supervision", "subagent", "continuation"])
def test_prompt_navigation_uses_the_same_input_eligibility_as_fork_and_user_offsets(history, kind):
    key = "websocket:prompt-inputs"
    for turn, text, origin in [
        ("first", "First user question", None),
        ("internal", "Display-only update", {"kind": kind}),
        ("second", "Second user question", None),
    ]:
        history.append(key, {"event": "user", "turn_id": turn, "text": text,
                             **({"input_origin": origin} if origin else {})})
        history.append(key, {"event": "message", "turn_id": turn, "text": f"Response to {turn}"})
        history.append(key, {"event": "turn_end", "turn_id": turn})
    page = history.prompt_page(key)
    eligible = history.sessions.project_history(key, lambda reader: reader.user_count_before(reader.turn_count))
    assert page["count"] == page["total"] == eligible == 2
    assert [(prompt["index"], prompt["preview"]) for prompt in page["prompts"]] == [
        (0, "First user question"), (1, "Second user question"),
    ]
    from cirno_core.session.transcript import PromptPageRequest
    search = history.prompt_page(key, request=PromptPageRequest(query="Display-only"))
    assert search["total"] == 0
    # Eligibility affects navigation, not the durable message displayed in the thread.
    assert any(event.get("text") == "Display-only update" for event in history.build(key)["events"])


@pytest.mark.parametrize("boundary", ["reasoning_delta", "reasoning_end"])
def test_prompt_backfill_keeps_answer_boundaries_without_decoding_reasoning_bodies(history, monkeypatch, boundary):
    key = "websocket:backfill-boundary"
    marker = "private-reasoning-body"
    for row in [
        {"event": "delta", "text": "First answer"},
        {"event": boundary, "text": marker},
        {"event": "delta", "text": "Second answer"},
        {"event": "turn_end"},
    ]:
        history.append(key, {**row, "turn_id": "turn"})
    canonical = [
        {"role": "user", "content": "Retained original question"},
        {"role": "assistant", "content": "First answer"},
        {"role": "assistant", "content": "Second answer"},
    ]
    decode = HistoryFact.decode

    def decode_without_reasoning(record):
        assert marker not in record, "navigation must not materialize the reasoning body"
        return decode(record)

    monkeypatch.setattr(HistoryFact, "decode", decode_without_reasoning)
    page = history.prompt_page(key, session_messages_loader=lambda: canonical)
    assert [(prompt["preview"], prompt["answerPreview"]) for prompt in page["prompts"]] == [
        ("Retained original question", "First answer"),
    ]
    boundaries = history.sessions.project_history(key, lambda reader: [
        fact for _, _, fact in reader.navigation()
        if fact.kind in {HistoryKind.REASONING_FRAGMENT, HistoryKind.REASONING_SEGMENT}
    ])
    assert len(boundaries) == 1
    assert boundaries[0].content == {}
