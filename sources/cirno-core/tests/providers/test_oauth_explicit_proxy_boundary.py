"""Owned OAuth discovery and Responses HTTP paths use only their explicit proxy."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import httpx
import pytest
from cirno_core.providers import github_copilot_provider as copilot
from cirno_core.providers import openai_codex_provider as codex
from cirno_core.providers import xai_grok_provider as xai
from cirno_core.providers import xai_oauth
from cirno_core.providers.openai_responses import ResponsesBackend, websocket


def response(payload):
    return httpx.Response(
        200, json=payload, request=httpx.Request("GET", "https://fixture.example/models")
    )


@pytest.mark.parametrize("provider", ["codex", "xai", "copilot"])
@pytest.mark.parametrize("proxy", [None, "http://proxy.example:8080"])
def test_oauth_catalog_fetch_respects_disabled_and_explicit_proxy(monkeypatch, provider, proxy):
    token = SimpleNamespace(access="fixture-token", account_id="fixture-account")
    storage = SimpleNamespace(load=lambda: token)
    client = MagicMock()
    client.__enter__.return_value = client
    constructor = Mock(return_value=client)
    monkeypatch.setattr(httpx, "Client", constructor)
    if provider == "codex":
        monkeypatch.setattr(codex, "get_codex_token", lambda **_kwargs: token)
        monkeypatch.setattr(codex, "token_storage", lambda *_args: storage)
        client.get.return_value = response({"models": [{"slug": "fixture-model"}]})
        models = codex._fetch_openai_codex_models(proxy)
    elif provider == "xai":
        monkeypatch.setattr(xai, "get_xai_oauth_token", lambda **_kwargs: token)
        client.get.return_value = response({"data": [{"id": "fixture-model"}]})
        models = xai._fetch_xai_grok_models(proxy)
    else:
        monkeypatch.setattr(copilot, "get_storage", lambda: storage)
        client.get.side_effect = [
            response({"token": "copilot-fixture"}),
            response({"data": [{"id": "fixture-model", "model_picker_enabled": True}]}),
        ]
        models = copilot._fetch_github_copilot_models(proxy)
    assert models
    assert constructor.call_args.kwargs.get("trust_env") is False
    assert constructor.call_args.kwargs.get("proxy") == proxy
    client.__exit__.assert_called_once()


@pytest.mark.parametrize("proxy", [None, "http://proxy.example:8080"])
def test_xai_owned_oauth_client_does_not_fall_back_to_environment_proxy(monkeypatch, proxy):
    constructor = Mock()
    monkeypatch.setattr(httpx, "Client", constructor)
    xai_oauth._http_client(proxy)
    assert constructor.call_args.kwargs.get("trust_env") is False
    assert constructor.call_args.kwargs.get("proxy") == proxy


@pytest.mark.parametrize("proxy", [None, "http://proxy.example:8080"])
async def test_responses_sse_transport_respects_disabled_and_explicit_proxy(monkeypatch, proxy):
    class StopBeforeRequestError(Exception):
        pass

    constructor = Mock(side_effect=StopBeforeRequestError)
    monkeypatch.setattr(httpx, "AsyncClient", constructor)
    with pytest.raises(StopBeforeRequestError):
        await ResponsesBackend.sse_request(
            "https://fixture.example/responses",
            {},
            {"input": []},
            proxy=proxy,
            error_factory=lambda *_args: RuntimeError("unexpected HTTP error"),
        )
    assert constructor.call_args.kwargs.get("trust_env") is False
    assert constructor.call_args.kwargs.get("proxy") == proxy


@pytest.mark.parametrize("proxy", [None, "http://proxy.example:8080"])
async def test_responses_websocket_respects_disabled_and_explicit_proxy(monkeypatch, proxy):
    from unittest.mock import AsyncMock

    # Stop at the handshake seam; no socket or TLS context is constructed.
    connect = AsyncMock(side_effect=OSError("fixture handshake unavailable"))
    monkeypatch.setattr(websocket, "connect", connect)
    session = websocket.ResponsesWebSocketSession()
    assert (
        await session.request(
            "https://fixture.example/responses",
            {},
            {"input": []},
            provider="fixture",
            verify=None,
            proxy=proxy,
        )
        is None
    )
    assert connect.call_args.kwargs["proxy"] == proxy
