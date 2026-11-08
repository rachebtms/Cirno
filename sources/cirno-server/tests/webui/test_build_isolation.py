"""The PEP 517 build can run frontend commands before Cirno dependencies exist."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from cirno_server.webui.bun import bun_environment


@pytest.mark.parametrize("runner", ["npm", "bun"])
def test_build_command_does_not_import_the_application(tmp_path, runner):
    hook = Path(__file__).resolve().parents[2] / "hatch_build.py"
    executable = tmp_path / runner
    executable.write_bytes(b"fake runtime")
    script = """
import importlib.abc, importlib.util, subprocess, sys
from pathlib import Path
class NoApplication(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name in {'cirno_core','cirno_server','cirno'}:
            raise ModuleNotFoundError('Application imported during isolated build: ' + name)
sys.meta_path.insert(0, NoApplication())
spec=importlib.util.spec_from_file_location('build_hook', sys.argv[1])
hook=importlib.util.module_from_spec(spec);spec.loader.exec_module(hook)
builder=hook._load_webui_build_module()
seen=[]
def run(command, **kwargs):
    seen.append(command)
    assert kwargs['check'] is True
    assert kwargs['timeout'] == 900
    return subprocess.CompletedProcess(command, 0)
builder._run_frontend_command([sys.argv[2], 'run', 'build'], cwd=Path.cwd(), subprocess_run=run)
assert len(seen) == 1
"""
    result = subprocess.run([sys.executable, "-I", "-c", script, str(hook), str(executable)],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_private_bun_alias_is_removed_without_modifying_the_parent_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", "original")
    runtime = tmp_path / "bun"
    runtime.write_bytes(b"runtime")
    with bun_environment(str(runtime)) as env:
        alias_dir = Path(env["PATH"].split(os.pathsep)[0])
        assert (alias_dir / ("node.exe" if os.name == "nt" else "node")).read_bytes() == b"runtime"
        assert env["PATH"].endswith(os.pathsep + "original")
    assert not alias_dir.exists()
    assert os.environ["PATH"] == "original"
