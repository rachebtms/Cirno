"""Compatible gateway streams recover before any local tool is executed."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import httpx
import pytest
from cirno_core.agent.hook import AgentHook
from cirno_core.agent.runner.engine import AgentRunner
from cirno_core.bus.agent_events import EventSink, RetryStatusEvent
from cirno_core.providers.model_api import ModelAPICapabilities
from cirno_core.providers.openai_compat_provider import OpenAICompatProvider

from sources.development.testing.runtime import make_run_spec


def tool_delta(identity, arguments, *, name="inspect", index=0):
    return {"choices": [{"delta": {"tool_calls": [{
        "index": index, "id": identity, "function": {"name": name, "arguments": arguments},
    }]}}]}


def finish(reason="stop", content=None):
    return {"choices": [{"delta": {"content": content}, "finish_reason": reason}]}


class Stream:
    def __init__(self, chunks, *, close_error=None):
        self.chunks = chunks
        self.closed = False
        self.close_error = close_error

    async def __aiter__(self):
        for value in self.chunks:
            if isinstance(value, Exception):
                raise value
            yield value

    async def close(self):
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


def provider_for(*streams):
    provider = OpenAICompatProvider(
        api_key="fixture", default_model="fixture-model",
        model_api=ModelAPICapabilities(("chat_completions",), "chat_completions"),
    )
    create = AsyncMock(side_effect=streams)
    provider._ensure_client = AsyncMock(return_value=SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    ))
    return provider, create


class StreamingHook(AgentHook):
    def wants_streaming(self):
        return True


async def test_reused_wire_indices_reach_runner_with_separate_calls_once():
    stream = Stream([
        tool_delta("a", '{"n":'), tool_delta("b", '{"n":'),
        tool_delta("a", '1}'), tool_delta("b", '2}'), finish("tool_calls"),
    ])
    provider, create = provider_for(stream, Stream([finish(content="Done")]))
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.execute = AsyncMock(return_value="verified")
    result = await AgentRunner().run(make_run_spec(
        provider, model="fixture-model", initial_messages=[{"role": "user", "content": "Inspect both"}],
        tools=tools, max_iterations=2, max_tool_result_chars=2000,
    ))
    assert result.stop_reason == "completed"
    assert result.final_content == "Done"
    assert tools.execute.await_args_list == [call("inspect", {"n": 1}), call("inspect", {"n": 2})]
    assert create.await_count == 2
    assert stream.closed


async def test_ambiguous_stream_retries_serially_without_executing_its_partial_tools(monkeypatch):
    bad = Stream([
        {"choices": [{"delta": {"content": "Checking…"}}]},
        tool_delta("a", '{"n":'), tool_delta("b", '{"n":'), tool_delta(None, '1}'),
    ])
    good = Stream([tool_delta("verified", '{"n":2}'), finish("tool_calls")])
    provider, create = provider_for(bad, good, Stream([finish(content="Done")]))
    statuses = []
    recoveries = []
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.execute = AsyncMock(return_value="verified")

    async def sleep(_delay):
        assert bad.closed and not tools.execute.called

    async def record(event):
        if isinstance(event, RetryStatusEvent):
            statuses.append(event)

    class Hook(StreamingHook):
        async def on_stream_end(self, context, *, resuming=False):
            if resuming:
                recoveries.append(list(context.streamed_content_parts))

    monkeypatch.setattr("cirno_core.providers.retry.asyncio.sleep", sleep)
    spec = make_run_spec(
        provider, model="fixture-model", initial_messages=[{"role": "user", "content": "Inspect"}],
        tools=tools, max_iterations=2, max_tool_result_chars=2000, hook=Hook(),
    )
    spec.events = EventSink(record)
    result = await AgentRunner().run(spec)
    assert result.stop_reason == "completed"
    tools.execute.assert_awaited_once_with("inspect", {"n": 2})
    assert create.await_count == 3
    assert recoveries[0] == ["Checking…"]
    assert [(event.state, event.error_kind) for event in statuses if event.state in {"waiting", "recovered"}] == [
        ("waiting", "invalid_response"), ("recovered", "unknown"),
    ]
    assert not any("Assistant reply unavailable" in (row.get("content") or "") for row in result.messages)


@pytest.mark.parametrize("tail", [TimeoutError("trailer stalled"), httpx.RemoteProtocolError("disconnected")])
async def test_transport_failure_after_finish_keeps_completed_answer(tail):
    stream = Stream([finish(content="Verified answer"), tail])
    provider, create = provider_for(stream)
    response = await provider.chat_stream_with_retry(messages=[{"role": "user", "content": "Inspect"}])
    assert response.finish_reason == "stop"
    assert response.content == "Verified answer"
    assert create.await_count == 1
    assert stream.closed


@pytest.mark.parametrize("completed", [False, True])
async def test_cleanup_failure_does_not_replace_original_outcome(completed):
    stream = Stream(
        [finish(content="Verified answer")] if completed else [httpx.RemoteProtocolError("original disconnect")],
        close_error=RuntimeError("cleanup failed"),
    )
    provider, _ = provider_for(stream)
    response = await provider.chat_stream(messages=[{"role": "user", "content": "Inspect"}])
    assert response.finish_reason == ("stop" if completed else "error")
    if completed:
        assert response.content == "Verified answer"
    else:
        assert response.error_kind == "connection"
        assert "original disconnect" in response.content
        assert "cleanup failed" not in response.content
    assert stream.closed


async def test_final_usage_does_not_depend_on_transport_eof():
    stream = Stream([
        finish(content="Verified answer"),
        {"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 5, "prompt_cache_hit_tokens": 90}},
        AssertionError("must not read beyond finish and usage"),
    ])
    provider, _ = provider_for(stream)
    response = await provider.chat_stream(messages=[{"role": "user", "content": "Inspect"}])
    assert response.finish_reason == "stop"
    assert response.usage.cache_read_tokens == 90
    assert stream.closed


async def test_repeated_ambiguous_streams_stop_after_configured_retries_without_tools(monkeypatch):
    streams = [Stream([
        tool_delta("a", '{"n":'), tool_delta("b", '{"n":'), tool_delta(None, '1}'),
    ]) for _ in range(4)]
    provider, create = provider_for(*streams)
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.execute = AsyncMock()

    async def sleep(_delay):
        assert not tools.execute.called

    monkeypatch.setattr("cirno_core.providers.retry.asyncio.sleep", sleep)
    result = await AgentRunner().run(make_run_spec(
        provider, model="fixture-model", initial_messages=[{"role": "user", "content": "Inspect"}],
        tools=tools, max_iterations=2, max_tool_result_chars=2000,
    ))
    assert result.stop_reason == "error"
    assert result.failure_error_kind == "invalid_response"
    assert create.await_count == 4
    tools.execute.assert_not_awaited()
    assert all(stream.closed for stream in streams)
    assert "Assistant reply unavailable" in result.messages[-1]["content"]
