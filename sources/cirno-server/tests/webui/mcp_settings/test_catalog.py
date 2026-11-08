"""MCP catalog behavior through the settings operations."""

from __future__ import annotations

import asyncio
import json
from functools import partial
from pathlib import Path

import pytest
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.schema import Config
from cirno_server.webui.mcp.actions import mcp_presets_settings_action
from cirno_server.webui.mcp.catalog import mcp_presets_payload
from cirno_server.webui.mcp.configuration import custom_mcp_action
from cirno_server.webui.mcp.contracts import McpPresetError
from cirno_server.webui.mcp.mentions import normalize_mcp_preset_mentions

from .fixtures import _use_config, _write_agent_plugin


def test_mcp_presets_payload_lists_supported_cards(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_config(tmp_path, monkeypatch)

    payload = mcp_presets_payload()
    names = {preset["name"] for preset in payload["presets"]}

    assert {
        "browserbase",
        "playwright",
        "github",
        "figma",
        "context7",
        "firecrawl",
        "parallel-search",
        "exa",
        "microsoft-learn",
        "aws-docs",
        "brave-search",
        "postman",
        "xmind",
        "notion",
        "linear",
    }.issubset(names)
    browserbase = next(preset for preset in payload["presets"] if preset["name"] == "browserbase")
    assert browserbase["installed"] is False
    assert browserbase["install_supported"] is True
    assert browserbase["required_fields"][0]["configured"] is False
    assert "browserbaseApiKey" not in browserbase["connection_summary"]
    manifest = browserbase["manifest"]
    assert manifest["schema"] == "agent-app.v1"
    assert manifest["id"] == "browserbase"
    assert manifest["source"] == "mcp-preset"
    assert manifest["capabilities"][0]["type"] == "mcp"
    assert manifest["capabilities"][0]["transport"] == "streamableHttp"
    assert manifest["install"]["strategy"] == "config"
    assert manifest["remove"]["verification"] == ["config_absent"]
    assert manifest["trust"]["review_status"] == "builtin_preset"


def test_agent_plugin_reuses_mcp_catalog_and_runtime_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)
    _write_agent_plugin(load_config().workspace_path)

    row = next(
        item for item in mcp_presets_payload()["presets"] if item["source"] == "agent-plugin"
    )
    assert (row["name"], row["display_name"], row["requires"]) == (
        "plugin-desktop",
        "Desktop Control",
        "screen-recording",
    )
    assert row["installed"] and row["configured"] and not row["enabled"]

    async def reload() -> dict[str, object]:
        return {"ok": True, "message": "MCP reloaded.", "requires_restart": False}

    plugin_action = partial(
        mcp_presets_settings_action,
        query={"name": ["plugin-desktop"]},
    )
    enabled = asyncio.run(plugin_action("enable", reload_mcp=reload))
    enabled_row = next(item for item in enabled["presets"] if item["name"] == "plugin-desktop")
    assert (enabled_row["enabled"], enabled_row["status"], enabled["requires_restart"]) == (
        True,
        "enabled",
        False,
    )

    disabled = asyncio.run(plugin_action("disable", reload_mcp=reload))
    disabled_row = next(item for item in disabled["presets"] if item["name"] == "plugin-desktop")
    assert (disabled_row["installed"], disabled_row["enabled"], disabled_row["status"]) == (
        True,
        False,
        "disabled",
    )

    with pytest.raises(McpPresetError, match="enable and disable"):
        asyncio.run(plugin_action("remove"))

    (load_config().workspace_path / "plugins" / "desktop" / "mcp.json").unlink()
    assert any(item["name"] == "plugin-desktop" for item in mcp_presets_payload()["presets"])

    config_path = tmp_path / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["tools"] = {"mcpServers": {"plugin-desktop": {"type": "stdio", "command": "echo"}}}
    config_path.write_text(json.dumps(config), encoding="utf-8")
    rows = [item for item in mcp_presets_payload()["presets"] if item["name"] == "plugin-desktop"]
    assert len(rows) == 1 and rows[0]["source"] == "custom"


@pytest.mark.asyncio
async def test_settings_list_projects_runtime_snapshot_and_reconnects_custom_server(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)
    custom_mcp_action(
        "custom",
        {
            "name": ["team-docs"],
            "transport": ["streamableHttp"],
            "url": ["https://mcp.example.com/mcp"],
        },
    )
    statuses = {"team-docs": "failed"}
    reload_calls = 0

    async def reload_mcp() -> dict[str, object]:
        nonlocal reload_calls
        reload_calls += 1
        statuses["team-docs"] = "connected"
        return {
            "ok": True,
            "connected": ["team-docs"],
            "failed": [],
            "requires_restart": False,
        }

    listed = await mcp_presets_settings_action(
        None,
        {},
        reload_mcp=reload_mcp,
        mcp_runtime_status=lambda: statuses,
    )
    row = next(item for item in listed["presets"] if item["name"] == "team-docs")
    assert row["configured"] is True
    assert row["runtime_status"] == "failed"
    assert reload_calls == 0

    reconnected = await mcp_presets_settings_action(
        "reconnect",
        {"name": ["team-docs"]},
        reload_mcp=reload_mcp,
        mcp_runtime_status=lambda: statuses,
    )
    row = next(item for item in reconnected["presets"] if item["name"] == "team-docs")
    assert row["runtime_status"] == "connected"
    assert reconnected["requires_restart"] is False
    assert reload_calls == 1


def test_normalize_mcp_preset_mentions_keeps_known_presets_only() -> None:
    payload = normalize_mcp_preset_mentions(
        [
            {
                "name": "browserbase",
                "display_name": "Browserbase",
                "transport": "streamableHttp",
                "configured": True,
                "logo_url": "https://example.invalid/logo.svg",
            },
            {"name": "totally-unknown"},
            "bad",
        ]
    )

    assert payload == [
        {
            "name": "browserbase",
            "display_name": "Browserbase",
            "transport": "streamableHttp",
            "configured": True,
            "logo_url": "https://example.invalid/logo.svg",
        }
    ]


def test_normalize_mcp_preset_mentions_accepts_configured_custom_server(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)
    custom_mcp_action(
        "custom",
        {
            "name": ["docs"],
            "transport": ["streamableHttp"],
            "url": ["https://example.com/mcp"],
        },
    )

    payload = normalize_mcp_preset_mentions(
        [
            {"name": "docs", "display_name": "Docs", "transport": "streamableHttp"},
        ]
    )

    assert payload == [{"name": "docs", "display_name": "Docs", "transport": "streamableHttp"}]


def test_normalize_mcp_mentions_uses_explicit_instance_config(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_path = tmp_path / "default.json"
    config_path = tmp_path / "gateway.json"
    save_config(Config(), default_path)
    monkeypatch.setattr("cirno_core.config.loader._current_config_path", default_path)
    custom_mcp_action(
        "custom",
        {
            "name": ["gateway-docs"],
            "transport": ["streamableHttp"],
            "url": ["https://example.com/mcp"],
        },
        config_path=config_path,
    )

    payload = normalize_mcp_preset_mentions(
        [{"name": "gateway-docs", "display_name": "Server docs"}],
        config_path=config_path,
    )

    assert payload == [{"name": "gateway-docs", "display_name": "Server docs"}]
