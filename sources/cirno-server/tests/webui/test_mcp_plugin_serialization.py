"""Plugin activation participates in the same owner lock as connection cleanup."""

import asyncio
import json
import threading

import pytest
from cirno_core.agent.plugins import AGENT_PLUGIN_MCP_SCHEMA, AGENT_PLUGIN_SCHEMA
from cirno_core.config.loader import save_config
from cirno_core.config.schema import Config
from cirno_server.webui.mcp import actions
from cirno_server.webui.mcp.catalog import mcp_presets_payload
from cirno_server.webui.settings.services import WebUISettingsConfig


@pytest.mark.parametrize("same_owner", [True, False])
async def test_plugin_enable_waits_for_an_accepted_orphan_cleanup(
    tmp_path, monkeypatch, same_owner
):
    path = tmp_path / "config.json"
    workspace = tmp_path / "workspace"
    plugin = workspace / "plugins" / "fixture"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(
        json.dumps({"$schema": AGENT_PLUGIN_SCHEMA, "name": "fixture"})
    )
    (plugin / "mcp.json").write_text(
        json.dumps(
            {
                "$schema": AGENT_PLUGIN_MCP_SCHEMA,
                "mcpServers": {"server": {"type": "stdio", "command": "fixture-mcp"}},
            }
        )
    )
    config = Config()
    config.agents.defaults.workspace = str(workspace)
    save_config(config, path)
    cwd = tmp_path / "state" / "mcp" / "fixture"
    cwd.mkdir(parents=True)
    (cwd / "cache.txt").write_text("Old managed data")
    cleanup_owner = WebUISettingsConfig(path)
    plugin_owner = cleanup_owner if same_owner else WebUISettingsConfig(path)
    loop = asyncio.get_running_loop()
    cleanup_entered = asyncio.Event()
    marker_entered = asyncio.Event()
    release = threading.Event()
    cleanup_finished = threading.Event()
    overlaps = []
    original_remove = actions.remove_managed_stdio_cwd
    original_enable = actions.set_agent_plugin_enabled

    def remove(*args, **kwargs):
        loop.call_soon_threadsafe(cleanup_entered.set)
        try:
            if not release.wait(2):
                raise AssertionError("Fixture did not release cleanup")
            return original_remove(*args, **kwargs)
        finally:
            cleanup_finished.set()

    def enable(*args, **kwargs):
        overlaps.append(not cleanup_finished.is_set())
        result = original_enable(*args, **kwargs)
        loop.call_soon_threadsafe(marker_entered.set)
        return result

    monkeypatch.setattr(actions, "remove_managed_stdio_cwd", remove)
    monkeypatch.setattr(actions, "set_agent_plugin_enabled", enable)
    cleanup = asyncio.create_task(
        actions.mcp_presets_settings_action(
            "remove", {"name": ["fixture"], "cleanup_only": ["true"]}, config=cleanup_owner
        )
    )
    activation = None
    try:
        await asyncio.wait_for(cleanup_entered.wait(), 1)
        activation = asyncio.create_task(
            actions.mcp_presets_settings_action(
                "enable", {"name": ["plugin-fixture"]}, config=plugin_owner
            )
        )
        try:
            await asyncio.wait_for(marker_entered.wait(), 0.05)
        except asyncio.TimeoutError:
            pass
        release.set()
        cleanup_receipt, plugin_receipt = await asyncio.gather(cleanup, activation)
        assert overlaps == [False], "Plugin marker bypassed the config lock during cleanup"
        assert cleanup_receipt["last_action"]["ok"] is True
        assert plugin_receipt["requires_restart"] is True
        assert not cwd.exists()
        row = next(
            row
            for row in mcp_presets_payload(config_path=path)["presets"]
            if row["name"] == "plugin-fixture"
        )
        assert row["enabled"] is True
    finally:
        release.set()
        await asyncio.gather(
            cleanup, *([activation] if activation is not None else []), return_exceptions=True
        )
