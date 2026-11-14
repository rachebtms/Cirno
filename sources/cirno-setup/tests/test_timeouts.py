"""Unlimited setup covers installation, readiness checks and final verification."""

import subprocess
import sys
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cirno_setup import backends, cli
from cirno_setup.backends import browser
from cirno_setup.context import Context
from cirno_setup.policy import Policy
from cirno_setup.recipe import Recipe, Verification


@pytest.mark.parametrize(("seconds", "install", "check"), [(0, None, None), (42, 42, 42), (1800, 1800, 60)])
def test_install_and_readiness_checks_use_the_selected_timeout(tmp_path, monkeypatch, seconds, install, check):
    context = Context(tmp_path, tmp_path, Policy(timeout_seconds=seconds))
    calls = []

    def run(arguments, **kwargs):
        calls.append(kwargs["timeout"])
        return subprocess.CompletedProcess(arguments, 0, stdout="ready", stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    context.run(["fixture-install"])
    assert context.probe(["fixture-check"])
    assert calls == [install, check]


def test_zero_timeout_runs_real_local_commands_without_an_immediate_timeout(tmp_path):
    context = Context(tmp_path, tmp_path, Policy(timeout_seconds=0))
    command = [sys.executable, "-c", "import time; time.sleep(0.02); print('ready')"]
    assert context.run(command, capture=True).stdout.strip() == "ready"
    assert context.probe(command)


def test_zero_timeout_still_reports_command_failures(tmp_path):
    context = Context(tmp_path, tmp_path, Policy(timeout_seconds=0))
    command = [sys.executable, "-c", "raise SystemExit(7)"]
    with pytest.raises(subprocess.CalledProcessError) as error:
        context.run(command)
    assert error.value.returncode == 7
    assert not context.probe(command)


@pytest.mark.parametrize("seconds", [0, 42])
def test_environment_cleanup_and_home_ownership_use_setup_timeout(tmp_path, monkeypatch, seconds):
    from cirno_setup.initialize import initialize
    from cirno_setup.launch import prepare_home

    context = Context(tmp_path, tmp_path, Policy(timeout_seconds=seconds))
    context.python.parent.mkdir(parents=True)
    (context.python.parent.parent / "pyvenv.cfg").touch()
    monkeypatch.setenv("CIRNO_SERVICE_PYTHON", str(context.python))
    calls = []

    def run(arguments, **kwargs):
        calls.append((arguments, kwargs["timeout"]))
        return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    initialize(context)
    prepare_home(context)
    assert len(calls) == 3  # legacy-path cleanup, pip readiness, ownership
    assert all(timeout == (seconds or None) for _, timeout in calls)
    assert "cirno-bundled-tools.pth" in calls[0][0][2]
    assert calls[-1][0][:3] == ["/usr/bin/chown", "-R", "cirno:cirno"]


@pytest.mark.parametrize(("seconds", "launch_timeout"), [(0, 0), (1800, 30000)])
def test_browser_readiness_does_not_reintroduce_a_timeout_when_unlimited(tmp_path, monkeypatch, seconds, launch_timeout):
    context = Context(tmp_path, tmp_path, Policy(timeout_seconds=seconds))
    executable = tmp_path / "fixture-browser"
    executable.touch()
    link = context.root / "bin/chromium"
    link.parent.mkdir(parents=True)
    link.symlink_to(executable)
    launch = Mock(return_value=SimpleNamespace(close=lambda: None))
    playwright = SimpleNamespace(chromium=SimpleNamespace(launch=launch, executable_path=str(executable)), stop=lambda: None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(
        sync_playwright=lambda: SimpleNamespace(start=lambda: playwright),
    ))

    def inspect(arguments):
        output = StringIO()
        with redirect_stdout(output):
            exec(arguments[2], {})
        return subprocess.CompletedProcess(arguments, 0, stdout=output.getvalue(), stderr="")

    monkeypatch.setattr(context, "inspect", inspect)
    assert browser.verify(context, Recipe()).ready
    launch.assert_called_once_with(headless=True, timeout=launch_timeout)


def test_cli_zero_timeout_reaches_install_and_both_verification_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(cli, "initialize", lambda context: None)
    installed = False
    calls = []

    def run(arguments, **kwargs):
        nonlocal installed
        assert kwargs["timeout"] is None
        calls.append(arguments[0])
        if arguments[0] == "fixture-install":
            installed = True
        return subprocess.CompletedProcess(arguments, 0 if installed else 1, stdout="", stderr="")

    backend = SimpleNamespace(
        install=lambda context, recipe: context.run(["fixture-install"]),
        verify=lambda context, recipe: Verification(context.probe(["fixture-check"])),
    )
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(backends, "backend", lambda name: backend)
    assert cli.main(["+pip.pytest", "--timeout", "0", "--verify"]) == 0
    assert calls == ["fixture-check", "fixture-install", "fixture-check", "fixture-check"]
