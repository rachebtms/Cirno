"""The public command starts the whole service without a terminal setup wizard."""
import json

import pytest
from typer.testing import CliRunner

from cirno_server.cli.commands import app


def test_bare_command_creates_browser_setup_in_selected_instance(tmp_path, monkeypatch):
    launches = []
    monkeypatch.setattr("cirno_server.cli.commands.run_server", lambda config, **options: launches.append((config, options)))
    root = tmp_path / "instance"
    result = CliRunner().invoke(app, ["--home", str(root)])
    assert result.exit_code == 0, result.output
    config, options = launches[0]
    assert config.channels.websocket["enabled"] is True
    assert config.channels.websocket["browserSetup"] is True
    assert config.workspace_path == root / "workspace"
    assert config.runtime_data_dir == root / "state"
    assert (root / "config.json").is_file()
    assert options["unconfigured_provider_error"]


def test_service_overrides_do_not_rewrite_existing_configuration(tmp_path, monkeypatch):
    launches = []
    monkeypatch.setattr("cirno_server.cli.commands.run_server", lambda config, **options: launches.append((config, options)))
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"agents": {"defaults": {"workspace": str(tmp_path / "workspace")}}}))
    before = path.read_bytes()
    result = CliRunner().invoke(app, ["--config", str(path), "--host", "127.0.0.1", "--port", "8873", "--health-port", "18793"])
    assert result.exit_code == 0, result.output
    assert launches[0][0].channels.websocket["port"] == 8873
    assert launches[0][1]["port"] == 18793
    assert path.read_bytes() == before


@pytest.mark.parametrize("command", ["gateway", "webui", "agent", "onboard", "status"])
def test_removed_subcommands_are_not_retained_as_aliases(command):
    result = CliRunner().invoke(app, [command])
    assert result.exit_code == 2


def test_help_and_version_do_not_start_service(monkeypatch):
    monkeypatch.setattr("cirno_server.cli.commands.run_server", lambda *a, **kw: pytest.fail("started"))
    runner = CliRunner()
    assert "Run Cirno and its Web UI" in runner.invoke(app, ["--help"]).output
    assert "0.1.3" in runner.invoke(app, ["--version"]).output
