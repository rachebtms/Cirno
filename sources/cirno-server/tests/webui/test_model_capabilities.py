"""Capability probes use this instance's endpoint and restore masked model fields."""
from unittest.mock import AsyncMock
from cirno_core.config.loader import save_config
from cirno_core.config.models import ModelPresetConfig
from cirno_core.config.schema import Config
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
