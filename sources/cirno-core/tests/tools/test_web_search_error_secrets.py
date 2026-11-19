"""Search failures must not reveal stored service or endpoint credentials."""

import httpx
import pytest
from cirno_core.agent.tools.registry import is_tool_error_result
from cirno_core.agent.tools.web.search import WebSearchTool
from cirno_core.agent.tools.web_config import WebSearchConfig
from loguru import logger


@pytest.mark.parametrize("provider", ["bocha", "searxng"])
async def test_adapter_error_hides_configured_key_and_endpoint_password(monkeypatch, provider):
    secret = "fixture-search-api-token"
    password = "fixture-password"
    endpoint = f"https://fixture-user:{password}@search.example.test"
    response = httpx.Response(
        401, text=f"Invalid token: {secret}", request=httpx.Request("GET", endpoint + "/search"),
    )

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def get(self, *_args, **_kwargs):
            return response

        post = get

    monkeypatch.setattr("httpx.AsyncClient", Client)
    result = await WebSearchTool(config=WebSearchConfig(
        provider=provider, api_key=secret, base_url=endpoint,
    )).execute("Local fixture")
    assert is_tool_error_result(result)
    assert "401" in result
    assert secret not in result
    assert password not in result


async def test_error_hides_environment_api_key_and_decoded_proxy_password(monkeypatch):
    from unittest.mock import AsyncMock

    from cirno_core.agent.tools.base import ToolResult

    secret = "fixture-env-api-token"
    monkeypatch.setenv("BRAVE_API_KEY", secret)
    monkeypatch.setattr("cirno_core.agent.tools.web.searches.brave.search", AsyncMock(return_value=ToolResult.error(
        f"Error: Service rejected {secret}; proxy password fixture pass",
    )))
    result = await WebSearchTool(
        config=WebSearchConfig(provider="brave"), proxy="http://user:fixture%20pass@proxy.example.test:8080",
    ).execute("Local fixture")
    assert is_tool_error_result(result)
    assert secret not in result
    assert "fixture pass" not in result
    assert "Service rejected" in result


@pytest.mark.parametrize("provider", ["jina", "deepseek"])
async def test_adapter_failure_logs_remove_key_and_proxy_password(monkeypatch, provider):
    from unittest.mock import AsyncMock

    secret = "fixture-log-api-token"
    password = "fixture-log-password"
    logs = []

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def get(self, *_args, **_kwargs):
            raise httpx.ProxyError(f"Fixture endpoint rejected {secret}; proxy password {password}")

        post = get

    monkeypatch.setattr("httpx.AsyncClient", Client)
    monkeypatch.setattr("cirno_core.agent.tools.web.searches.duckduckgo.search", AsyncMock(return_value="Fixture fallback"))
    handler = logger.add(lambda message: logs.append(str(message)), format="{message}", level="WARNING")
    try:
        await WebSearchTool(config=WebSearchConfig(provider=provider, api_key=secret),
                            proxy=f"http://user:{password}@proxy.example.test:8080").execute("Fixture")
    finally:
        logger.remove(handler)
    assert logs
    assert secret not in "\n".join(logs)
    assert password not in "\n".join(logs)
    assert "Fixture endpoint rejected" in "\n".join(logs)


@pytest.mark.parametrize("at_boundary", [False, True])
@pytest.mark.parametrize("provider,limit", [("deepseek", 300), ("bocha", 200)])
@pytest.mark.parametrize("credential", ["api_key", "proxy_password"])
async def test_search_error_redacts_before_truncating(monkeypatch, at_boundary, provider, limit, credential):
    secret = "fixture-sensitive-credential-must-not-leak"
    message = "x" * (limit - 15 if at_boundary else 0) + secret + " invalid"
    response = httpx.Response(400, request=httpx.Request("POST", "https://search.example.test"), **(
        {"json": {"error": {"message": message}}} if provider == "deepseek" else {"text": message}
    ))

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def post(self, *_args, **_kwargs):
            return response

    monkeypatch.setattr("httpx.AsyncClient", Client)
    result = await WebSearchTool(
        config=WebSearchConfig(provider=provider, api_key=secret if credential == "api_key" else "ordinary-key"),
        proxy=f"http://user:{secret}@proxy.example.test:8080" if credential == "proxy_password" else None,
    ).execute("Fixture")
    assert is_tool_error_result(result)
    assert "400" in result
    assert "fixture-sensit" not in result
    assert "[redacted]" in result


async def test_ddgs_redacts_proxy_username_before_diagnostic_truncation(monkeypatch):
    from unittest.mock import AsyncMock

    username = "fixture-sensitive-proxy-account"
    monkeypatch.setattr("cirno_core.agent.tools.web.searches.duckduckgo.asyncio.to_thread", AsyncMock(
        side_effect=RuntimeError("x" * 985 + username + " denied"),
    ))
    result = await WebSearchTool(
        config=WebSearchConfig(provider="duckduckgo"),
        proxy=f"http://{username}:password@proxy.example.test:8080",
    ).execute("Fixture")
    assert is_tool_error_result(result)
    assert "fixture-sensit" not in result
    assert "[redacted]" in result
