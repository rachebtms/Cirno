"""Regression coverage for the executable Python import boundaries."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from sources.development.check_import_boundaries import Violation, find_violations


@pytest.mark.parametrize(
    ("source", "target", "line"),
    [
        ("import cirno.webui.metadata", "cirno.webui.metadata", 1),
        ("from cirno import webui", "cirno.webui", 1),
        ("from cirno.webui import metadata", "cirno.webui.metadata", 1),
        ("from .. import webui", "cirno.webui", 1),
        ("from ..webui import metadata", "cirno.webui.metadata", 1),
        (
            "def load():\n    from cirno.cli import gateway",
            "cirno.cli.gateway", 2,
        ),
        (
            "import importlib\nimportlib.import_module('cirno.webui.metadata')",
            "cirno.webui.metadata", 2,
        ),
        (
            "import importlib as modules\n"
            "modules.import_module(name='cirno.webui.metadata')",
            "cirno.webui.metadata", 2,
        ),
        (
            "from importlib import import_module as load\n"
            "load('..webui.metadata', __package__)",
            "cirno.webui.metadata", 2,
        ),
        (
            "from importlib import import_module\n"
            "import_module('..webui.metadata', package='cirno.agent')",
            "cirno.webui.metadata", 2,
        ),
        ("__import__('cirno.webui.metadata')", "cirno.webui.metadata", 1),
        (
            "import builtins as imports\nimports.__import__('cirno.webui.metadata')",
            "cirno.webui.metadata", 2,
        ),
    ],
)
def test_core_rejects_adapter_imports_in_supported_spellings(
    source: str, target: str, line: int,
) -> None:
    assert find_violations(source, "cirno.agent.loop") == [
        Violation("core-execution", target, line),
    ]


@pytest.mark.parametrize(
    "source",
    [
        "from typing import TYPE_CHECKING as TC\n"
        "if TC:\n    from cirno.webui import metadata",
        "import typing as t\n"
        "if t.TYPE_CHECKING:\n    from cirno.webui import metadata",
    ],
)
def test_core_boundary_includes_type_dependencies(source: str) -> None:
    assert find_violations(source, "cirno.agent.runner") == [
        Violation("core-execution", "cirno.webui.metadata", 3),
    ]


@pytest.mark.parametrize(
    ("module", "rule"),
    [
        ("cirno.session.manager", "session-storage"),
        ("cirno.session.recovery", "session-storage"),
        ("cirno.security.workspace_policy", "security-primitives"),
        ("cirno.agent.turn_delivery", "core-execution"),
        ("cirno.channels.notification_routes", "channel-routing-contracts"),
        ("cirno.config.schema", "configuration-contracts"),
        ("cirno.agent.tools.cli_apps_config", "tool-configuration-contracts"),
        ("cirno.utils.file_io", "shared-primitives"),
    ],
)
def test_storage_and_security_do_not_depend_on_adapters(module: str, rule: str) -> None:
    assert find_violations("from cirno.cli import gateway", module) == [
        Violation(rule, "cirno.cli.gateway", 1),
    ]


@pytest.mark.parametrize(
    "dependency",
    [
        "cirno.bus.outbound_events.ProgressEvent",
        "cirno.command.router",
        "cirno.pairing.events.PairingChanged",
        "cirno.session.webui_turns.clear_websocket_turn_if_current",
        "cirno.webui.transcript.WebUITranscriptRecorder",
        "cirno.webui.outbound_wire.project_notification",
    ],
)
def test_websocket_transport_leaves_event_and_history_policy_to_delivery(dependency: str) -> None:
    module, name = dependency.rsplit(".", 1)
    source = f"from {module} import {name}\n"
    assert find_violations(source, "cirno.channels.websocket.runtime") == [
        Violation("websocket-transport", dependency, 1),
    ]
    assert find_violations(source, "cirno.webui.outbound_delivery") == []


@pytest.mark.parametrize(
    "source",
    [
        "from cirno.config.schema import Base",
        "from ...config.schema import Base as ConfigBase",
    ],
)
def test_tool_configs_import_the_shared_base_directly(source: str) -> None:
    assert find_violations(source, "cirno.agent.tools.shell") == [
        Violation("tool-config-base", "cirno.config.schema.Base", 1),
    ]
    assert find_violations(
        "from cirno.config.base import Base", "cirno.agent.tools.shell",
    ) == []


def test_configuration_imports_the_tool_owned_config_contracts() -> None:
    source = (
        "from cirno.agent.tools.cli_apps_config import CliAppsToolConfig\n"
        "from cirno.agent.tools.filesystem_config import FileToolsConfig\n"
        "from cirno.agent.tools.self_config import MyToolConfig\n"
        "from cirno.agent.tools.shell_config import ExecToolConfig\n"
        "from cirno.agent.tools.web_config import WebToolsConfig\n"
    )
    assert find_violations(source, "cirno.config.schema") == []


@pytest.mark.parametrize(
    ("module", "source"),
    [
        ("cirno.agent.loop", "from cirno.session.recovery import RecoveryAdmission"),
        ("cirno.session.manager", "from cirno.providers.base import ProviderConversationState"),
        ("cirno.session.webui_turns", "from cirno.webui import transcript"),
        ("cirno.cli.gateway_runtime", "from cirno.agent.loop import AgentLoop"),
        ("cirno.channels.websocket.runtime", "from cirno.webui import inbound_commands"),
        ("cirno.agent.tools.cli_apps_config", "from cirno.config.base import Base"),
        (
            "cirno.agent.turn_delivery",
            "from cirno.channels.notification_routes import notification_metadata",
        ),
    ],
)
def test_existing_runtime_and_composition_dependencies_remain_allowed(
    module: str, source: str,
) -> None:
    assert find_violations(source, module) == []


@pytest.mark.parametrize(
    ("relative", "source", "rule", "target", "line"),
    [
        (
            "cirno/agent/runner.py", "import cirno.webui.metadata",
            "core-execution", "cirno.webui.metadata", 1,
        ),
        (
            "cirno/agent/loop.py",
            "import importlib\nif importlib.import_module('cirno.webui.metadata'):\n    pass",
            "core-execution", "cirno.webui.metadata", 2,
        ),
        (
            "cirno/agent/loop.py", "if __import__('cirno.webui.metadata'):\n    pass",
            "core-execution", "cirno.webui.metadata", 1,
        ),
        (
            "cirno/session/manager.py", "from cirno.cli import gateway",
            "session-storage", "cirno.cli.gateway", 1,
        ),
        (
            "cirno/channels/notification_routes.py",
            "from cirno.channels.slack.runtime import SlackChannel",
            "channel-routing-contracts", "cirno.channels.slack.runtime.SlackChannel", 1,
        ),
        (
            "cirno/channels/notification_routes.py",
            "from cirno.agent.turn_delivery import TurnRoute",
            "channel-routing-contracts", "cirno.agent.turn_delivery.TurnRoute", 1,
        ),
        (
            "cirno/security/__init__.py", "from ..cli import gateway",
            "security-primitives", "cirno.cli.gateway", 1,
        ),
        (
            "cirno/channels/websocket/runtime.py",
            "import importlib as modules\nmodules.import_module('cirno.command.router')",
            "websocket-transport", "cirno.command.router", 2,
        ),
        (
            "cirno/agent/tools/shell.py", "from ...config.schema import Base as ConfigBase",
            "tool-config-base", "cirno.config.schema.Base", 1,
        ),
        (
            "cirno/channels/telegram/runtime.py", "from cirno.config.schema import Base",
            "tool-config-base", "cirno.config.schema.Base", 1,
        ),
        (
            "cirno/config/schema.py", "from cirno.agent.tools.shell import ExecTool",
            "configuration-contracts", "cirno.agent.tools.shell.ExecTool", 1,
        ),
        (
            "cirno/agent/tools/cli_apps_config.py", "from .cli_apps import CliAppsTool",
            "tool-configuration-contracts", "cirno.agent.tools.cli_apps.CliAppsTool", 1,
        ),
        (
            "cirno/agent/tools/web_config.py", "from cirno.config.schema import Config",
            "tool-configuration-contracts", "cirno.config.schema.Config", 1,
        ),
        (
            "cirno/providers/oauth_catalog_cache.py",
            "from cirno.providers import openai_codex_provider",
            "oauth-catalog-cache", "cirno.providers.openai_codex_provider", 1,
        ),
    ],
)
def test_cli_rejects_a_violation_and_reports_its_source_location(
    tmp_path: Path, relative: str, source: str, rule: str, target: str, line: int,
) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(source + "\n", encoding="utf-8")
    (tmp_path / "cirno" / "__init__.py").write_text("")

    (tmp_path / "cirno" / "__init__.py").write_text("")
    result = subprocess.run(
        [sys.executable, "-m", "sources.development.check_import_boundaries", "--root", str(tmp_path / "cirno")],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stderr.strip() == f"{relative.removeprefix('cirno/')}:{line}: [{rule}] must not import {target}"


def test_cli_accepts_a_tool_owned_config_import(tmp_path: Path) -> None:
    path = tmp_path / "cirno/config/schema.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "from cirno.agent.tools.cli_apps_config import CliAppsToolConfig\n",
        encoding="utf-8",
    )

    (tmp_path / "cirno" / "__init__.py").write_text("")
    result = subprocess.run(
        [sys.executable, "-m", "sources.development.check_import_boundaries", "--root", str(tmp_path / "cirno")],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
