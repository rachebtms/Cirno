"""Preset credential edits preserve HTTP header identity across letter cases."""

import json

import pytest
from cirno_core.config.loader import load_config, save_config
from cirno_server.webui.mcp.actions import mcp_presets_action
from cirno_server.webui.mcp.catalog import mcp_presets_payload
from cirno_server.webui.mcp.presets import MCP_PRESETS

from .fixtures import _use_config


@pytest.mark.parametrize("name", ["deepnote", "agentmail"])
@pytest.mark.parametrize("letter_case", ["lower", "upper"])
def test_header_credentials_stay_configured_and_survive_reenable(tmp_path, monkeypatch, name, letter_case):
    _use_config(tmp_path, monkeypatch)
    preset = next(preset for preset in MCP_PRESETS if preset.name == name)
    field = preset.fields[0]
    header = getattr(field.target[1], letter_case)()
    cfg = preset.server.model_copy(deep=True)
    cfg.headers = {header: field.value_prefix + "retained-secret"}
    config = load_config()
    config.tools.mcp_servers[name] = cfg
    save_config(config)

    payload = mcp_presets_payload()
    row = next(row for row in payload["presets"] if row["name"] == name)
    assert row["configured"] is True
    assert row["required_fields"][0]["configured"] is True
    assert "retained-secret" not in json.dumps(payload)
    payload = mcp_presets_action("enable", {"name": [name]})
    saved = load_config().tools.mcp_servers[name]
    assert saved.headers == {field.target[1]: field.value_prefix + "retained-secret"}
    assert "retained-secret" not in json.dumps(payload)


@pytest.mark.parametrize("name", ["deepnote", "agentmail"])
@pytest.mark.parametrize("letter_case", ["lower", "upper"])
def test_replacing_header_credential_removes_all_case_variants(tmp_path, monkeypatch, name, letter_case):
    _use_config(tmp_path, monkeypatch)
    preset = next(preset for preset in MCP_PRESETS if preset.name == name)
    field = preset.fields[0]
    canonical = field.target[1]
    variant = getattr(canonical, letter_case)()
    cfg = preset.server.model_copy(deep=True)
    cfg.headers = {canonical: field.value_prefix + "old-secret", variant: field.value_prefix + "other-secret", "X-Trace": "keep"}
    config = load_config()
    config.tools.mcp_servers[name] = cfg
    save_config(config)

    payload = mcp_presets_action("enable", {"name": [name], field.name: ["new-secret"]})
    saved = load_config().tools.mcp_servers[name]
    assert saved.headers == {canonical: field.value_prefix + "new-secret", "X-Trace": "keep"}
    for secret in ("old-secret", "other-secret", "new-secret"):
        assert secret not in json.dumps(payload)


@pytest.mark.parametrize("saved_header", ["bearer retained-secret", "BEARER retained-secret", "Basic retained-secret", "${FIXTURE_AUTH_HEADER}"])
def test_reenable_preserves_a_complete_saved_authorization_header(tmp_path, monkeypatch, saved_header):
    _use_config(tmp_path, monkeypatch)
    monkeypatch.setenv("FIXTURE_AUTH_HEADER", "Bearer retained-secret")
    preset = next(preset for preset in MCP_PRESETS if preset.name == "deepnote")
    cfg = preset.server.model_copy(deep=True)
    cfg.headers = {"authorization": saved_header}
    config = load_config()
    config.tools.mcp_servers[preset.name] = cfg
    save_config(config)

    payload = mcp_presets_action("enable", {"name": [preset.name]})
    saved = load_config().tools.mcp_servers[preset.name]
    assert saved.headers == {"Authorization": saved_header}
    assert "retained-secret" not in json.dumps(payload)
