"""Copilot proxy ownership reaches model requests and device authorization."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_core.config.models import ModelPresetConfig
from cirno_core.providers import github_copilot_oauth as oauth
from cirno_core.providers import github_copilot_provider as copilot
from cirno_core.providers.factory import _make_provider_core
from cirno_core.providers.retry import ProviderRetryPolicy


@pytest.mark.parametrize("proxy", [None, "http://proxy.test:8080"])
def test_constructor_forwards_proxy_to_shared_model_transport(monkeypatch, proxy):
    constructor = Mock(return_value=None)
    monkeypatch.setattr(copilot.OpenAICompatProvider, "__init__", constructor)
    copilot.GitHubCopilotProvider(proxy=proxy)
    assert constructor.call_args.kwargs["proxy"] == proxy


def test_factory_passes_resolved_copilot_proxy(monkeypatch):
    route = SimpleNamespace(model="github-copilot/gpt-4.1", provider_name="github_copilot", provider_config=SimpleNamespace(use_proxy=True), spec=None, backend="github_copilot", model_api=None)
    monkeypatch.setattr("cirno_core.providers.factory.resolve_provider_route", lambda *_args, **_kwargs: route)
    fake = SimpleNamespace(retry_policy=ProviderRetryPolicy())
    constructor = Mock(return_value=fake)
    monkeypatch.setattr(copilot, "GitHubCopilotProvider", constructor)
    config = SimpleNamespace(network=SimpleNamespace(resolve_proxy=Mock(return_value="http://proxy.test:8080"), stream_idle_timeout_s=120, request_timeout_s=120, provider_max_retries=3))
    assert _make_provider_core(config, preset=ModelPresetConfig(model=route.model)) is fake
    assert constructor.call_args.kwargs["proxy"] == "http://proxy.test:8080"


@pytest.mark.parametrize("proxy", [None, "http://proxy.test:8080"])
async def test_access_token_exchange_obeys_explicit_proxy_policy(monkeypatch, proxy):
    provider = copilot.GitHubCopilotProvider.__new__(copilot.GitHubCopilotProvider)
    provider._proxy = proxy
    provider._copilot_access_token = None
    provider._copilot_expires_at = 0
    provider._copilot_token_lock = asyncio.Lock()
    client = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"token": "fake-copilot", "refresh_in": 1500},
    )))
    manager = AsyncMock()
    manager.__aenter__.return_value = client
    constructor = Mock(return_value=manager)
    monkeypatch.setattr(copilot.httpx, "AsyncClient", constructor)
    monkeypatch.setattr(copilot, "_load_github_token", lambda: SimpleNamespace(access="fake-github"))
    assert await provider._get_copilot_access_token() == "fake-copilot"
    assert constructor.call_args.kwargs.get("proxy") == proxy
    assert constructor.call_args.kwargs["trust_env"] is False
    assert await provider._get_copilot_access_token() == "fake-copilot"
    client.get.assert_awaited_once()
    manager.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("proxy", [None, "http://proxy.test:8080"])
def test_device_login_uses_explicit_proxy_policy(monkeypatch, proxy):
    class StopBeforeRequestError(Exception):
        pass

    constructor = Mock(side_effect=StopBeforeRequestError)
    monkeypatch.setattr(copilot.httpx, "Client", constructor)
    with pytest.raises(StopBeforeRequestError):
        copilot.login_github_copilot(proxy=proxy, open_browser=False, persist=False)
    assert constructor.call_args.kwargs.get("proxy") == proxy
    assert constructor.call_args.kwargs["trust_env"] is False


def test_device_flow_forwards_proxy_without_starting_a_thread(monkeypatch):
    login = Mock(return_value=SimpleNamespace(access="fake-token"))
    monkeypatch.setattr(oauth, "login_github_copilot", login)
    flow = oauth.GitHubCopilotOAuthFlow(proxy="http://proxy.test:8080")
    flow._run()
    assert login.call_args.kwargs["proxy"] == "http://proxy.test:8080"
    assert login.call_args.kwargs["persist"] is False
    assert flow._done.is_set()


def test_cancelled_device_login_never_opens_transport(monkeypatch):
    cancelled = threading.Event()
    cancelled.set()
    constructor = Mock(side_effect=AssertionError("cancelled login opened a transport"))
    monkeypatch.setattr(copilot.httpx, "Client", constructor)
    with pytest.raises(RuntimeError, match="cancelled"):
        copilot.login_github_copilot(cancelled=cancelled, open_browser=False, persist=False)
    constructor.assert_not_called()


def test_cancelled_token_poll_does_not_request_account_or_save(monkeypatch):
    cancelled = threading.Event()
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    def post(url, **_kwargs):
        if url.endswith("/device/code"):
            payload = {"device_code": "fake", "user_code": "CODE", "expires_in": 60}
        else:
            cancelled.set()
            payload = {"access_token": "fake-token"}
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    client.post.side_effect = post
    storage = SimpleNamespace(save=Mock())
    monkeypatch.setattr(copilot.httpx, "Client", Mock(return_value=client))
    monkeypatch.setattr(copilot, "get_storage", lambda: storage)
    with pytest.raises(RuntimeError, match="cancelled"):
        copilot.login_github_copilot(cancelled=cancelled, open_browser=False, print_fn=lambda _: None)
    client.get.assert_not_called()
    storage.save.assert_not_called()
