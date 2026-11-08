"""Opt-in recordings are independent, disposable and filtered before pagination."""

import sqlite3
import tracemalloc
from uuid import uuid4

import pytest
from cirno_core.observability.recordings import TraceRecordings
from cirno_core.session.display_history import HistoryFact, HistoryKind
from cirno_core.session.manager import SessionManager
from cirno_server.webui.trace_api import TraceAPI


@pytest.fixture
async def capture(monkeypatch, tmp_path):
    recordings = TraceRecordings()
    monkeypatch.setattr(
        "cirno_core.observability.recordings.current_recordings", lambda: recordings
    )
    monkeypatch.setattr("cirno_server.webui.trace_api.current_recordings", lambda: recordings)
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    session = await sessions.state.get("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb")
    api = TraceAPI()
    identifier = str(uuid4())
    yield sessions, session, recordings, api, identifier
    recordings.close_all()
    await sessions.state.aclose()


async def append(sessions, session, text, kind=HistoryKind.INPUT):
    await sessions.state.append_history(
        session.key,
        [HistoryFact(kind, {"text": text}, "turn", created_at_ms=1000)],
        expected_generation=session.generation,
    )


async def test_only_captures_after_start_pause_skips_events_clear_and_close_delete_recording(
    capture,
):
    sessions, session, recordings, api, identifier = capture
    await append(sessions, session, "before opening")
    assert not recordings.active
    assert recordings.begin(session.key, "model", [], []) == []
    values = {"recording_id": identifier}
    opened = await api.action("create", values)
    assert opened["running"]
    await append(sessions, session, "captured")
    assert (await api.action("events", values))["events"][0]["summary"] == "captured"
    await api.action("pause", values)
    await append(sessions, session, "while paused")
    assert (await api.action("events", values))["count"] == 1
    await api.action("start", values)
    await append(sessions, session, "resumed")
    page = await api.action("events", values)
    assert [row["summary"] for row in page["events"]] == ["resumed", "captured"]
    old_epoch = page["epoch"]
    path = recordings._recordings[identifier].path
    cleared = await api.action("clear", values)
    assert not path.exists() and cleared["epoch"] != old_epoch
    assert (await api.action("events", values))["events"] == []
    with pytest.raises(ValueError, match="cleared"):
        await api.action("detail", {**values, "event_id": 1, "epoch": old_epoch})
    path = recordings._recordings[identifier].path
    await api.action("close", values)
    assert not path.exists() and not recordings.active
    assert (await api.action("close", values)) == {"ok": True}
    # Clearing diagnostics never deletes actual conversation history.
    facts = await sessions.state.project_history(session.key, lambda reader: reader.all_facts())
    assert [fact.content["text"] for fact in facts] == [
        "before opening",
        "captured",
        "while paused",
        "resumed",
    ]


async def test_types_and_source_filters_apply_to_entire_recording_not_only_current_page(capture):
    _, _, recordings, api, identifier = capture
    values = {"recording_id": identifier}
    await api.action("create", values)
    for index in range(265):
        recordings.facts(
            "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb" if index % 2 else "websocket:worker",
            [
                HistoryFact(
                    HistoryKind.TOOL_ACTIVITY,
                    {
                        "tool_events": [
                            {
                                "name": "nodes.execute",
                                "phase": "end",
                                "arguments": {"command": str(index)},
                            }
                        ]
                    },
                    "turn",
                    created_at_ms=1000,
                )
            ],
        )
    cursor, seen = None, []
    for _ in range(4):
        page = await api.action(
            "events",
            {**values, "before": cursor, "kind": "tool", "session_key": "websocket:worker"},
        )
        assert all(event["session_key"] == "websocket:worker" for event in page["events"])
        seen.extend(row["id"] for row in page["events"])
        cursor = page["before"]
        if cursor is None:
            break
    assert len(seen) == len(set(seen)) == 133
    assert seen == sorted(seen, reverse=True)
    assert page["sources"] == ["websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", "websocket:worker"]
    detail = await api.action("detail", {**values, "event_id": seen[0], "epoch": page["epoch"]})
    assert detail["event"]["content"]["tool_events"][0]["arguments"]["command"] == "264"


async def test_request_snapshot_finishes_after_pause_but_cannot_reappear_after_clear(capture):
    _, session, recordings, api, identifier = capture
    values = {"recording_id": identifier}
    await api.action("create", values)
    handles = recordings.begin(
        session.key, "DeepSeek", [{"role": "system", "content": "real system prompt"}], []
    )
    await api.action("pause", values)
    recordings.finish(handles, {"content": "answer"}, "completed")
    page = await api.action("events", values)
    assert page["events"][0]["status"] == "completed"
    detail = await api.action(
        "detail", {**values, "event_id": page["events"][0]["id"], "epoch": page["epoch"]}
    )
    assert detail["messages"][0]["content"] == "real system prompt"
    assert detail["response"]["content"] == "answer"
    await api.action("clear", values)
    recordings.finish(handles, {"content": "late answer"}, "completed")
    assert (await api.action("events", values))["events"] == []


async def test_separate_tabs_do_not_clear_or_pause_each_other(capture):
    _, session, recordings, api, first = capture
    second = str(uuid4())
    await api.action("create", {"recording_id": first})
    await api.action("create", {"recording_id": second})
    await api.action("pause", {"recording_id": first})
    recordings.facts(
        session.key, [HistoryFact(HistoryKind.REASONING_SEGMENT, {"text": "thinking"})]
    )
    assert (await api.action("events", {"recording_id": first}))["count"] == 0
    assert (await api.action("events", {"recording_id": second}))["count"] == 1
    await api.action("close", {"recording_id": first})
    assert recordings.active


async def test_large_recording_headers_remain_bounded_and_storage_failure_only_stops_recording(
    capture, monkeypatch
):
    _, session, recordings, api, identifier = capture
    values = {"recording_id": identifier}
    await api.action("create", values)
    recordings.facts(
        session.key,
        [
            HistoryFact(
                HistoryKind.TOOL_ACTIVITY,
                {"tool_events": [{"name": "shell.exec", "result": "x" * 1_000_000}]},
            )
            for _ in range(20)
        ],
    )
    tracemalloc.start()
    try:
        page = await api.action("events", values)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 4 * 1024 * 1024 and len(str(page)) < 15000
    record = recordings._recordings[identifier]
    monkeypatch.setattr(
        record, "fact", lambda *args: (_ for _ in ()).throw(sqlite3.OperationalError("disk full"))
    )
    recordings.facts(session.key, [HistoryFact(HistoryKind.INPUT, {"text": "still runs"})])
    assert not recordings.active
    assert (await api.action("events", values))["reason"] == "storage_error"


async def test_cancel_while_snapshot_is_starting_settles_it_as_cancelled(capture, monkeypatch):
    import asyncio
    import threading

    from cirno_core.observability.requests import begin_request

    _, session, recordings, api, identifier = capture
    values = {"recording_id": identifier}
    await api.action("create", values)
    entered, release = threading.Event(), threading.Event()
    original = recordings.begin

    def delayed(*args):
        entered.set()
        assert release.wait(3)
        return original(*args)

    monkeypatch.setattr(recordings, "begin", delayed)
    task = asyncio.create_task(begin_request(recordings, session.key, "model", [], []))
    await asyncio.to_thread(entered.wait, 3)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await api.action("events", values))["events"][0]["status"] == "cancelled"


@pytest.mark.parametrize("persist", [True, False])
async def test_real_runner_only_records_persistent_provider_calls_when_enabled(capture, persist):
    from unittest.mock import AsyncMock, MagicMock

    from cirno_core.agent.runner.engine import AgentRunner
    from cirno_core.agent.tools.context import RequestContext, request_context
    from cirno_core.providers.base import LLMProvider
    from cirno_core.providers.contracts import LLMResponse
    from cirno_core.providers.generation import GenerationSettings

    from sources.development.testing.runtime import make_run_spec

    _, session, _, api, identifier = capture
    values = {"recording_id": identifier}
    await api.action("create", values)
    provider = MagicMock(spec=LLMProvider)
    provider.generation = GenerationSettings()
    provider.chat_stream_with_retry = AsyncMock(
        return_value=LLMResponse(content="completed answer")
    )
    tools = MagicMock()
    tools.get_definitions.return_value = []
    with request_context(
        RequestContext(
            channel="websocket",
            chat_id="b1ec9323-2155-5f24-bc56-1da2f59aeecb",
            session_key=session.key,
            session_generation=session.generation,
            persist_session=persist,
        )
    ):
        result = await AgentRunner().run(
            make_run_spec(
                provider,
                model="captured-model",
                initial_messages=[
                    {"role": "system", "content": "exact instructions"},
                    {"role": "user", "content": "hello"},
                ],
                tools=tools,
                session_key=session.key,
                max_iterations=1,
                max_tool_result_chars=1000,
            )
        )
    assert result.final_content == "completed answer"
    page = await api.action("events", values)
    assert len(page["events"]) == int(persist)
    if persist:
        detail = await api.action(
            "detail", {**values, "event_id": page["events"][0]["id"], "epoch": page["epoch"]}
        )
        assert detail["messages"][0]["content"] == "exact instructions"
        assert detail["response"]["content"] == "completed answer"


async def test_unencodable_snapshot_pauses_capture_instead_of_failing_model_execution(capture):
    _, session, recordings, api, identifier = capture
    values = {"recording_id": identifier}
    await api.action("create", values)
    assert recordings.begin(session.key, "model", [{"role": "user", "content": "lone surrogate: \ud800"}], []) == []
    assert not recordings.active
    assert (await api.action("events", values))["reason"] == "storage_error"
