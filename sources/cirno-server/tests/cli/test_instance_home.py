import sys

import pytest
from typer.testing import CliRunner

from cirno_server.cli.commands import app
from cirno_core.config import home as instance_home
from cirno_core.config import loader
from cirno_core.config.schema import Config
from cirno_core.config.paths import get_media_dir


@pytest.fixture(autouse=True)
def isolate_config(monkeypatch):
    monkeypatch.setattr(loader, "_current_config_path", None)
    monkeypatch.setattr(instance_home, "_instance_path", None)




def test_home_explicit_config_and_workspace_take_precedence(tmp_path, monkeypatch):
    launches = []
    monkeypatch.setattr("cirno_server.cli.commands.run_server", lambda config, **options: launches.append(config))
    home = tmp_path / "home"
    config = tmp_path / "other" / "config.json"
    workspace = tmp_path / "project"
    result = CliRunner().invoke(app, [
        "--home", str(home), "--config", str(config),
        "--workspace", str(workspace),
    ])
    assert result.exit_code == 0, result.output
    assert not (home / "config.json").exists()
    loaded = loader.load_config(config)
    assert launches[0].workspace_path == workspace
    assert loaded.runtime_data_dir == config.parent / "state"


def test_home_paths_and_saved_workspace(tmp_path):
    instance_home.set_instance_path(tmp_path)
    assert loader.get_config_path() == tmp_path / "config.json"
    assert Config().workspace_path == tmp_path / "workspace"
    assert get_media_dir() == tmp_path / "state" / "media"
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "custom")
    loader.save_config(config)
    assert loader.load_config().workspace_path == tmp_path / "custom"




def test_home_rejects_file(tmp_path):
    target = tmp_path / "file"
    target.touch()
    result = CliRunner().invoke(app, ["--home", str(target), "onboard"])
    assert result.exit_code == 2


def test_home_bare_command_opens_webui_and_restores_selection(monkeypatch, tmp_path):

    selected = tmp_path / "selected"
    observed = []

    def run_webui(*args, **kwargs):
        observed.append((loader.get_config_path(), Config().workspace_path))

    monkeypatch.setattr("cirno_server.cli.commands.run_server", run_webui)
    result = CliRunner().invoke(app, ["--home", str(selected)])
    assert result.exit_code == 0, result.output
    assert observed == [(selected / "config.json", selected / "workspace")]
    assert instance_home.get_selected_instance_path() is None


def test_gateway_child_receives_home_after_cli_selection_ends(tmp_path):
    from cirno_server.lifecycle import ServerInstance, build_server_command

    home = tmp_path / "instance with spaces"
    instance_home.set_instance_path(home)
    instance = ServerInstance.resolve(config_path=home / "config.json")
    instance_home.set_instance_path(None)
    options = instance.start_options(port=18791)
    command = build_server_command(sys.executable, options)
    assert command[:5] == [sys.executable, "-m", "cirno", "--home", str(home)]
    assert command[5] == "--health-port"
    assert options.config_path == str(home / "config.json")


def test_fresh_instance_separates_agent_home_runtime_state_and_workspace(tmp_path, monkeypatch):
    from cirno_core.config.paths import get_data_dir
    from cirno_core.config.home import get_home_path
    from cirno_core.notifications.inbox import NotificationInbox
    from cirno_server.channels.telegram.binding import TelegramBinding
    from cirno_core.storage.instance import InstanceData
    from cirno_core.agent.context import ContextBuilder
    from cirno_core.utils.helpers import sync_workspace_templates
    from cirno_core.session.manager import SessionManager

    root = tmp_path / "instance"
    instance_home.set_instance_path(root)
    loader.save_config(Config())
    workspace = Config().workspace_path
    workspace.mkdir(parents=True)
    sync_workspace_templates(workspace, silent=True)
    assert get_home_path() == root / "home"
    assert get_data_dir() == root / "state"
    assert (root / "config.json").is_file()
    assert (root / "home" / "SOUL.md").is_file()
    assert (root / "home" / "memory" / "MEMORY.md").is_file()
    assert (root / "home" / "skills").is_dir()
    assert ContextBuilder(workspace).memory.workspace == root / "home"
    assert InstanceData().path == root / "state" / "instance.sqlite3"
    assert TelegramBinding().path == root / "state" / "telegram.sqlite3"
    assert NotificationInbox().path == root / "state" / "notifications" / "inbox.sqlite3"
    from cirno_core.config.paths import get_runtime_subdir
    monkeypatch.setattr("cirno_core.session.location.get_runtime_subdir", get_runtime_subdir)
    manager = SessionManager(workspace)
    assert manager.sessions_dir.is_relative_to(root / "state" / "sessions")
    for directory in [root / "home", workspace]:
        assert not (directory / "config.json").exists()
        assert not list(directory.glob("*.sqlite3"))
