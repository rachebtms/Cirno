"""Package and module ownership are executable contracts."""

import subprocess
import sys
from pathlib import Path

import pytest

from sources.development.check_import_boundaries import ImportCollector, find_violations
import ast


@pytest.mark.parametrize("source", [
    "import cirno_server.webui",
    "from cirno_server import webui",
    "def load():\n    from cirno_server.webui import http",
    "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from cirno_server import webui",
    "import importlib\nimportlib.import_module('cirno_server.webui')",
    "from importlib import import_module as load\nload('cirno_server.webui')",
    "__import__('cirno_server.webui')",
    "import cirno",
])
def test_core_cannot_depend_on_server_or_application(source):
    assert any(item.rule == "package-dependencies" for item in find_violations(source, "cirno_core.agent.context"))


@pytest.mark.parametrize("module", ["cirno_core.session.webui_turns", "cirno_core.agent.loop", "cirno_server.webui.http"])
def test_shared_session_contracts_are_allowed(module):
    assert find_violations("from cirno_core.session.transcript import WebUITranscriptRecorder", module) == []


@pytest.mark.parametrize(("source", "package", "target"), [
    ("from .. import transcript", "cirno_core.session.worker", "cirno_core.transcript"),
    ("from . import transcript", "cirno_core.session.worker", "cirno_core.session.transcript"),
    ("import importlib\nimportlib.import_module('.transcript', 'cirno_core.session')", "cirno_core.session.worker", "cirno_core.session.transcript"),
])
def test_collector_resolves_relative_and_dynamic_imports(source, package, target):
    collector = ImportCollector(ast.parse(source), package)
    collector.visit(ast.parse(source))
    assert collector.edges[0].target == target


@pytest.mark.parametrize(("module", "source", "rule"), [
    ("cirno_core.agent.tools.shell", "from cirno_core.config.schema import Base", "tool-config-base"),
    ("cirno_core.config.schema", "from cirno_core.agent.tools.shell import ExecTool", "configuration-contracts"),
    ("cirno_core.security.network", "from cirno_core.agent.loop import AgentLoop", "security-primitives"),
    ("cirno_core.processes.launch", "from cirno_core.agent.tools.shell import ExecTool", "process-primitives"),
    ("cirno_core.session.manager", "from cirno_core.agent.loop import AgentLoop", "session-storage"),
    ("cirno_server.channels.websocket.runtime", "from cirno_core.session.transcript import WebUITranscriptRecorder", "websocket-transport"),
    ("cirno_core.providers.oauth_catalog_cache", "from cirno_core.providers.openai_codex_provider import OpenAICodexProvider", "oauth-catalog-cache"),
])
def test_internal_ownership_boundaries_remain_enforced(module, source, rule):
    assert any(item.rule == rule for item in find_violations(source, module))


def test_repository_command_checks_all_distributions():
    repository = Path(__file__).resolve().parents[4]
    result = subprocess.run([sys.executable, str(repository / "sources/development/check_import_boundaries.py")], cwd=repository, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "rules" in result.stdout


@pytest.mark.parametrize("package", ["cirno_memory", "cirno_usage", "cirno_vault"])
@pytest.mark.parametrize("source", [
    "from cirno_core.config.paths import get_data_dir",
    "from cirno_server.application import main",
    "import importlib\nimportlib.import_module('cirno_core.config.loader')",
])
def test_independent_libraries_cannot_import_application_policy(package, source):
    assert any(item.rule.startswith("independent-") for item in find_violations(source, package + ".store"))
