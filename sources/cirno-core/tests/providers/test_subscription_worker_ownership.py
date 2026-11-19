"""Subscription calls retain accepted blocking work until cancellation settles."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_core.providers import openai_codex_provider as codex
from cirno_core.providers import xai_grok_provider as xai
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.errors import ModelStreamProtocolError
from loguru import logger


def fake_provider(monkeypatch, kind, *, catalog=False):
    module = codex if kind == "codex" else xai
    backend = SimpleNamespace(prepare=Mock(side_effect=lambda *_args, **_kwargs: SimpleNamespace(
        body={"instructions": "stable", "input": [], "model": "fixture", "tools": []}, replayed=False,
    )), native_compaction_available=False)
    monkeypatch.setattr(module, "ResponsesBackend", Mock(return_value=backend))
    if kind == "codex":
        provider = module.OpenAICodexProvider(proxy="http://proxy.test:8080")
        provider._ssl_context = Mock(return_value=True)
        monkeypatch.setattr(module, "token_storage", lambda *_args: None)
        request = AsyncMock(return_value=LLMResponse("ready"))
        monkeypatch.setattr(module, "_request_codex", request)
    else:
        provider = module.XAIGrokProvider(proxy="http://proxy.test:8080", extra_body={} if catalog else {"tools": []})
        request = AsyncMock(return_value=("ready", [], "stop", None, None))
        monkeypatch.setattr(module, "_request_xai", request)
    return provider, request


@pytest.mark.parametrize("stage", ["codex-token", "xai-token", "xai-catalog", "xai-refresh"])
@pytest.mark.parametrize("worker_error", [False, True])
async def test_cancel_keeps_blocking_auth_or_catalog_work_owned(monkeypatch, stage, worker_error):
    kind = "codex" if stage.startswith("codex") else "xai"
    provider, request = fake_provider(monkeypatch, kind, catalog=stage == "xai-catalog")
    if stage == "xai-refresh":
        request.side_effect = xai._XAIHTTPError("sign-in rejected", status_code=401)
    entered, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
    token = SimpleNamespace(access="fake-access", account_id="fake-account")
    workers = []
    accepted_calls = []

    async def blocking_worker():
        entered.set()
        await release.wait()
        finished.set()
        if worker_error:
            raise RuntimeError("fake worker failed during cancellation")
        return token

    async def fake_to_thread(function, *args, **kwargs):
        # Real executor work survives cancellation of its awaiting coroutine.
        # Model that ownership without starting threads or opening transports.
        accepted_calls.append((function, args, kwargs))
        is_catalog = function is xai.get_xai_grok_model_catalog
        selected = stage in {"codex-token", "xai-token"} or (
            stage == "xai-catalog" and is_catalog
        ) or (stage == "xai-refresh" and kwargs.get("force_refresh"))
        if not selected:
            return token
        worker = asyncio.create_task(blocking_worker())
        workers.append(worker)
        return await asyncio.shield(worker)

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    task = asyncio.create_task(provider.chat(messages=[{"role": "user", "content": "hello"}]))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        for _ in range(3):
            await asyncio.sleep(0)
        task.cancel()
        for _ in range(3):
            await asyncio.sleep(0)
        assert not task.done(), "provider released its request while accepted worker was still running"
        assert not finished.is_set()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
        assert request.await_count == (1 if stage == "xai-refresh" else 0)
        assert all(entry[2].get("proxy", entry[1][0] if entry[1] else None) == "http://proxy.test:8080" for entry in accepted_calls)
    finally:
        release.set()
        await asyncio.gather(task, *workers, return_exceptions=True)


@pytest.mark.parametrize("stage", ["codex-token", "xai-token", "xai-catalog", "xai-refresh"])
async def test_normal_subscription_request_and_bounded_refresh_still_work(monkeypatch, stage):
    kind = "codex" if stage.startswith("codex") else "xai"
    provider, request = fake_provider(monkeypatch, kind, catalog=stage == "xai-catalog")
    accepted = []
    async def fake_to_thread(function, *args, **kwargs):
        accepted.append((function, args, kwargs))
        if function is xai.get_xai_grok_model_catalog:
            return SimpleNamespace(message=None, find=lambda _model: None)
        return SimpleNamespace(access="refreshed-access" if kwargs.get("force_refresh") else "first-access", account_id="fake-account")
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    if stage == "xai-refresh":
        request.side_effect = [xai._XAIHTTPError("rejected", status_code=401), ("ready", [], "stop", None, None)]
    response = await provider.chat(messages=[{"role": "user", "content": "hello"}])
    assert response.content == "ready"
    assert response.finish_reason == "stop"
    assert request.await_count == (2 if stage == "xai-refresh" else 1)
    assert all(entry.kwargs["proxy"] == "http://proxy.test:8080" for entry in request.await_args_list)
    if stage == "xai-refresh":
        assert request.await_args_list[0].args[1]["Authorization"] == "Bearer first-access"
        assert request.await_args_list[1].args[1]["Authorization"] == "Bearer refreshed-access"
        assert [entry[2].get("force_refresh", False) for entry in accepted] == [False, True]


@pytest.mark.parametrize("kind", ["codex", "xai"])
async def test_protocol_error_keeps_retryable_classification_at_adapter_boundary(monkeypatch, kind):
    provider, request = fake_provider(monkeypatch, kind)
    monkeypatch.setattr(asyncio, "to_thread", AsyncMock(return_value=SimpleNamespace(access="fake-access", account_id="fake-account")))
    error = ModelStreamProtocolError("conflicting tool-call identities")
    request.side_effect = error
    response = await provider.chat(messages=[{"role": "user", "content": "hello"}])
    assert response.finish_reason == "error"
    assert response.error_kind == "invalid_response"
    assert response.error_should_retry is True
    assert request.await_count == 1


async def test_xai_ordinary_failure_log_does_not_copy_upstream_body(monkeypatch):
    provider, request = fake_provider(monkeypatch, "xai")
    monkeypatch.setattr(asyncio, "to_thread", AsyncMock(return_value=SimpleNamespace(access="fake-access")))
    raw = '{"error":{"message":"PrivatePrompt2026", "password":"PrivatePassword2026"}}'
    request.side_effect = xai._build_xai_http_error(503, {}, raw)
    lines = []
    sink = logger.add(lambda message: lines.append(str(message)), format="{message}")
    try:
        response = await provider.chat(messages=[{"role": "user", "content": "hello"}])
    finally:
        logger.remove(sink)
    assert response.error_status_code == 503
    assert response.error_should_retry is True
    assert "PrivatePrompt2026" in response.content
    text = "\n".join(lines)
    assert "PrivatePrompt2026" not in text
    assert "PrivatePassword2026" not in text
    assert "503" in text
