"""Exercise real setup backends with fake package managers and no downloads."""

import json
import subprocess
from pathlib import Path

import pytest
from cirno_setup import apt
from cirno_setup.backends import brew, homebrew
from cirno_setup.context import Context
from cirno_setup.planner import Step
from cirno_setup.policy import Policy
from cirno_setup.recipe import Recipe
from cirno_setup.runner import ensure


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setattr("cirno_setup.context.os.geteuid", lambda: 1000)
    monkeypatch.setenv("CIRNO_SERVICE_PYTHON", str(tmp_path / "service/bin/python"))
    return Context(tmp_path / "home", Path(__file__).parents[1] / "src/cirno_setup/assets", Policy(timeout_seconds=0))


def complete_setup(context, recipe):
    steps = [Step("fixture", recipe)]
    ensure(context, [], steps=steps, verify_after=True)
    assert json.loads((context.root / "setup.json").read_text())["status"] == "ready"
    # Reused installations must also remain verifiable with unlimited time.
    ensure(context, [], steps=steps, verify_after=True)


def test_apt_install_queries_and_final_verification_accept_unlimited(context, monkeypatch):
    monkeypatch.setattr("cirno_setup.runner.os.geteuid", lambda: 0)
    monkeypatch.setattr(apt, "record", lambda *args, **kwargs: None)
    installed = False
    calls = []

    def run(arguments, **kwargs):
        nonlocal installed
        assert kwargs.get("timeout") is None
        calls.append(arguments)
        if arguments[0] == "/usr/bin/dpkg-query":
            output = "hello\thello\t2.0\tinstall ok installed\n" if installed else ""
        elif arguments[0] == "/usr/bin/apt-get":
            if "install" in arguments:
                installed = True
                assert kwargs["env"]["CIRNO_APT_MANAGED"] == "1"
            output = ""
        else:
            pytest.fail(f"Unexpected subprocess: {arguments}")
        return subprocess.CompletedProcess(arguments, 0, stdout=output, stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    complete_setup(context, Recipe("apt", ("hello=2.0",)))
    assert sum(arguments[0] == "/usr/bin/apt-get" for arguments in calls) == 2


@pytest.mark.parametrize("provider,target", [("pip", "tools"), ("pip", "service"), ("extra", "service")])
def test_python_install_and_import_verification_accept_unlimited(context, monkeypatch, provider, target):
    interpreter = context.python if target == "tools" else context.service_python
    installed = False
    installs = []

    def run(arguments, **kwargs):
        nonlocal installed
        assert kwargs["timeout"] is None
        assert kwargs["env"]["PYTHONPATH"] == ""
        if arguments[:3] == ["uv", "pip", "install"]:
            assert arguments[arguments.index("--python") + 1] == str(interpreter)
            installed = True
            installs.append(arguments)
            (interpreter.parent / "demo-cli").parent.mkdir(parents=True, exist_ok=True)
            (interpreter.parent / "demo-cli").touch()
            output = ""
        elif arguments[0] == str(interpreter):
            if arguments[-2:] == ["cirno-memory", "embedding"]:
                output = '["demo-package"]'
            else:
                output = json.dumps([["demo-package", "1.0", [], []]])
                if not installed:
                    return subprocess.CompletedProcess(arguments, 1, stdout="", stderr="Not installed")
        else:
            pytest.fail(f"Unexpected subprocess: {arguments}")
        return subprocess.CompletedProcess(arguments, 0, stdout=output, stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    packages = ("cirno-memory:embedding",) if provider == "extra" else ("demo-package",)
    commands = () if provider == "extra" else ("demo-cli",)
    complete_setup(context, Recipe(provider, packages, imports=("demo_package",), commands=commands, target=target))
    assert len(installs) == 1


def test_npm_install_and_metadata_verification_accept_unlimited(context, monkeypatch):
    calls = []

    def run(arguments, **kwargs):
        assert kwargs["timeout"] is None
        assert arguments[:3] == ["npm", "install", "--global"]
        calls.append(arguments)
        metadata = context.root / "npm/lib/node_modules/demo-npm/package.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text('{"version":"1.0"}')
        (context.root / "npm/bin").mkdir()
        (context.root / "npm/bin/demo-npm").touch()
        return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    complete_setup(context, Recipe("npm", ("demo-npm@1.0",), commands=("demo-npm",)))
    assert len(calls) == 1


def test_homebrew_bootstrap_formula_and_repair_accept_unlimited(context, monkeypatch, tmp_path):
    prefix = tmp_path / "brew"
    monkeypatch.setattr(brew, "PREFIX", prefix)
    monkeypatch.setattr(homebrew, "PREFIX", prefix)
    calls = []

    def run(arguments, **kwargs):
        assert kwargs["timeout"] is None
        calls.append(arguments)
        if arguments[:2] == ["/usr/bin/git", "clone"]:
            command = prefix / "Homebrew/bin/brew"
            command.parent.mkdir(parents=True)
            command.touch()
        elif arguments[:2] in ([str(prefix / "bin/brew"), "install"], [str(prefix / "bin/brew"), "reinstall"]):
            receipt = prefix / "Cellar/tea/1.0/INSTALL_RECEIPT.json"
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text("{}")
            (prefix / "bin/tea").touch()
        else:
            pytest.fail(f"Unexpected subprocess: {arguments}")
        return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    complete_setup(context, Recipe("homebrew"))
    recipe = Recipe("brew", ("tea",), commands=("tea",))
    complete_setup(context, recipe)
    (prefix / "bin/tea").unlink()
    complete_setup(context, recipe)
    assert [arguments[1] for arguments in calls] == ["clone", "install", "reinstall"]
