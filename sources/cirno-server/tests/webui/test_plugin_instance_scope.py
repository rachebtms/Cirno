"""Plugin activation and generated runtime paths belong to the requested instance."""

import json

import pytest
from cirno_core.agent.plugins import AGENT_PLUGIN_MCP_SCHEMA, AGENT_PLUGIN_SCHEMA
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.schema import Config
from cirno_server.webui.mcp.actions import mcp_presets_settings_action
from cirno_server.webui.mcp.catalog import mcp_presets_payload
from cirno_server.webui.settings.services import WebUISettingsConfig


@pytest.fixture
def instances(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    plugin = workspace / "plugins" / "fixture"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(json.dumps({"$schema": AGENT_PLUGIN_SCHEMA, "name": "fixture"}))
    (plugin / "mcp.json").write_text(json.dumps({"$schema": AGENT_PLUGIN_MCP_SCHEMA,
        "mcpServers": {"fixture": {"type": "stdio", "command": "fixture-mcp", "args": ["${PLUGIN_DATA}"], "cwd": "${PLUGIN_DATA}"}}}))
    skill = plugin / "skills" / "fixture-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: fixture-skill\ndescription: Fixture skill.\n---\nFixture body.\n")
    config = Config()
    config.agents.defaults.workspace = str(workspace)
    first = tmp_path / "first" / "config.json"
    second = tmp_path / "second" / "config.json"
    save_config(config, first)
    save_config(config, second)
    monkeypatch.setattr("cirno_core.config.loader._current_config_path", first)
    return workspace, first, second


def enabled(path):
    return next(row for row in mcp_presets_payload(config_path=path)["presets"] if row["name"] == "plugin-fixture")["enabled"]


def test_reading_an_explicit_instance_catalog_does_not_create_plugin_data_in_default_instance(instances):
    _, first, second = instances
    assert enabled(second) is False
    assert not (first.parent / "state").exists()
    assert (second.parent / "state" / "plugin-data").exists()


async def test_enabling_and_disabling_an_explicit_instance_does_not_change_default_instance(instances):
    _, first, second = instances
    query = {"name": ["plugin-fixture"]}
    await mcp_presets_settings_action("enable", query, config=WebUISettingsConfig(second))
    assert enabled(second) is True
    assert enabled(first) is False
    await mcp_presets_settings_action("enable", query, config=WebUISettingsConfig(first))
    await mcp_presets_settings_action("disable", query, config=WebUISettingsConfig(second))
    assert enabled(second) is False
    assert enabled(first) is True


async def test_explicit_instance_runtime_uses_its_own_plugin_data_directory(instances, monkeypatch):
    from cirno_core.agent.tools.mcp.provider import _configured_servers
    from cirno_core.config.loader import resolve_config_env_vars

    _, first, second = instances
    await mcp_presets_settings_action("enable", {"name": ["plugin-fixture"]}, config=WebUISettingsConfig(second))
    config = load_config(second)
    config.agents.defaults.system_prompts.shared = "${CIRNO_PLUGIN_SCOPE_NOTE}"
    save_config(config, second)
    monkeypatch.setenv("CIRNO_PLUGIN_SCOPE_NOTE", "Fixture scope")
    resolved = resolve_config_env_vars(load_config(second))
    assert resolved.source_path == second
    assert resolved.agents.defaults.system_prompts.shared == "Fixture scope"
    server = _configured_servers(resolved)["fixture"]
    assert server.cwd.startswith(str(second.parent / "state" / "plugin-data"))
    assert server.args == [server.cwd]
    assert _configured_servers(load_config(first)) == {}


async def test_explicit_instance_skill_cache_and_revocation_are_isolated(instances):
    from cirno_core.agent.plugins import (
        enabled_agent_plugin_skill_dirs,
        enabled_agent_plugin_skills,
    )

    workspace, first, second = instances
    query = {"name": ["plugin-fixture"]}
    await mcp_presets_settings_action("enable", query, config=WebUISettingsConfig(second))
    assert [name for name, _ in enabled_agent_plugin_skills(workspace, config_path=second)] == ["fixture-skill"]
    assert enabled_agent_plugin_skills(workspace, config_path=first) == []
    await mcp_presets_settings_action("enable", query, config=WebUISettingsConfig(first))
    expected = (workspace / "plugins" / "fixture" / "skills" / "fixture-skill",)
    assert enabled_agent_plugin_skill_dirs(workspace, config_path=first) == expected
    assert enabled_agent_plugin_skill_dirs(workspace, config_path=second) == expected
    await mcp_presets_settings_action("disable", query, config=WebUISettingsConfig(second))
    assert enabled_agent_plugin_skill_dirs(workspace, config_path=second) == ()
    assert enabled_agent_plugin_skill_dirs(workspace, config_path=first) == expected


async def test_provider_reload_keeps_the_initial_configuration_owner(instances, monkeypatch):
    from cirno_core.agent.tools.mcp.provider import MCPProvider
    from cirno_core.agent.tools.registry import ToolRegistry
    from cirno_core.config.tools import MCPServerConfig

    _, first, second = instances
    await mcp_presets_settings_action("enable", {"name": ["plugin-fixture"]}, config=WebUISettingsConfig(second))
    provider = MCPProvider.from_config(load_config(second), ToolRegistry())
    config = load_config(second)
    config.tools.mcp_servers["fixture-docs"] = MCPServerConfig(type="streamableHttp", url="https://fixture.test/mcp")
    save_config(config, second)

    async def connect(_servers, _registry, **kwargs):
        return {}

    monkeypatch.setattr("cirno_core.agent.tools.mcp.provider.connect_mcp_servers", connect)
    try:
        result = await provider.reload()
        assert set(result["configured"]) == {"fixture", "fixture-docs"}
        assert provider.configured_server_names == {"fixture", "fixture-docs"}
        assert load_config(first).tools.mcp_servers == {}
    finally:
        await provider.aclose()
