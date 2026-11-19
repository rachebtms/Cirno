"""An unresolved secret placeholder must not become a saved null value."""

import json
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_core.config.balance import ProviderBalanceConfig
from cirno_core.config.loader import save_config
from cirno_core.config.models import ModelPresetConfig
from cirno_core.config.schema import Config
from cirno_server.webui import model_capabilities
from cirno_server.webui.settings import api
from cirno_server.webui.settings.contracts import WebUISettingsError
from cirno_server.webui.settings.models.mutations import (
    create_model_configuration,
    update_model_configuration,
)
from cirno_server.webui.settings.providers.mutations import (
    create_provider_settings,
    update_provider_settings,
)
from cirno_server.webui.settings.requests import redact_request_secrets, restore_request_secrets
from cirno_server.webui.settings.runtime import update_runtime_config

MASK = "••••••••"


@pytest.mark.parametrize("domain", ["provider", "preset", "new-provider", "new-preset"])
@pytest.mark.parametrize("body", [{"metadata": {"api_key": MASK}}, {"routes": [{"token": MASK}]}])
def test_missing_nested_body_masks_are_rejected_without_config_changes(domain, body):
    config = Config()
    config.providers.openai.api_key = "fixture"
    config.model_presets["primary"] = ModelPresetConfig(provider="openai", model="gpt-4o")
    before = config.model_dump(mode="json")
    query = {"extra_body": [json.dumps(body)]}
    with pytest.raises(WebUISettingsError, match="saved secret"):
        if domain == "provider":
            update_provider_settings(config, {"provider": ["openai"], **query})
        elif domain == "preset":
            update_model_configuration(config, {"id": ["primary"], **query}, oauth_status=lambda _: {})
        elif domain == "new-provider":
            create_provider_settings(config, {"name": ["Research"], "apiBase": ["https://example.test/v1"], **query})
        else:
            create_model_configuration(config, {"name": ["Research"], "provider": ["openai"], "model": ["gpt-4o"], **query}, oauth_status=lambda _: {})
    assert config.model_dump(mode="json") == before


@pytest.mark.parametrize("existing", [False, True])
def test_missing_balance_mask_does_not_replace_api_key_with_null(existing):
    config = Config()
    if existing:
        config.providers.openai.balance = ProviderBalanceConfig(endpoint="https://billing.test/balance")
    before = config.model_dump(mode="json")
    with pytest.raises(WebUISettingsError, match="saved secret"):
        update_provider_settings(config, {"provider": ["openai"], "balance": [json.dumps({
            "endpoint": "https://billing.test/balance", "api_key": MASK,
        })]})
    assert config.model_dump(mode="json") == before


def test_missing_embedding_mask_does_not_turn_into_an_empty_runtime_key():
    config = Config()
    before = config.model_dump(mode="json")
    with pytest.raises(WebUISettingsError, match="saved secret"):
        update_runtime_config(config, {"agents.defaults.memory.embedding_api_key": MASK})
    assert config.model_dump(mode="json") == before


@pytest.mark.parametrize("key_field", ["api_key", "apiKey"])
def test_balance_and_embedding_masks_preserve_saved_keys_and_allow_explicit_clearing(key_field):
    config = Config()
    config.providers.openai.balance = ProviderBalanceConfig(
        endpoint="https://billing.test/balance", api_key="billing-fixture",
    )
    update_provider_settings(config, {"provider": ["openai"], "balance": [json.dumps({
        "endpoint": "https://billing.test/balance", "currency": "credits", key_field: MASK,
    })]})
    assert config.providers.openai.balance.api_key == "billing-fixture"
    assert config.providers.openai.balance.currency == "credits"
    config.agents.defaults.memory.embedding_api_key = "embedding-fixture"
    update_runtime_config(config, {"agents.defaults.memory.embedding_api_key": MASK})
    assert config.agents.defaults.memory.embedding_api_key == "embedding-fixture"
    update_runtime_config(config, {"agents.defaults.memory.embedding_api_key": ""})
    assert config.agents.defaults.memory.embedding_api_key == ""
    update_provider_settings(config, {"provider": ["openai"], "balance": ["null"]})
    assert config.providers.openai.balance is None


@pytest.mark.parametrize("domain", ["provider", "preset"])
def test_existing_nested_body_masks_roundtrip_then_allow_an_explicit_null(domain):
    config = Config()
    config.providers.openai.api_key = "fixture"
    config.model_presets["primary"] = ModelPresetConfig(provider="openai", model="gpt-4o")
    target = config.providers.openai if domain == "provider" else config.model_presets["primary"]
    target.extra_body = {"metadata": {"token": "stored-fixture", "label": "before"}}
    query = {"extra_body": [json.dumps({"metadata": {"token": MASK, "label": "after"}})]}
    def update(values):
        if domain == "provider":
            update_provider_settings(config, {"provider": ["openai"], **values})
            return config.providers.openai
        update_model_configuration(config, {"id": ["primary"], **values}, oauth_status=lambda _: {})
        return config.model_presets["primary"]
    assert update(query).extra_body == {"metadata": {"token": "stored-fixture", "label": "after"}}
    assert update({"extra_body": [json.dumps({"metadata": {"token": None}})]}).extra_body == {"metadata": {"token": None}}


def test_missing_body_mask_failure_preserves_the_actual_settings_file(tmp_path):
    path = tmp_path / "config.json"
    save_config(Config(), path)
    before = path.read_bytes()
    with pytest.raises(WebUISettingsError, match="saved secret"):
        api.update_provider_settings({"provider": ["openai"], "extraBody": [json.dumps({"api_token": MASK})]}, config_path=path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("secret", [False, 0, [], {}, "fixture-secret"])
def test_existing_json_secret_values_roundtrip_and_explicit_null_can_clear_them(secret):
    current = {"metadata": {"token": secret}, "note": MASK}
    submitted = redact_request_secrets(current)
    assert restore_request_secrets(submitted, current) == current
    assert restore_request_secrets({"metadata": {"token": None}}, current) == {"metadata": {"token": None}}


@pytest.mark.parametrize("identity", ["new", "different-model", "different-provider", "missing-field"])
@pytest.mark.parametrize("field", ["extra_body", "extra_headers"])
async def test_probe_does_not_send_unresolved_masks_to_a_provider(tmp_path, monkeypatch, identity, field):
    path = tmp_path / "config.json"
    config = Config()
    config.providers.openai.api_key = "fixture"
    config.providers.anthropic.api_key = "fixture"
    config.model_presets["vision"] = ModelPresetConfig(
        provider="openai", model="gpt-4o", **{field: {"api_token": "stored-fixture"}},
    )
    save_config(config, path)
    factory = Mock(side_effect=AssertionError("unresolved mask reached provider factory"))
    monkeypatch.setattr(model_capabilities, "make_provider", factory)
    preset = {"provider": "anthropic" if identity == "different-provider" else "openai",
              "model": "gpt-4.1" if identity == "different-model" else "gpt-4o",
              field: {"other_token" if identity == "missing-field" else "api_token": MASK}}
    values = {"preset": preset, **({} if identity == "new" else {"preset_id": "vision"})}
    with pytest.raises(WebUISettingsError, match="saved secret"):
        await model_capabilities.probe_model_capabilities(values, config_path=path)
    factory.assert_not_called()


@pytest.mark.parametrize("header", ["authorization", "AUTHORIZATION"])
async def test_probe_restores_saved_headers_after_a_case_only_edit(tmp_path, monkeypatch, header):
    path = tmp_path / "config.json"
    config = Config()
    config.providers.openai.api_key = "fixture"
    config.model_presets["vision"] = ModelPresetConfig(
        provider="openai", model="gpt-4o", extra_headers={"Authorization": "Bearer stored-fixture"},
    )
    save_config(config, path)
    provider = AsyncMock()
    factory = Mock(return_value=provider)
    monkeypatch.setattr(model_capabilities, "make_provider", factory)
    monkeypatch.setattr(model_capabilities, "probe_visual_inputs", AsyncMock(return_value={"image": {"supported": True}}))
    await model_capabilities.probe_model_capabilities({"preset_id": "vision", "preset": {
        "provider": "openai", "model": "gpt-4o", "extra_headers": {header: MASK},
    }}, config_path=path)
    assert factory.call_args.kwargs["preset"].extra_headers == {header: "Bearer stored-fixture"}
    provider.aclose.assert_awaited_once()
