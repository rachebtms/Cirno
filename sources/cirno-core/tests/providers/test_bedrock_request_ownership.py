"""Blocking SDK work retains an async owner through cancellation and close."""

import asyncio
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cirno_core.providers.bedrock.provider import BedrockProvider


@pytest.mark.parametrize("stage,outcome", [
    ("initialize-complete", "ok"), ("initialize-stream", "ok"),
    ("request", "ok"), ("request", "error"),
])
async def test_cancelled_request_keeps_its_blocking_worker_owned(monkeypatch, stage, outcome):
    entered, release, settled = Event(), Event(), Event()
    calls = []

    def converse(**_kwargs):
        calls.append("request")
        entered.set()
        assert release.wait(2)
        settled.set()
        if outcome == "error":
            raise OSError("fake SDK request failed after cancellation")
        return {"output": {"message": {"content": [{"text": "done"}]}}, "stopReason": "end_turn"}

    client = SimpleNamespace(converse=converse, converse_stream=converse, close=lambda: None)
    provider = BedrockProvider(client=client if stage == "request" else None)

    def make_client(**_kwargs):
        entered.set()
        assert release.wait(2)
        settled.set()
        return client

    monkeypatch.setattr(provider, "_make_client", make_client)
    method = provider.chat_stream if stage == "initialize-stream" else provider.chat
    task = asyncio.create_task(method([]))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "Cancellation abandoned its blocking worker"
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await provider.aclose()
        assert await asyncio.to_thread(settled.wait, 1)
    assert task.cancelled()
    assert settled.is_set()
    assert calls == (["request"] if stage == "request" else [])


@pytest.mark.parametrize("blocked", ["complete", "stream"])
async def test_cancelled_close_still_closes_both_owned_clients(blocked):
    entered, release, settled = Event(), Event(), Event()
    closed = []

    def close(name):
        if name == blocked:
            entered.set()
            assert release.wait(2)
        closed.append(name)
        if name == blocked:
            settled.set()

    provider = BedrockProvider()
    provider._client = SimpleNamespace(close=lambda: close("complete"))
    provider._stream_client = SimpleNamespace(close=lambda: close("stream"))
    task = asyncio.create_task(provider.aclose())
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(settled.wait, 1)
        await provider.aclose()
    assert task.cancelled()
    assert closed == ["complete", "stream"]


@pytest.mark.parametrize("broken", ["complete", "stream"])
async def test_close_attempts_other_client_before_propagating_failure(broken):
    closed = []
    problem = OSError("fake close failed")

    def close(name):
        closed.append(name)
        if name == broken:
            raise problem

    provider = BedrockProvider()
    provider._client = SimpleNamespace(close=lambda: close("complete"))
    provider._stream_client = SimpleNamespace(close=lambda: close("stream"))
    with pytest.raises(OSError) as caught:
        await provider.aclose()
    assert caught.value is problem
    assert closed == ["complete", "stream"]


async def test_successful_complete_request_preserves_result_and_external_client_ownership():
    converse = Mock(return_value={
        "output": {"message": {"content": [{"text": "done"}]}}, "stopReason": "end_turn",
    })
    close = Mock()
    provider = BedrockProvider(client=SimpleNamespace(converse=converse, close=close))
    response = await provider.chat([{"role": "user", "content": "hello"}])
    assert response.content == "done" and response.finish_reason == "stop"
    converse.assert_called_once()
    await provider.aclose()
    close.assert_not_called()
