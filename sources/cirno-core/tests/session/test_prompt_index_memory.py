"""Navigation indexes release full answers and bound retained prompt snapshots."""

import tracemalloc
from types import SimpleNamespace

import pytest
from cirno_core.session.display_history import HistoryFact, HistoryKind
from cirno_core.session.transcript import prompts


def test_index_does_not_retain_full_answer_bodies_for_all_turns():
    def navigation():
        for ordinal in range(300):
            yield ordinal, 0, HistoryFact(HistoryKind.INPUT, {"text": f"question {ordinal}"}, f"turn-{ordinal}")
            yield ordinal, 1, HistoryFact(HistoryKind.ANSWER,
                                        {"text": str(ordinal) + "x" * (96 * 1024)}, f"turn-{ordinal}")

    history = SimpleNamespace(key="websocket:profile", navigation=navigation)
    tracemalloc.start()
    try:
        index = prompts._history_prompt_summaries(history)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(index.prompts) == 300
    assert all(len(item["answerPreview"]) == 240 for item in index.prompts)
    # Holding all decoded answers would retain 28 MiB before constructing summaries.
    assert peak < 4 * 1024**2


def test_index_does_not_retain_all_segments_within_one_long_execution():
    def navigation():
        yield 0, 0, HistoryFact(HistoryKind.INPUT, {"text": "Sustained research task"}, "long-turn")
        for index in range(300):
            yield 0, index + 1, HistoryFact(HistoryKind.ANSWER_SEGMENT,
                {"text": f"Research phase {index}: " + "x" * (96 * 1024)}, "long-turn")
        yield 0, 301, HistoryFact(HistoryKind.COMPLETION, {}, "long-turn")

    tracemalloc.start()
    try:
        index = prompts._history_prompt_summaries(SimpleNamespace(key="websocket:long-turn", navigation=navigation))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(index.prompts) == 1
    assert index.prompts[0]["answerPreview"].startswith("Research phase 0:")
    assert len(index.prompts[0]["answerPreview"]) == 240
    assert peak < 4 * 1024**2


def test_long_prompt_preview_does_not_copy_the_complete_input():
    text = "\n  " + "large source material " * 500000 + " \n"
    fact = HistoryFact(HistoryKind.INPUT, {"text": text}, "long-input")
    history = SimpleNamespace(key="websocket:long-input", navigation=lambda: iter([(0, 0, fact)]))
    tracemalloc.start()
    try:
        index = prompts._history_prompt_summaries(history)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert index.prompts[0]["preview"] == text.strip()[:320]
    assert peak < 1024**2


@pytest.mark.asyncio
async def test_prompt_cache_budget_evicts_old_revisions_without_losing_navigation(history, monkeypatch):
    monkeypatch.setattr(prompts, "_PROMPT_CACHE_MAX_PROMPTS", 4)
    with prompts._PROMPT_SNAPSHOT_LOCK:
        prompts._PROMPT_SNAPSHOTS.clear()
    for key in ("websocket:first", "websocket:second"):
        for i in range(3):
            history.append(key, {"event": "user", "text": f"question {i}", "turn_id": f"t{i}"})
            history.append(key, {"event": "turn_end", "turn_id": f"t{i}"})
        result = history.prompt_page(key)
        assert len(result["prompts"]) == 3
        with prompts._PROMPT_SNAPSHOT_LOCK:
            assert sum(len(view.prompts) for view in prompts._PROMPT_SNAPSHOTS.values()) <= 4
    # An evicted directory can still be reconstructed with identical stable IDs.
    again = history.prompt_page("websocket:first")
    assert [item["preview"] for item in again["prompts"]] == ["question 0", "question 1", "question 2"]
    with prompts._PROMPT_SNAPSHOT_LOCK:
        prompts._PROMPT_SNAPSHOTS.clear()
