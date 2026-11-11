"""The standalone CLI can plan without a server or filesystem mutations."""

import json
import os
import subprocess
import sys

from cirno_setup.cli import main


def test_cli_dry_run_resolves_aliases_without_initializing_an_instance(tmp_path):
    result = subprocess.run([sys.executable, "-m", "cirno_setup", "+npm.summarize", "+pip.pytest", "--dry-run"],
        env={**os.environ, "HOME": str(tmp_path), "CIRNO_SETUP": ""}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    steps = json.loads(result.stdout)
    assert [item["id"] for item in steps] == ["system.node_runtime", "tools.node", "npm.summarize", "pip.pytest"]
    assert list(tmp_path.iterdir()) == []


def test_apt_hook_does_not_read_or_execute_user_configuration(tmp_path, monkeypatch):
    from cirno_setup import apt
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".cirno").mkdir()
    (tmp_path / ".cirno/config.json").write_text("not valid JSON")
    recorded = []
    monkeypatch.setattr(apt, "record", lambda context: recorded.append(context.home))
    assert main(["--record-apt"]) == 0
    assert recorded == [tmp_path]


def test_channel_dependency_contract_does_not_import_installers():
    code = "import sys; from cirno_setup.contracts.telegram import REQUIREMENTS; assert REQUIREMENTS; assert 'cirno_setup.backends' not in sys.modules; assert 'cirno_setup.runner' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_initializer_does_not_delete_the_interpreter_running_setup(tmp_path, monkeypatch):
    from pathlib import Path

    from cirno_setup.context import Context
    from cirno_setup.initialize import initialize
    from cirno_setup.policy import Policy

    context = Context(tmp_path, tmp_path, Policy())
    context.python.parent.mkdir(parents=True)
    context.python.write_text("interpreter fixture")
    (context.python.parent.parent / "pyvenv.cfg").touch()
    monkeypatch.setenv("CIRNO_SERVICE_PYTHON", str(context.python))

    def run(arguments, **kwargs):
        assert Path(arguments[0]).is_file(), "setup deleted its active interpreter"

    monkeypatch.setattr("cirno_setup.initialize.subprocess.run", run)
    monkeypatch.setattr(context, "inspect", lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "", ""))
    initialize(context)
    assert context.python.read_text() == "interpreter fixture"



def test_standalone_uv_install_preserves_user_packages(tmp_path):
    import zipfile
    from pathlib import Path

    from cirno_setup.backends import pip
    from cirno_setup.context import Context
    from cirno_setup.initialize import initialize
    from cirno_setup.policy import Policy
    from cirno_setup.recipe import Recipe

    context = Context(tmp_path / "home", Path(__file__).parents[1] / "src/cirno_setup/assets", Policy())
    initialize(context)
    wheel = tmp_path / "cirno_setup_probe-0.0.1-py3-none-any.whl"
    metadata = "cirno_setup_probe-0.0.1.dist-info"
    files = {
        "cirno_setup_probe.py": "value = 42\ndef main():\n    print(value)\n",
        f"{metadata}/METADATA": "Metadata-Version: 2.1\nName: cirno-setup-probe\nVersion: 0.0.1\n",
        f"{metadata}/entry_points.txt": "[console_scripts]\ncirno-setup-probe = cirno_setup_probe:main\n",
        f"{metadata}/WHEEL": "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    files[f"{metadata}/RECORD"] = "".join(f"{name},,\n" for name in files)
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, contents in files.items():
            archive.writestr(name, contents)
    recipe = Recipe(provider="pip", packages=(f"cirno-setup-probe @ {wheel.as_uri()}",), imports=("cirno_setup_probe",), commands=("cirno-setup-probe",))
    pip.install(context, recipe)
    assert pip.verify(context, recipe).ready
    initialize(context)
    assert pip.verify(context, recipe).ready
    assert "uv = " in (context.python.parent.parent / "pyvenv.cfg").read_text()
    assert context.inspect([str(context.python), "-c", "import pip"]).returncode == 0
    result = context.inspect([str(context.python), "-c", "import cirno_setup_probe; assert cirno_setup_probe.value == 42"])
    assert result.returncode == 0, result.stderr

    script = context.python.parent / "cirno-setup-probe"
    assert context.inspect([str(script)]).stdout.strip() == "42"
    from cirno_setup.python import package_command
    context.run(package_command("uninstall", context.python, ["cirno-setup-probe"]))
    assert not script.exists()
    assert not pip.verify(context, recipe).ready
