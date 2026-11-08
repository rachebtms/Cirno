"""Completed external work remains recoverable through output storage failures."""

import asyncio
import threading
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.agent.runner.engine import AgentRunner
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.tool_calls import ToolCallRequest
from cirno_core.session.model import Session
from cirno_core.session.recovery.contracts import RUNTIME_CHECKPOINT_KEY
from cirno_core.session.recovery.checkpoints import restore_runtime_checkpoint, runtime_checkpoint_is_well_formed
from cirno_core.utils.tool_results import maybe_persist_tool_result
from cirno_usage.types import LLMUsage

from sources.development.testing.runtime import make_run_spec


def output_path(reference: str) -> Path:
    prefix = "Full output saved to workspace path: "
    return Path(reference.split(prefix, 1)[1].splitlines()[0])


def setup_execution(tmp_path):
    provider = MagicMock(spec=LLMProvider)
    provider.chat_stream_with_retry = AsyncMock(
        side_effect=[
            LLMResponse(
                content="Analyzing",
                finish_reason="tool_calls",
                tool_calls=[
                    ToolCallRequest(id="call1", name="exec", arguments={"command": "write result"})
                ],
                usage=LLMUsage.reported(input_tokens=20, output_tokens=5),
            ),
            LLMResponse(
                content="Finished", usage=LLMUsage.reported(input_tokens=50, output_tokens=2)
            ),
        ]
    )
    tools = MagicMock()
    tools.get_definitions.return_value = []
    raw = "Verified scientific output\n" * 2000
    tools.execute = AsyncMock(return_value=raw)
    checkpoints = []

    async def checkpoint(value):
        checkpoints.append(deepcopy(value))

    spec = make_run_spec(
        provider,
        model="test",
        tools=tools,
        workspace=tmp_path,
        session_key="cli:research",
        max_iterations=2,
        max_tool_result_chars=2048,
        initial_messages=[{"role": "user", "content": "Run analysis once"}],
        checkpoint_callback=checkpoint,
    )
    return provider, tools, raw, checkpoints, spec


@pytest.mark.parametrize("tool_count", [1, 2])
async def test_storage_failure_preserves_raw_completed_result_for_one_time_recovery(
    tmp_path, monkeypatch, tool_count
):
    provider, tools, raw, checkpoints, spec = setup_execution(tmp_path)
    outputs = [raw + f"Dataset {index}" for index in range(tool_count)]
    response = LLMResponse(
        content="Analyzing",
        finish_reason="tool_calls",
        tool_calls=[
            ToolCallRequest(
                id=f"call{index + 1}", name="exec", arguments={"command": f"write dataset {index}"}
            )
            for index in range(tool_count)
        ],
        usage=LLMUsage.reported(input_tokens=20, output_tokens=5),
    )
    provider.chat_stream_with_retry.side_effect = [response, LLMResponse(content="Finished")]
    tools.execute.side_effect = outputs
    from cirno_core.utils.tool_results import maybe_persist_tool_result as persist

    with monkeypatch.context() as patch:

        def fail(workspace, session_key, call_id, content, **kwargs):
            if call_id == f"call{tool_count}":
                raise OSError("Result volume is read-only")
            return persist(workspace, session_key, call_id, content, **kwargs)

        patch.setattr("cirno_core.agent.governance.results.maybe_persist_tool_result", fail)
        with pytest.raises(OSError, match="Result volume is read-only"):
            await AgentRunner().run(spec)
    assert tools.execute.await_count == tool_count
    assert provider.chat_stream_with_retry.await_count == 1
    saved = checkpoints[-1]
    assert saved["phase"] == "tools_completed"
    assert saved["pending_tool_calls"] == []
    assert [message["content"] for message in saved["completed_tool_results"]] == outputs
    assert saved["provider_state"] is None
    assert runtime_checkpoint_is_well_formed(saved)
    session = Session(
        key="cli:research",
        messages=list(spec.initial_messages),
        metadata={RUNTIME_CHECKPOINT_KEY: saved},
    )
    assert restore_runtime_checkpoint(session)
    assert not restore_runtime_checkpoint(session)
    spec.initial_messages = session.get_history()
    result = await AgentRunner().run(spec)
    assert result.final_content == "Finished"
    assert tools.execute.await_count == tool_count
    replayed = [
        message
        for message in provider.chat_stream_with_retry.await_args.kwargs["messages"]
        if message["role"] == "tool"
    ]
    assert len(replayed) == tool_count
    assert [output_path(message["content"]).read_text() for message in replayed] == outputs


@pytest.mark.parametrize("cancel", [False, True])
async def test_slow_result_write_keeps_event_loop_responsive_and_settles_before_stop(
    tmp_path, monkeypatch, cancel
):
    provider, tools, raw, checkpoints, spec = setup_execution(tmp_path)
    entered, release = threading.Event(), threading.Event()
    from cirno_core.utils.tool_results import maybe_persist_tool_result as persist

    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(3), "test did not release the output writer"
        return persist(*args, **kwargs)

    monkeypatch.setattr("cirno_core.agent.governance.results.maybe_persist_tool_result", slow)
    watchdog = threading.Timer(2, release.set)
    watchdog.start()
    task = asyncio.create_task(AgentRunner().run(spec))
    try:
        assert await asyncio.wait_for(asyncio.to_thread(entered.wait, 1), 2)
        assert not release.is_set(), "tool output storage blocked the shared runtime loop"
        assert await asyncio.sleep(0, result="status available") == "status available"
        assert not task.done()
        if cancel:
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            assert not task.done()
        release.set()
        if cancel:
            with pytest.raises(asyncio.CancelledError):
                await task
            saved = checkpoints[-1]
            assert saved["phase"] == "tools_completed"
            assert runtime_checkpoint_is_well_formed(saved)
            assert output_path(saved["completed_tool_results"][0]["content"]).read_text() == raw
            assert tools.execute.await_count == 1
            assert provider.chat_stream_with_retry.await_count == 1
        else:
            result = await task
            assert result.final_content == "Finished"
    finally:
        release.set()
        watchdog.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_reused_call_id_cannot_overwrite_or_alias_earlier_output(tmp_path):
    first = "First experiment\n" * 2000
    second = "Second experiment\n" * 2000
    before = maybe_persist_tool_result(tmp_path, "cli:research", "call1", first, max_chars=2048)
    after = maybe_persist_tool_result(tmp_path, "cli:research", "call1", second, max_chars=2048)
    assert output_path(before) != output_path(after)
    assert output_path(before).read_text() == first
    assert output_path(after).read_text() == second
    assert (
        maybe_persist_tool_result(tmp_path, "cli:research", "call1", first, max_chars=2048)
        == before
    )
