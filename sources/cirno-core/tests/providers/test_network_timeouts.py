"""Saved network timeouts reach SDK, HTTP and WebSocket provider transports."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from cirno_core.config.schema import Config
from cirno_core.providers.factory import make_provider
from cirno_core.providers.openai_responses.backend import ResponsesBackend
from cirno_core.providers.timeouts import ProviderTimeouts


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["custom", "anthropic", "bedrock", "azure_openai", "openai_codex", "xai_grok"])
async def test_saved_timeouts_override_constructor_environment_defaults(name, monkeypatch):
    monkeypatch.setenv("CIRNO_STREAM_IDLE_TIMEOUT_S", "0.01")
    config = Config.model_validate({
        "agents": {"defaults": {"provider": name, "model": "example"}},
        "providers": {name: {"apiKey": "fixture", "apiBase": "https://models.example/v1"}},
        "network": {"requestTimeoutS": 137, "streamIdleTimeoutS": 241},
    })
    provider = make_provider(config)
    try:
        assert provider.request_timeout_s == 137
        assert provider.stream_idle_timeout_s == 241
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_responses_sdk_receives_configured_nonstreaming_response_timeout():
    policy = ProviderTimeouts(request_s=137, stream_idle_s=241)
    create = AsyncMock(return_value={"output": [{"type": "message", "content": [
        {"type": "output_text", "text": "ok"},
    ]}]})
    backend = ResponsesBackend(timeouts=policy)
    result = await backend.sdk_request(SimpleNamespace(responses=SimpleNamespace(create=create)),
                                       {"model": "fixture", "input": []}, provider="fixture")
    assert result.content == "ok"
    timeout = create.call_args.kwargs["timeout"]
    assert timeout.read == 137
    assert timeout.connect == 137


@pytest.mark.asyncio
async def test_responses_sse_keeps_connection_and_idle_timeouts_separate(monkeypatch):
    seen = []
    real_client = httpx.AsyncClient

    def handle(request):
        seen.append(request.extensions["timeout"])
        return httpx.Response(200, text='data: {"type":"response.completed","response":{"status":"completed"}}\n\n')

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handle), **kwargs,
    ))
    await ResponsesBackend.sse_request("https://models.example/v1/responses", {}, {"input": []},
        timeouts=ProviderTimeouts(request_s=137, stream_idle_s=241),
        error_factory=lambda *args: AssertionError(args))
    assert seen == [{"connect": 137, "read": 241, "write": 137, "pool": 137}]


@pytest.mark.asyncio
async def test_bedrock_builds_lazy_clients_with_current_response_and_stream_timeouts(monkeypatch):
    boto3 = pytest.importorskip("boto3")
    from cirno_core.providers.bedrock.provider import BedrockProvider

    settings = []
    closed = []

    def client(service, **kwargs):
        settings.append(kwargs["config"])
        return SimpleNamespace(close=lambda: closed.append(service))

    monkeypatch.setattr(boto3, "Session", lambda **kwargs: SimpleNamespace(client=client))
    provider = BedrockProvider(region="us-east-1")
    assert settings == []
    provider.request_timeout_s = 137
    provider.stream_idle_timeout_s = 241
    await asyncio.to_thread(provider._get_client)
    await asyncio.to_thread(provider._get_client, stream=True)
    await provider.aclose()
    assert [(item.connect_timeout, item.read_timeout) for item in settings] == [(137, 137), (137, 241)]
    assert closed == ["bedrock-runtime", "bedrock-runtime"]
