"""MCP oauth behavior through the settings operations."""

from __future__ import annotations

import json

import pytest
from cirno_core.agent.tools.mcp_oauth import MCPOAuthStorage, mcp_oauth_has_credentials
from cirno_core.config.loader import load_config, save_config
from cirno_server.webui.mcp.actions import mcp_presets_action
from cirno_server.webui.mcp.catalog import mcp_presets_payload
from cirno_server.webui.mcp.configuration import custom_mcp_action, ensure_mcp_oauth_server
from cirno_server.webui.mcp.contracts import McpPresetError
from mcp.shared.auth import OAuthToken

from .fixtures import _use_config


@pytest.mark.asyncio
async def test_oauth_preset_is_one_click_configured_after_token_storage(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)

    payload = mcp_presets_action("enable", {"name": ["xmind"]})

    row = next(item for item in payload["presets"] if item["name"] == "xmind")
    assert row["installed"] is True
    assert row["configured"] is False
    assert row["status"] == "authorization_required"
    assert row["transport"] == "streamableHttp"
    assert row["auth"] == "oauth"
    config = load_config()
    cfg = config.tools.mcp_servers["xmind"]
    assert cfg.type == "streamableHttp"
    assert cfg.auth == "oauth"
    assert cfg.url == "https://app.xmind.com/api/mcp"

    await MCPOAuthStorage("xmind", cfg.url).set_tokens(OAuthToken(access_token="secret"))
    connected = mcp_presets_payload()
    row = next(item for item in connected["presets"] if item["name"] == "xmind")
    assert row["configured"] is True
    assert row["status"] == "configured"

    failed = mcp_presets_payload(runtime_status={"xmind": "failed"})
    row = next(item for item in failed["presets"] if item["name"] == "xmind")
    assert row["configured"] is True
    assert row["status"] == "configured"
    assert row["runtime_status"] == "failed"
    assert "secret" not in str(row)

    healthy = mcp_presets_payload(runtime_status={"xmind": "connected"})
    row = next(item for item in healthy["presets"] if item["name"] == "xmind")
    assert row["runtime_status"] == "connected"

    await MCPOAuthStorage("xmind", cfg.url).clear_tokens()
    refresh_failed = mcp_presets_payload(runtime_status={"xmind": "failed"})
    row = next(item for item in refresh_failed["presets"] if item["name"] == "xmind")
    assert row["configured"] is False
    assert row["status"] == "authorization_required"
    assert row["runtime_status"] == "failed"

    stale_connected = mcp_presets_payload(runtime_status={"xmind": "connected"})
    row = next(item for item in stale_connected["presets"] if item["name"] == "xmind")
    assert "runtime_status" not in row

    mcp_presets_action("remove", {"name": ["xmind"]})
    assert await MCPOAuthStorage("xmind", cfg.url).get_tokens() is None


def test_instance_oauth_setup_saves_endpoint_before_authorization(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)
    name, cfg, network = ensure_mcp_oauth_server(
        {"name": ["metabase"], "mcp_url": ["https://analytics.example.com/api/metabase-mcp"]}
    )
    assert name == "metabase"
    assert cfg.auth == "oauth"
    assert network == load_config().network
    assert cfg.url == "https://analytics.example.com/api/metabase-mcp"
    row = next(item for item in mcp_presets_payload()["presets"] if item["name"] == name)
    assert row["installed"] is True
    assert row["status"] == "authorization_required"

    config = load_config()
    config.tools.mcp_servers[name].enabled_tools = ["search"]
    save_config(config)
    _, updated, _network = ensure_mcp_oauth_server(
        {"name": [name], "mcp_url": ["https://other.example.com/api/metabase-mcp"]}
    )
    assert updated.url == "https://other.example.com/api/metabase-mcp"
    assert updated.enabled_tools == ["search"]
    assert load_config().tools.mcp_servers[name].url == updated.url


def test_instance_oauth_setup_requires_endpoint_without_saving_empty_connection(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)
    with pytest.raises(McpPresetError, match="missing MCP server URL"):
        ensure_mcp_oauth_server({"name": ["metabase"]})
    assert load_config().tools.mcp_servers == {}


def test_unknown_oauth_placeholder_is_not_enabled(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_config(tmp_path, monkeypatch)

    with pytest.raises(McpPresetError) as exc:
        mcp_presets_action("enable", {"name": ["asana"]})

    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_replacing_oauth_config_removes_its_stored_credentials(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)
    server_url = "https://mcp.example.com/mcp"
    custom_mcp_action(
        "custom",
        {
            "name": ["company-mcp"],
            "transport": ["streamableHttp"],
            "url": [server_url],
            "auth": ["oauth"],
        },
    )
    await MCPOAuthStorage("company-mcp", server_url).set_tokens(OAuthToken(access_token="secret"))
    assert mcp_oauth_has_credentials("company-mcp", server_url)

    custom_mcp_action(
        "custom",
        {
            "name": ["company-mcp"],
            "transport": ["streamableHttp"],
            "url": [server_url],
        },
    )

    assert not mcp_oauth_has_credentials("company-mcp", server_url)


@pytest.mark.parametrize("installed", [False, True], ids=["first-authorization", "existing-preset"])
def test_oauth_setup_persists_proxy_choice_without_credential_fields(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    installed: bool,
) -> None:
    _use_config(tmp_path, monkeypatch)
    config = load_config()
    config.network.proxy = "http://shared.example:8080"
    save_config(config)
    if installed:
        mcp_presets_action("enable", {"name": ["xmind"]})

    name, cfg, network = ensure_mcp_oauth_server(
        {
            "name": ["xmind"],
            "use_proxy": ["true"],
        }
    )

    assert name == "xmind"
    assert cfg.use_proxy is True
    assert cfg.auth == "oauth"
    assert network.proxy == "http://shared.example:8080"
    assert load_config().tools.mcp_servers[name].use_proxy is True
    payload = mcp_presets_payload()
    row = next(item for item in payload["presets"] if item["name"] == name)
    assert row["use_proxy"] is True
    assert row["status"] == "authorization_required"
    assert payload["proxy_configured"] is True
    assert "shared.example" not in json.dumps(payload)

    _, updated, _ = ensure_mcp_oauth_server({"name": [name], "use_proxy": ["false"]})
    assert updated.use_proxy is False
    assert load_config().tools.mcp_servers[name].use_proxy is False
