"""Real CLI commands leave the service responsive and terminate on Stop."""

import asyncio
import json
import os
import sys
import time

import pytest
from cirno_core.agent.tools.cli_apps import CliAppsTool
from cirno_core.apps.cli.process import run_cli
from cirno_core.apps.cli.service import CliAppManager


def manager_for(tmp_path):
    manager = CliAppManager(workspace=tmp_path, data_dir=tmp_path / "state")
    manager.installed.put("python", {"entry_point": sys.executable})
    manager.data_dir.mkdir(exist_ok=True)
    for source in ("harness", "public", "extensions"):
        manager.registry._cache_path(source).write_text(
            json.dumps(
                {
                    "_cached_at": time.time(),
                    "data": {
                        "clis": [
                            {
                                "name": "python",
                                "entry_point": sys.executable,
                                "install_strategy": "bundled",
                            },
                        ]
                    },
                }
            )
        )
    return manager


@pytest.mark.asyncio
async def test_tool_does_not_block_event_loop_during_real_child(tmp_path, monkeypatch):
    manager = manager_for(tmp_path)
    monkeypatch.setattr("cirno_core.agent.tools.cli_apps.CliAppManager", lambda **kwargs: manager)
    operation = asyncio.create_task(
        CliAppsTool(workspace=tmp_path).execute(
            "python", ["-c", "import time; time.sleep(0.3); print('done')"]
        )
    )
    await asyncio.sleep(0.05)
    assert not operation.done(), "The event loop could not run until the CLI command had finished"
    assert "done" in await operation


@pytest.mark.asyncio
async def test_stop_reaps_cli_child_before_propagating_cancellation(tmp_path, monkeypatch):
    manager = manager_for(tmp_path)
    monkeypatch.setattr("cirno_core.agent.tools.cli_apps.CliAppManager", lambda **kwargs: manager)
    pid_path = tmp_path / "pid"
    operation = asyncio.create_task(
        CliAppsTool(workspace=tmp_path).execute(
            "python",
            [
                "-c",
                f"import os, pathlib, time; pathlib.Path({str(pid_path)!r}).write_text(str(os.getpid())); time.sleep(10)",
            ],
        )
    )
    deadline = time.monotonic() + 5
    while not pid_path.exists():
        assert time.monotonic() < deadline
        await asyncio.sleep(0.01)
    pid = int(pid_path.read_text())
    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(operation, timeout=2)
    if os.name == "posix":
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


def test_large_cli_output_is_drained_without_retaining_full_output(tmp_path):
    result = run_cli(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('x' * 2000000); sys.stderr.write('e' * 2000000)",
        ],
        cwd=tmp_path,
        timeout=5,
        env=dict(os.environ),
    )
    assert result.returncode == 0
    assert len(result.stdout) < 50_000 and len(result.stderr) < 50_000
    assert "truncated" in result.stdout and "truncated" in result.stderr


def test_capture_decodes_cli_bytes_as_utf8_with_replacement(tmp_path):
    result = run_cli(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xffok')"],
        cwd=tmp_path,
        timeout=5,
        env=dict(os.environ),
    )
    assert result.stdout == "\ufffdok"


def test_timeout_reaps_owned_child(tmp_path, monkeypatch):
    import subprocess

    processes = []
    spawn = subprocess.Popen

    def track_process(*args, **kwargs):
        process = spawn(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr("cirno_core.apps.cli.process.subprocess.Popen", track_process)
    with pytest.raises(subprocess.TimeoutExpired):
        run_cli(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(10)",
            ],
            cwd=tmp_path,
            timeout=0.2,
            env=dict(os.environ),
        )
    assert len(processes) == 1
    assert processes[0].returncode is not None
    if os.name == "posix":
        with pytest.raises(ProcessLookupError):
            os.kill(processes[0].pid, 0)
