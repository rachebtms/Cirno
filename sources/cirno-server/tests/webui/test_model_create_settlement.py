"""Creation and call-order publication are separate persisted operations."""

import json

import pytest
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.models import ModelPresetConfig
from cirno_core.config.schema import Config
from cirno_server.webui.settings import api
from cirno_server.webui.settings.contracts import WebUISettingsError
from cirno_server.webui.settings.models.payload import model_settings_payload


@pytest.mark.parametrize("existing", [False, True])
def test_created_preset_survives_rejected_order_and_can_be_enabled_without_recreation(
    tmp_path, monkeypatch, existing,
):
    path = tmp_path / "config.json"
    config = Config()
    config.providers.openai.api_key = "fixture-only"
    if existing:
        config.model_presets["primary"] = ModelPresetConfig(
            display_name="Primary", model="gpt-4o", provider="openai",
        )
        config.agents.defaults.model_preset = "primary"
    save_config(config, path)

    def oauth_status(_spec):
        return {"configured": False, "account": None, "expires_at": None,
                "login_supported": False}

    def project_settings(*, config_path, **_options):
        # Keep the real model projection; omit unrelated system/installation probes.
        return model_settings_payload(load_config(config_path), oauth_status=oauth_status)

    monkeypatch.setattr(api.provider_oauth, "oauth_provider_status", oauth_status)
    monkeypatch.setattr(api, "settings_payload", project_settings)
    created = api.create_model_configuration({
        "name": ["Writer"], "provider": ["openai"], "model": ["gpt-4o-mini"],
        "reasoning_history": ["preserve"],
        "idle_compact_percent": ["40"], "idle_compact_keep_percent": ["10"],
    }, config_path=path)
    identity = created["created_model_preset"]
    assert created["model_call_order"] == (["primary"] if existing else [identity])
    row = next(row for row in created["model_presets"] if row["id"] == identity)
    assert (row["reasoning_history"], row["idle_compact_percent"],
            row["idle_compact_keep_percent"]) == ("preserve", 40, 10)

    committed = path.read_bytes()
    with pytest.raises(WebUISettingsError, match="unknown model preset"):
        api.update_model_call_order({"order": ['["missing"]']}, config_path=path)
    assert path.read_bytes() == committed
    assert identity in load_config(path).model_presets

    order = ["primary", identity] if existing else [identity]
    enabled = api.update_model_call_order({"order": [json.dumps(order)]}, config_path=path)
    assert enabled["model_call_order"] == order
    assert len(load_config(path).model_presets) == (2 if existing else 1)
