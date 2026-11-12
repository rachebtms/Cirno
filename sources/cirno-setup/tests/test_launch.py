"""Command-line ownership and fail-before-start lifecycle checks."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from cirno_setup import cli, launch
from cirno_setup.context import Context
from cirno_setup.policy import Policy


def test_empty_selection_ignores_saved_settings_and_environment_defaults(tmp_path):
    instance = tmp_path / ".cirno"
    instance.mkdir()
    config = instance / "config.json"
    original = '{"tools":{"startup":{"components":["presets.rachebtms"]}}}'
    config.write_text(original)
    result = subprocess.run([sys.executable, "-m", "cirno_setup", "--dry-run"],
        env={**os.environ, "HOME": str(tmp_path), "CIRNO_SETUP": "+presets.rachebtms"}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []
    assert config.read_text() == original
    assert not (instance / "state").exists()


@pytest.mark.parametrize("timeout", [0, 42])
def test_user_setup_precedes_service_and_forwards_only_server_arguments(tmp_path, monkeypatch, timeout):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000)
    events = []
    monkeypatch.setattr(cli, "initialize", lambda context: events.append("environment"))
    monkeypatch.setattr(cli, "ensure", lambda context, selections, **kwargs: events.append((selections, context.policy.timeout_seconds)))
    monkeypatch.setattr(launch, "start_service", lambda context, arguments: events.append(arguments))
    assert cli.main(["--serve", "+pip.pytest", "--timeout", str(timeout), "--", "--port", "9000"]) == 0
    assert events == ["environment", (["+pip.pytest"], timeout), ["--port", "9000"]]
    assert not (tmp_path / ".cirno/config.json").exists()


def test_failed_dependency_does_not_start_the_service(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(cli, "initialize", lambda context: None)
    monkeypatch.setattr(cli, "ensure", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("missing dependency")))
    monkeypatch.setattr(launch, "start_service", lambda *args: pytest.fail("service started after failure"))
    with pytest.raises(RuntimeError, match="missing dependency"):
        cli.main(["--serve", "+pip.pytest"])


def test_final_verification_failure_prevents_service_start(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(cli, "initialize", lambda context: None)

    def verify(*args, **kwargs):
        assert kwargs["verify_after"] is True
        raise RuntimeError("final verification failed")

    monkeypatch.setattr(cli, "ensure", verify)
    monkeypatch.setattr(launch, "start_service", lambda *args: pytest.fail("server started before verification"))
    with pytest.raises(RuntimeError, match="final verification failed"):
        cli.main(["--serve", "+rachebtms", "--verify"])


@pytest.mark.parametrize("timeout", [0, 42])
def test_root_setup_drops_privileges_with_original_installer_arguments(tmp_path, monkeypatch, timeout):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    events = []
    monkeypatch.setattr(launch, "prepare_home", lambda context: events.append("ownership"))
    monkeypatch.setattr(cli, "prepare", lambda *args: events.append("system"))
    monkeypatch.setattr(cli, "ensure", lambda *args, **kwargs: events.append(kwargs["phase"]))
    monkeypatch.setattr(cli, "hand_over_state", lambda context: events.append("state ownership"))
    monkeypatch.setattr(launch, "as_user", lambda context, arguments: events.append(arguments))
    argv = ["--serve", "+pip.pytest", "--timeout", str(timeout), "--", "--config", "/service.json"]
    assert cli.main(argv) == 0
    assert events == ["ownership", "system", "system", "state ownership", argv]


@pytest.mark.parametrize("options", [["--timeout", "-1"], ["--timeout", "1.5"], ["--serve", "--phase", "user"]])
def test_invalid_startup_options_fail_before_changes(tmp_path, monkeypatch, options):
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(SystemExit):
        cli.main(options)
    assert not list(tmp_path.iterdir())


def test_server_check_then_bootstrap_then_exec_preserves_arguments(tmp_path, monkeypatch):
    monkeypatch.setenv("CIRNO_DOCKER_BOOTSTRAP", "1")
    monkeypatch.setenv("CIRNO_SERVICE_PYTHON", "/service/bin/python")
    context = Context(tmp_path, Path(__file__).parent, Policy())
    calls = []
    monkeypatch.setattr(context, "run", lambda command: calls.append(command))
    monkeypatch.setattr(launch.os, "execv", lambda executable, arguments: calls.append(arguments))
    launch.start_service(context, ["--port", "9000"])
    assert calls[0][1] == "-c"
    assert calls[1][1:3] == ["-m", "cirno_server.cli.docker_bootstrap"]
    assert calls[2] == ["/service/bin/python", "-m", "cirno", "--port", "9000", "--config", str(tmp_path / ".cirno/config.json")]


def test_installer_preserves_standard_browser_download_configuration(tmp_path, monkeypatch):
    monkeypatch.setattr("cirno_setup.context.os.geteuid", lambda: 1000)
    monkeypatch.setenv("PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT", "120000")
    monkeypatch.setenv("PLAYWRIGHT_DOWNLOAD_HOST", "https://mirror.example")
    context = Context(tmp_path, tmp_path, Policy())
    values = context.environment()
    assert values["PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT"] == "120000"
    assert values["PLAYWRIGHT_DOWNLOAD_HOST"] == "https://mirror.example"


@pytest.mark.parametrize("selected", [None, "cpu", "cu130"])
def test_setup_selects_matching_pytorch_backend_and_preserves_override(tmp_path, monkeypatch, selected):
    monkeypatch.setattr("cirno_setup.context.os.geteuid", lambda: 1000)
    monkeypatch.delenv("UV_TORCH_BACKEND", raising=False)
    if selected:
        monkeypatch.setenv("UV_TORCH_BACKEND", selected)
    context = Context(tmp_path, tmp_path, Policy())
    assert context.environment()["UV_TORCH_BACKEND"] == (selected or "auto")
