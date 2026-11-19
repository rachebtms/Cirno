"""Visual probe requests finish cleanup before their owning call settles."""
import asyncio
from types import SimpleNamespace

import pytest
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.media_capabilities import probe_visual_inputs
from cirno_core.providers.requests import ProviderRequestExecutor


def clip_resource(monkeypatch, *, missing=False):
    def read():
        if missing:
            raise FileNotFoundError("Missing video sample")
        return b"fake-video-sample"
    resource = SimpleNamespace(read_bytes=read)
    resource.joinpath = lambda *_parts: resource
    monkeypatch.setattr("importlib.resources.files", lambda *_args: resource)


@pytest.mark.parametrize("missing_clip", [False, True])
async def test_visual_probe_peer_failure_drains_the_other_request(monkeypatch, missing_clip):
    clip_resource(monkeypatch, missing=missing_clip)
    stopped = asyncio.Event()
    requests = []
    async def complete(_executor, **kwargs):
        kind = kwargs["messages"][0]["content"][1]["type"]
        if kind == "video_url":
            raise RuntimeError("Video response could not be decoded")
        requests.append(asyncio.current_task())
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
    monkeypatch.setattr(ProviderRequestExecutor, "complete", complete)
    try:
        with pytest.raises(FileNotFoundError if missing_clip else RuntimeError):
            await asyncio.wait_for(probe_visual_inputs(object(), model="fake", video_transport=True), 1)
        assert stopped.is_set(), "The owner returned while its image request was still running"
        assert all(task.done() for task in requests)
    finally:
        for task in requests:
            task.cancel()
        await asyncio.gather(*requests, return_exceptions=True)


async def test_visual_probe_repeated_cancellation_drains_request_cleanup(monkeypatch):
    started, closing = asyncio.Event(), asyncio.Event()
    release_close, closed = asyncio.Event(), asyncio.Event()
    async def complete(_executor, **_kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            closing.set()
            await release_close.wait()
            closed.set()
    monkeypatch.setattr(ProviderRequestExecutor, "complete", complete)
    operation = asyncio.create_task(probe_visual_inputs(object(), model="fake", video_transport=True, video=False))
    try:
        await asyncio.wait_for(started.wait(), 1)
        operation.cancel()
        await asyncio.wait_for(closing.wait(), 1)
        operation.cancel()
        await asyncio.sleep(0)
        finished_before_close = operation.done()
        release_close.set()
        result, = await asyncio.wait_for(asyncio.gather(operation, return_exceptions=True), 1)
        assert not finished_before_close
        assert closed.is_set()
        assert isinstance(result, asyncio.CancelledError)
    finally:
        release_close.set()
        await asyncio.gather(operation, return_exceptions=True)


@pytest.mark.parametrize(("image", "video"), [(True, True), (True, False), (False, True), (False, False)])
async def test_visual_probe_keeps_results_attached_to_enabled_inputs(monkeypatch, image, video):
    clip_resource(monkeypatch)
    monkeypatch.setattr("secrets.SystemRandom.sample", lambda *_args: ["green", "blue", "red"])
    calls = []
    async def complete(_executor, **kwargs):
        calls.append(kwargs["messages"][0]["content"][1]["type"])
        return LLMResponse(content="green blue red")
    monkeypatch.setattr(ProviderRequestExecutor, "complete", complete)
    result = await probe_visual_inputs(object(), model="fake", video_transport=True, image=image, video=video)
    expected = {kind for kind, enabled in (("image", image), ("video", video)) if enabled}
    assert set(result) == expected
    assert set(calls) == {kind + "_url" for kind in expected}
    assert all(value["supported"] is True for value in result.values())


async def test_video_without_native_transport_does_not_submit_a_provider_request(monkeypatch):
    clip_resource(monkeypatch, missing=True)
    async def unexpected(*_args, **_kwargs):
        pytest.fail("A video request was submitted to an API without native video transport")
    monkeypatch.setattr(ProviderRequestExecutor, "complete", unexpected)
    result = await probe_visual_inputs(object(), model="fake", video_transport=False, image=False)
    assert result["video"]["supported"] is None
    assert "no native video input transport" in result["video"]["detail"]
