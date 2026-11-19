"""HTTP header masks follow case-insensitive names; JSON/query keys remain exact."""

import json

import pytest
from cirno_core.config.models import ModelPresetConfig
from cirno_core.config.schema import Config
from cirno_server.webui.settings.contracts import WebUISettingsError
from cirno_server.webui.settings.models.mutations import update_model_configuration
from cirno_server.webui.settings.providers.mutations import update_provider_settings
from cirno_server.webui.settings.requests import redact_request_secrets


def configured(domain, field, value):
    config = Config()
    config.providers.openai.api_key = "fixture"
    config.model_presets["primary"] = ModelPresetConfig(provider="openai", model="gpt-4o")
    target = config.providers.openai if domain == "provider" else config.model_presets["primary"]
    setattr(target, field, value)
    return config


def read(config, domain):
    return config.providers.openai if domain == "provider" else config.model_presets["primary"]


def update(config, domain, field, value):
    patch = {field: [json.dumps(value)]}
    if domain == "provider":
        update_provider_settings(config, {"provider": ["openai"], **patch})
    else:
        update_model_configuration(config, {"id": ["primary"], **patch}, oauth_status=lambda _: {})


@pytest.mark.parametrize("domain", ["provider", "preset"])
@pytest.mark.parametrize("before,after", [
    ("Authorization", "authorization"),
    ("authorization", "AUTHORIZATION"),
    ("Authorization", "Authorization"),
])
def test_masked_header_case_edits_retain_the_saved_secret(domain, before, after):
    config = configured(domain, "extra_headers", {before: "Bearer stored-fixture", "X-Route": "research"})
    submitted = redact_request_secrets(read(config, domain).extra_headers)
    submitted[after] = submitted.pop(before)
    update(config, domain, "extra_headers", submitted)
    assert read(config, domain).extra_headers == {after: "Bearer stored-fixture", "X-Route": "research"}


@pytest.mark.parametrize("domain", ["provider", "preset"])
def test_query_secret_masks_do_not_match_differently_cased_keys(domain):
    config = configured(domain, "extra_query", {"API-Key": "stored-fixture"})
    with pytest.raises(WebUISettingsError):
        update(config, domain, "extra_query", {"api-key": "••••••••"})
    assert read(config, domain).extra_query == {"API-Key": "stored-fixture"}


@pytest.mark.parametrize("domain", ["provider", "preset"])
def test_a_different_header_name_cannot_restore_an_unrelated_secret(domain):
    config = configured(domain, "extra_headers", {"Authorization": "Bearer stored-fixture"})
    with pytest.raises(WebUISettingsError):
        update(config, domain, "extra_headers", {"Cookie": "••••••••"})
    assert read(config, domain).extra_headers == {"Authorization": "Bearer stored-fixture"}
