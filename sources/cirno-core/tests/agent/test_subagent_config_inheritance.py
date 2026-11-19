"""Task tools retain instance capability controls without mutating their parent."""

from types import SimpleNamespace
from unittest.mock import Mock

from cirno_core.agent.subagents import tools as task_tools
from cirno_core.agent.tools.cli_apps import CliAppsTool
from cirno_core.agent.tools.loader import ToolLoader
from cirno_core.config.network import NetworkConfig
from cirno_core.config.tools import ToolsConfig


def configured_tools(tmp_path):
    config = ToolsConfig()
    config.cli_apps.enable = False
    config.cli_apps.run_timeout = 73
    config.webui_allow_local_service_access = False
    config.ssrf_whitelist = ["203.0.113.9/32"]
    config.exec.allowed_env_keys = ["FIXTURE_KEY"]
    owner = task_tools.SubagentTools(tmp_path, config, NetworkConfig(), True, set())
    return config, owner


def test_subagent_configuration_keeps_capability_and_network_settings(tmp_path):
    config, owner = configured_tools(tmp_path)
    scoped = owner.configuration()
    assert scoped.cli_apps.enable is False
    assert scoped.cli_apps.run_timeout == 73
    assert scoped.webui_allow_local_service_access is False
    assert scoped.ssrf_whitelist == config.ssrf_whitelist
    assert scoped.restrict_to_workspace is True
    assert config.restrict_to_workspace is False


def test_subagent_configuration_does_not_share_mutable_parent_settings(tmp_path):
    config, owner = configured_tools(tmp_path)
    scoped = owner.configuration()
    original_response_limit = config.web.fetch.max_response_mb
    scoped.exec.allowed_env_keys.append("TASK_LOCAL")
    scoped.web.fetch.max_response_mb = original_response_limit + 1
    assert config.exec.allowed_env_keys == ["FIXTURE_KEY"]
    assert config.web.fetch.max_response_mb == original_response_limit


def test_disabled_cli_apps_are_not_created_in_task_tool_registration(tmp_path, monkeypatch):
    _config, owner = configured_tools(tmp_path)
    loader = ToolLoader(test_classes=[CliAppsTool])
    monkeypatch.setattr(loader, "_discover_plugins", lambda: {})
    monkeypatch.setattr(task_tools, "ToolLoader", lambda: loader)
    create = Mock(side_effect=AssertionError("Disabled CLI capability must not be instantiated"))
    monkeypatch.setattr(CliAppsTool, "create", create)
    registry = owner.build(exec_manager=SimpleNamespace())
    create.assert_not_called()
    assert registry.tool_names == []
