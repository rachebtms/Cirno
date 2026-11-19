"""Capability probes use this instance's endpoint and restore masked model fields."""
import asyncio
from unittest.mock import AsyncMock

import pytest
from cirno_core.config.errors import ConfigLoadError
from cirno_core.config.loader import save_config
from cirno_core.config.models import ModelPresetConfig
from cirno_core.config.schema import Config
from cirno_core.providers.requests import ProviderRequestExecutor
from cirno_server.webui import model_capabilities


async def test_capability_probe_uses_path_scoped_config_and_saved_secrets(tmp_path, monkeypatch):
    path = tmp_path / "separate-config.json"
    config = Config()
    config.providers.openai.api_key = "instance-test-key"
    config.model_presets["vision"] = ModelPresetConfig(model="gpt-4o", provider="openai", extra_headers={"Authorization": "saved-model-secret"})
    config.agents.defaults.fallback_models = ["vision"]
    save_config(config, path)
    provider = AsyncMock()
    captured = {}
    def make_provider(config, *, preset):
        assert config.providers.openai.api_key == "instance-test-key"
        assert config.agents.defaults.fallback_models == []
        captured["preset"] = preset
        return provider
    monkeypatch.setattr(model_capabilities, "make_provider", make_provider)
    probe = AsyncMock(return_value={"image": {"supported": True, "detail": "Visual sample recognized"}})
    monkeypatch.setattr(model_capabilities, "probe_visual_inputs", probe)
    result = await model_capabilities.probe_model_capabilities({"preset_id": "vision", "preset": {"model": "gpt-4o", "provider": "openai", "extra_headers": {"Authorization": "••••••••"}, "video_input": False}}, config_path=path)
    assert captured["preset"].extra_headers["Authorization"] == "saved-model-secret"
    assert result["image"]["supported"] is True
    assert probe.await_args.kwargs["video"] is False
    provider.aclose.assert_awaited_once()


@pytest.mark.parametrize(("model", "api", "video_transport"), [
    ("gpt-5", "chat_completions", True),
    ("gpt-4o", "responses", False),
])
async def test_capability_probe_uses_the_selected_request_api(tmp_path, monkeypatch, model, api, video_transport):
    path = tmp_path / "config.json"
    config = Config()
    config.providers.openai.api_key = "test-key"
    save_config(config, path)
    provider = AsyncMock()
    monkeypatch.setattr(model_capabilities, "make_provider", lambda *_args, **_kwargs: provider)
    probe = AsyncMock(return_value={})
    monkeypatch.setattr(model_capabilities, "probe_visual_inputs", probe)
    await model_capabilities.probe_model_capabilities({"preset": {
        "model": model, "provider": "openai",
        "api": {"supported_apis": [api], "preferred_api": api},
    }}, config_path=path)
    assert probe.await_args.kwargs["video_transport"] is video_transport
    provider.aclose.assert_awaited_once()


async def test_capability_probe_missing_environment_error_names_its_actual_config(tmp_path, monkeypatch):
    path = tmp_path / "other-instance.json"
    config = Config()
    config.providers.openai.api_key = "${CIRNO_TEST_PROBE_MISSING_KEY}"
    save_config(config, path)
    monkeypatch.delenv("CIRNO_TEST_PROBE_MISSING_KEY", raising=False)
    factory = AsyncMock()
    monkeypatch.setattr(model_capabilities, "make_provider", factory)
    with pytest.raises(ConfigLoadError) as error:
        await model_capabilities.probe_model_capabilities({"preset": {
            "model": "gpt-4o", "provider": "openai",
        }}, config_path=path)
    assert error.value.path == path
    factory.assert_not_called()


@pytest.mark.parametrize("cancel_during_probe", [False, True])
async def test_capability_probe_drains_close_after_cancellation(tmp_path, monkeypatch, cancel_during_probe):
    path = tmp_path / "config.json"
    config = Config()
    config.providers.openai.api_key = "test-key"
    save_config(config, path)
    started, release_probe = asyncio.Event(), asyncio.Event()
    closing, release_close, closed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def probe(*_args, **_kwargs):
        started.set()
        await release_probe.wait()
        return {}
    async def close():
        closing.set()
        await release_close.wait()
        closed.set()
    provider = AsyncMock()
    provider.aclose.side_effect = close
    monkeypatch.setattr(model_capabilities, "make_provider", lambda *_args, **_kwargs: provider)
    monkeypatch.setattr(model_capabilities, "probe_visual_inputs", probe)
    operation = asyncio.create_task(model_capabilities.probe_model_capabilities({"preset": {
        "model": "gpt-4o", "provider": "openai",
    }}, config_path=path))
    try:
        await asyncio.wait_for(started.wait(), 1)
        if cancel_during_probe:
            operation.cancel()
        else:
            release_probe.set()
        await asyncio.wait_for(closing.wait(), 1)
        operation.cancel()
        await asyncio.sleep(0)
        finished_before_close = operation.done()
        release_close.set()
        result, = await asyncio.wait_for(asyncio.gather(operation, return_exceptions=True), 1)
        assert not finished_before_close
        assert closed.is_set()
        assert isinstance(result, asyncio.CancelledError)
        provider.aclose.assert_awaited_once()
    finally:
        release_probe.set()
        release_close.set()
        await asyncio.gather(operation, return_exceptions=True)


async def test_capability_probe_repeated_cancellation_settles_requests_before_closing_provider(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    config = Config()
    config.providers.openai.api_key = "test-key"
    save_config(config, path)
    started, request_closing, request_closed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    release_request, closing, release_close, closed = (asyncio.Event() for _ in range(4))
    calls = []
    async def complete(_executor, **_kwargs):
        calls.append("request")
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            request_closing.set()
            await release_request.wait()
            request_closed.set()
    async def close():
        assert request_closed.is_set()
        closing.set()
        await release_close.wait()
        closed.set()
    provider = AsyncMock()
    provider.aclose.side_effect = close
    monkeypatch.setattr(model_capabilities, "make_provider", lambda *_args, **_kwargs: provider)
    monkeypatch.setattr(ProviderRequestExecutor, "complete", complete)
    operation = asyncio.create_task(model_capabilities.probe_model_capabilities({"preset": {
        "model": "gpt-4o", "provider": "openai", "video_input": False,
    }}, config_path=path))
    try:
        await asyncio.wait_for(started.wait(), 1)
        operation.cancel()
        await asyncio.wait_for(request_closing.wait(), 1)
        operation.cancel()
        await asyncio.sleep(0)
        assert not closing.is_set()
        assert not operation.done()
        release_request.set()
        await asyncio.wait_for(closing.wait(), 1)
        operation.cancel()
        await asyncio.sleep(0)
        assert not operation.done()
        release_close.set()
        result, = await asyncio.wait_for(asyncio.gather(operation, return_exceptions=True), 1)
        assert isinstance(result, asyncio.CancelledError)
        assert closed.is_set()
        assert calls == ["request"]
        provider.aclose.assert_awaited_once()
    finally:
        release_request.set()
        release_close.set()
        await asyncio.gather(operation, return_exceptions=True)
