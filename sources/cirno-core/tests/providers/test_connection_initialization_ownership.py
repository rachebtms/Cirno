"""Configuration and owned SDK client lifetimes, using constructor substitutes."""

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from cirno_core.agent.model_runtime import ModelRuntimeResolver
from cirno_core.config.schema import Config
from cirno_core.providers import openai_compat_provider as compat
from cirno_core.providers.factory import make_provider
from cirno_core.providers.generation import GenerationSettings
from cirno_core.utils.llm_runtime import LLMRuntime


def config_for(provider, **connection):
    return Config.model_validate(
        {
            "agents": {"defaults": {"model_preset": "fixture"}},
            "model_presets": {"fixture": {"provider": provider, "model": "fixture-model"}},
            "providers": {provider: {"api_key": "fixture-key", **connection}},
            "network": {"proxy": "http://proxy.example:8080"},
        }
    )


@pytest.mark.parametrize("name", ["http-referer", "x-openrouter-title", "X-Session-Affinity"])
def test_explicit_connection_header_replaces_auto_header_case_insensitively(name):
    provider = make_provider(config_for("openrouter", extra_headers={name: "owner-choice"}))
    headers = httpx.Headers(provider._default_headers)
    assert headers.get_list(name) == ["owner-choice"]


@pytest.mark.parametrize("enabled", [False, True])
def test_anthropic_factory_uses_only_explicit_proxy(monkeypatch, enabled):
    http_client = Mock(aclose=AsyncMock())
    sdk = SimpleNamespace(
        DefaultAsyncHttpxClient=Mock(return_value=http_client),
        AsyncAnthropic=Mock(return_value=SimpleNamespace(close=AsyncMock())),
    )
    monkeypatch.setitem(sys.modules, "anthropic", sdk)
    make_provider(config_for("anthropic", use_proxy=enabled))
    sdk.DefaultAsyncHttpxClient.assert_called_once_with(
        proxy="http://proxy.example:8080" if enabled else None,
        trust_env=False,
    )
    assert sdk.AsyncAnthropic.call_args.kwargs["http_client"] is http_client
    assert sdk.AsyncAnthropic.call_args.kwargs["max_retries"] == 0


async def test_failed_openai_sdk_initialization_closes_transport_and_allows_retry(monkeypatch):
    first = SimpleNamespace(aclose=AsyncMock())
    second = SimpleNamespace(aclose=AsyncMock())
    sdk = SimpleNamespace(close=AsyncMock())
    failure = ValueError("fixture constructor failure")
    monkeypatch.setattr(httpx, "AsyncClient", Mock(side_effect=[first, second]))
    constructor = Mock(side_effect=[failure, sdk])
    monkeypatch.setattr(compat, "AsyncOpenAI", constructor)
    provider = compat.OpenAICompatProvider(api_key="fixture")
    with pytest.raises(ValueError) as caught:
        await provider._ensure_client()
    assert caught.value is failure
    first.aclose.assert_awaited_once()
    assert provider._client is None
    assert await provider._ensure_client() is sdk
    second.aclose.assert_not_awaited()
    assert await provider._ensure_client() is sdk
    assert constructor.call_count == 2
    await provider.aclose()
    sdk.close.assert_awaited_once()


async def test_cancelled_initialization_drains_transport_before_unlocking_retry(monkeypatch):
    entered, release, settled = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def close():
        entered.set()
        await release.wait()
        settled.set()

    first = SimpleNamespace(aclose=close)
    second = SimpleNamespace(aclose=AsyncMock())
    sdk = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(httpx, "AsyncClient", Mock(side_effect=[first, second]))
    constructor = Mock(side_effect=[ValueError("fixture constructor failure"), sdk])
    monkeypatch.setattr(compat, "AsyncOpenAI", constructor)
    provider = compat.OpenAICompatProvider(api_key="fixture")
    owner = asyncio.create_task(provider._ensure_client())
    retry = None
    try:
        await entered.wait()
        owner.cancel()
        await asyncio.sleep(0)
        owner.cancel()
        retry = asyncio.create_task(provider._ensure_client())
        for _ in range(5):
            await asyncio.sleep(0)
        assert not owner.done()
        assert not retry.done()
        assert constructor.call_count == 1
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await owner
        assert settled.is_set()
        assert await retry is sdk
        assert constructor.call_count == 2
    finally:
        release.set()
        await asyncio.gather(owner, *([retry] if retry is not None else []), return_exceptions=True)
        await provider.aclose()


async def test_runtime_shutdown_retains_peer_failures_after_closing_all_providers():
    failure = ValueError("fixture provider close failed")
    first = Mock(aclose=AsyncMock(side_effect=failure))
    second = Mock(aclose=AsyncMock())
    resolver = ModelRuntimeResolver(
        LLMRuntime(
            provider=first,
            model="fixture",
            generation=GenerationSettings(),
            context_window_tokens=4096,
        )
    )
    resolver._providers.add(second)
    with pytest.raises(ExceptionGroup) as caught:
        await resolver.aclose()
    assert caught.value.exceptions == (failure,)
    first.aclose.assert_awaited_once()
    second.aclose.assert_awaited_once()
    await resolver.aclose()
    first.aclose.assert_awaited_once()
    second.aclose.assert_awaited_once()


@pytest.mark.parametrize("owner_kind", ["client", "resolver"])
async def test_accepted_client_close_survives_repeated_owner_cancellation(owner_kind):
    entered, release, settled = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def close():
        entered.set()
        await release.wait()
        settled.set()

    provider = compat.OpenAICompatProvider(api_key="fixture")
    provider._client = SimpleNamespace(close=close)
    if owner_kind == "client":
        operation = provider.aclose()
    else:
        leaf = Mock(aclose=close)
        runtime = LLMRuntime(
            provider=leaf,
            model="fixture",
            generation=GenerationSettings(),
            context_window_tokens=4096,
        )
        resolver = ModelRuntimeResolver(runtime)
        operation = resolver.aclose()
    task = asyncio.create_task(operation)
    try:
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert settled.is_set()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
