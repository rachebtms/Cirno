"""Offline uv installation checks for independent integration prefixes."""

import json
import subprocess
from pathlib import Path
from zipfile import ZipFile

from cirno_setup.python import package_command


def _run(*command):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=30).stdout


def _wheel(directory: Path, version: str) -> Path:
    dist = f"seed_probe-{version}.dist-info"
    files = {
        "seed_probe/__init__.py": (
            "def main():\n"
            "    import importlib.metadata as metadata, json, sys\n"
            "    print(json.dumps([sys.prefix, sys.executable, metadata.version('seed-probe')]))\n"
        ),
        f"{dist}/METADATA": f"Metadata-Version: 2.1\nName: seed-probe\nVersion: {version}\n",
        f"{dist}/WHEEL": "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        f"{dist}/entry_points.txt": "[console_scripts]\nseed-probe = seed_probe:main\n",
    }
    record = f"{dist}/RECORD"
    files[record] = "".join(f"{name},,\n" for name in [*files, record])
    path = directory / f"seed_probe-{version}-py3-none-any.whl"
    with ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path



def test_uv_installs_and_updates_independent_environments(create_integration_env, tmp_path, monkeypatch):
    first = create_integration_env(tmp_path / "first prefix with spaces")
    second = create_integration_env(tmp_path / "second prefix with spaces")
    monkeypatch.setenv("VIRTUAL_ENV", str(first.parent.parent))
    for python, version in ((first, "1.0.0"), (second, "2.0.0")):
        probe = _run(str(python), "-I", "-c", "import importlib.util; assert importlib.util.find_spec('pip') is None")
        assert probe == ""
        _run(*package_command("install", python, ["--no-index", "--no-deps", str(_wheel(tmp_path, version))]))
    _run(*package_command("install", first, ["--no-index", "--no-deps", "--reinstall", str(_wheel(tmp_path, "3.0.0"))]))
    for python, version in ((first, "3.0.0"), (second, "2.0.0")):
        command = python.parent / ("seed-probe.exe" if python.suffix == ".exe" else "seed-probe")
        prefix, executable, installed = json.loads(_run(str(command)))
        assert Path(prefix).resolve() == python.parent.parent.resolve()
        assert Path(executable).resolve() == python.resolve()
        assert installed == version
        assert "uv = " in (python.parent.parent / "pyvenv.cfg").read_text()
