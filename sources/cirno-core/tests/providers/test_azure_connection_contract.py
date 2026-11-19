"""Azure connection options reach fake clients without creating SDK transports."""

import asyncio
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_core.config.models import ModelPresetConfig
from cirno_core.providers import azure_openai_provider as azure
from cirno_core.providers.factory import _make_provider_core
from cirno_core.providers.retry import ProviderRetryPolicy


@pytest.fixture
def clients(monkeypatch):
    http = Mock(return_value=SimpleNamespace(aclose=AsyncMock()))
    sdk = Mock(return_value=SimpleNamespace(close=AsyncMock()))
    monkeypatch.setattr(azure, "DefaultAsyncHttpxClient", http, raising=False)
    monkeypatch.setattr(azure, "AsyncOpenAI", sdk)
    return http, sdk


@pytest.mark.parametrize("proxy", [None, "http://proxy.test:8080"])
@pytest.mark.parametrize("aad", [False, True])
async def test_explicit_proxy_policy_reaches_data_and_aad_clients(monkeypatch, clients, proxy, aad):
    http, sdk = clients
    token = Mock(return_value=SimpleNamespace(aclose=AsyncMock()))
    monkeypatch.setattr(azure, "_AzureTokenProvider", token)
    provider = azure.AzureOpenAIProvider(api_key="" if aad else "fake-key", api_base="https://azure.test", proxy=proxy)
    http.assert_called_once_with(proxy=proxy, trust_env=False)
    assert sdk.call_args.kwargs["http_client"] is http.return_value
    if aad:
        token.assert_called_once_with(proxy=proxy, timeouts=provider.timeouts)
    else:
        token.assert_not_called()
    await provider.aclose()


@pytest.mark.parametrize("proxy", [None, "http://proxy.test:8080"])
async def test_aad_http_pipeline_uses_explicit_proxy_and_ignores_environment(monkeypatch, proxy):
    credential = SimpleNamespace(get_token=AsyncMock(return_value=SimpleNamespace(token="fake-token")), close=AsyncMock())
    factory = Mock(return_value=credential)
    modules = {name: ModuleType(name) for name in ("azure", "azure.identity", "azure.identity.aio")}
    modules["azure.identity.aio"].DefaultAzureCredential = factory
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    token = azure._AzureTokenProvider(proxy=proxy)
    factory.assert_called_once_with(use_env_settings=False, proxies={"http": proxy, "https": proxy} if proxy else None)
    assert await token() == "fake-token"
    await token.aclose()
    credential.close.assert_awaited_once()


def test_factory_forwards_the_configured_azure_proxy(monkeypatch):
    configured = SimpleNamespace(use_proxy=True, api_key="fake-key", api_base="https://azure.test")
    route = SimpleNamespace(model="deployment", provider_name="azure_openai", provider_config=configured, spec=None, backend="azure_openai")
    monkeypatch.setattr("cirno_core.providers.factory.resolve_provider_route", lambda *_args, **_kwargs: route)
    fake = SimpleNamespace(retry_policy=ProviderRetryPolicy())
    constructor = Mock(return_value=fake)
    monkeypatch.setattr(azure, "AzureOpenAIProvider", constructor)
    config = SimpleNamespace(network=SimpleNamespace(resolve_proxy=Mock(return_value="http://proxy.test:8080"), stream_idle_timeout_s=120, request_timeout_s=120, provider_max_retries=3))
    assert _make_provider_core(config, preset=ModelPresetConfig(model="deployment")) is fake
    assert constructor.call_args.kwargs["proxy"] == "http://proxy.test:8080"


@pytest.mark.parametrize("endpoint,expected", [
    ("https://azure.test", "https://azure.test/openai/v1/"),
    ("https://azure.test/", "https://azure.test/openai/v1/"),
    ("https://azure.test/openai", "https://azure.test/openai/v1/"),
    ("https://azure.test/openai/v1", "https://azure.test/openai/v1/"),
    ("https://azure.test/gateway/openai/v1/", "https://azure.test/gateway/openai/v1/"),
])
async def test_azure_endpoint_does_not_duplicate_the_responses_base(clients, endpoint, expected):
    _, sdk = clients
    provider = azure.AzureOpenAIProvider(api_key="fake-key", api_base=endpoint)
    assert sdk.call_args.kwargs["base_url"] == expected
    await provider.aclose()


@pytest.mark.parametrize("stage", ["backend", "client", "credential"])
async def test_repeated_cancel_does_not_abandon_azure_close(stage):
    entered, release = asyncio.Event(), asyncio.Event()
    closed = []

    async def close(name):
        if name == stage:
            entered.set()
            await release.wait()
        closed.append(name)

    provider = azure.AzureOpenAIProvider.__new__(azure.AzureOpenAIProvider)
    provider._responses = SimpleNamespace(aclose=lambda: close("backend"))
    provider._client = SimpleNamespace(close=lambda: close("client"))
    provider._token_provider = SimpleNamespace(aclose=lambda: close("credential"))
    task = asyncio.create_task(provider.aclose())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    assert closed == ["backend", "client", "credential"]


@pytest.mark.parametrize("stage", ["backend", "client", "credential"])
async def test_close_failure_still_attempts_all_azure_resources(stage):
    closed = []
    problem = OSError("fake Azure close failure")

    async def close(name):
        closed.append(name)
        if name == stage:
            raise problem

    provider = azure.AzureOpenAIProvider.__new__(azure.AzureOpenAIProvider)
    provider._responses = SimpleNamespace(aclose=lambda: close("backend"))
    provider._client = SimpleNamespace(close=lambda: close("client"))
    provider._token_provider = SimpleNamespace(aclose=lambda: close("credential"))
    with pytest.raises(OSError) as caught:
        await provider.aclose()
    assert caught.value is problem
    assert closed == ["backend", "client", "credential"]


async def test_aad_acquisition_obeys_the_current_configured_request_timeout(monkeypatch, clients):
    settled = asyncio.Event()

    async def get_token(_scope):
        try:
            await asyncio.Future()
        finally:
            settled.set()

    credential = SimpleNamespace(get_token=AsyncMock(side_effect=get_token), close=AsyncMock())
    modules = {name: ModuleType(name) for name in ("azure", "azure.identity", "azure.identity.aio")}
    modules["azure.identity.aio"].DefaultAzureCredential = Mock(return_value=credential)
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    provider = azure.AzureOpenAIProvider(api_key="", api_base="https://azure.test")
    provider.request_timeout_s = 0.01
    task = asyncio.create_task(provider._token_provider())
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(task, 1)
        assert not task.cancelled() and task.cancelling() == 0
        assert settled.is_set()
        credential.get_token.assert_awaited_once()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await provider.aclose()
