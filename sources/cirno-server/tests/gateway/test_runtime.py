import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from cirno_core.runtime.processes import ManagedProcessRuntime, process_is_running
from cirno_core.utils.rotating_output import (
    BACKGROUND_LOG_BACKUP_COUNT_ENV,
    BACKGROUND_LOG_MAX_BYTES_ENV,
    BACKGROUND_LOG_PATH_ENV,
    DEFAULT_BACKUP_COUNT,
    DEFAULT_MAX_BYTES,
)
from cirno_server.lifecycle.contracts import RuntimeResult, ServerStartOptions, ServerStatus
from cirno_server.lifecycle.instance import ServerInstance, ServerRuntimePaths
from cirno_server.lifecycle.runtime import ServerRuntime


class FakeProcess:
    def __init__(self, pid: int = 12345):
        self.pid = pid


class PollableProcess(FakeProcess):
    def __init__(self, pid: int = 12345):
        super().__init__(pid)
        self.returncode: int | None = None

    def poll(self):
        return self.returncode


def _paths(tmp_path: Path) -> ServerRuntimePaths:
    return ServerRuntimePaths.for_instance(data_dir=tmp_path)


@pytest.mark.parametrize("damaged", [b"{", b"[]", b"\xff", b"x" * (64 * 1024 + 1)])
def test_invalid_process_record_cannot_be_overwritten_by_a_new_start(tmp_path, damaged):
    runtime = ServerRuntime(paths=_paths(tmp_path))
    runtime.paths.run_dir.mkdir()
    runtime.paths.state_path.write_bytes(damaged)
    with pytest.raises(ValueError, match="[Pp]rocess state"):
        with runtime.foreground_instance(ServerStartOptions(port=18790)):
            pytest.fail("An invalid owner record must be resolved before starting another service")
    assert runtime.paths.state_path.read_bytes() == damaged


def test_runtime_state_publish_keeps_existing_snapshot_readable(tmp_path):
    """Status polling must not prevent a gateway from publishing readiness."""
    from cirno_core.utils.atomic_file import open_atomic_snapshot

    runtime = ServerRuntime(paths=_paths(tmp_path / "网关 home"))
    previous = {"pid": os.getpid(), "identity": "fixture", "command": ["cirno", "gateway"]}
    current = {**previous, "health_host": "127.0.0.1"}
    runtime._write_state(previous)
    with open_atomic_snapshot(runtime.paths.state_path) as snapshot:
        runtime._write_state(current)
        assert json.loads(snapshot.read()) == previous
        assert runtime._read_state() == current
    assert list(runtime.paths.run_dir.glob("*.tmp")) == []
    if os.name != "nt":
        assert runtime.paths.state_path.stat().st_mode & 0o777 == 0o600


def test_runtime_state_reader_does_not_block_publish_while_decoding(tmp_path, monkeypatch):
    """Pause a real status read while a readiness update replaces its record."""
    runtime = ServerRuntime(paths=_paths(tmp_path))
    previous = {"pid": os.getpid(), "identity": "fixture"}
    current = {**previous, "health_host": "127.0.0.1"}
    runtime._write_state(previous)
    decode = json.loads

    def publish_during_decode(value, **kwargs):
        runtime._write_state(current)
        return decode(value, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr("cirno_core.runtime.processes.json.loads", publish_during_decode)
        assert runtime._read_state() == previous
    assert runtime._read_state() == current


_FOREGROUND_CHILD = r"""
import os
import signal
import sys
import time
from pathlib import Path

from cirno_server.lifecycle.contracts import ServerAlreadyRunningError, ServerStartOptions
from cirno_server.lifecycle.runtime import ServerRuntime
from cirno_server.lifecycle.instance import ServerRuntimePaths

root = Path(sys.argv[1])
duration = float(sys.argv[2])
marker = Path(sys.argv[3])
runtime = ServerRuntime(paths=ServerRuntimePaths.for_instance(data_dir=root))

def publish_marker(detail):
    pending = marker.with_suffix(".tmp")
    pending.write_text(detail, encoding="utf-8")
    pending.replace(marker)

def stop(*_args):
    raise SystemExit(0)

try:
    if os.name != "nt":
        signal.signal(signal.SIGTERM, stop)
    with runtime.foreground_instance(ServerStartOptions(port=18790)):
        publish_marker(f"claimed:{os.getpid()}")
        time.sleep(duration)
except ServerAlreadyRunningError:
    publish_marker("occupied")
    raise SystemExit(17)
except BaseException as exc:
    publish_marker(f"error:{type(exc).__name__}:{exc}")
    raise
"""


def _foreground_child(
    runtime_dir: Path,
    duration_s: float,
    marker: Path,
) -> subprocess.Popen[str]:
    env = os.environ.copy()
    root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (root, env.get("PYTHONPATH"))))
    return subprocess.Popen(
        [
            sys.executable,
            "-c",
            _FOREGROUND_CHILD,
            str(runtime_dir),
            str(duration_s),
            str(marker),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        start_new_session=os.name != "nt",
    )


def _wait_for_claim(
    process: subprocess.Popen[str],
    marker: Path,
) -> int:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if marker.exists():
            detail = marker.read_text(encoding="utf-8")
            if detail.startswith("claimed:"):
                return int(detail.partition(":")[2])
            pytest.fail(f"gateway claim failed: returncode={process.poll()}, {detail}")
        if process.poll() is not None:
            break
        time.sleep(0.01)
    detail = marker.read_text(encoding="utf-8") if marker.exists() else "no marker"
    pytest.fail(f"gateway claim failed: returncode={process.poll()}, {detail}")


class _ManagedForegroundChildRuntime(ServerRuntime):
    """Launch the foreground claim helper through the managed-process path."""

    def __init__(self, *, data_dir: Path, marker: Path) -> None:
        super().__init__(
            paths=_paths(data_dir),
            platform_name="Windows",
            python_executable=sys.executable,
        )
        self._data_dir = data_dir
        self._marker = marker

    def _build_child_command(self, options: ServerStartOptions) -> list[str]:
        return [
            self.python_executable,
            "-c",
            _FOREGROUND_CHILD,
            str(self._data_dir),
            "30",
            str(self._marker),
        ]


def test_config_files_in_one_instance_share_the_same_process_owner(tmp_path):
    first = ServerInstance.resolve(config_path=tmp_path / "one.json", workspace="/tmp/a")
    second = ServerInstance.resolve(config_path=tmp_path / "two.json", workspace="/tmp/b")
    assert first.paths == second.paths
    assert first.paths.state_path == tmp_path / "state" / "run" / "gateway.json"


def test_default_instance_preserves_released_gateway_paths() -> None:
    config_path = Path.home() / ".cirno" / "config.json"

    instance = ServerInstance.resolve(config_path=config_path)

    assert instance.paths.state_path == config_path.parent / "state" / "run" / "gateway.json"
    assert instance.paths.log_path == config_path.parent / "state" / "logs" / "gateway.log"
    assert instance.start_options(port=18790) == ServerStartOptions(port=18790, home=str(instance.home) if instance.home is not None else None)


def test_custom_instance_round_trips_the_same_child_selectors(tmp_path: Path) -> None:
    config_path = tmp_path / "instance" / "config.json"
    workspace = tmp_path / "workspace"
    parent = ServerInstance.resolve(
        config_path=config_path,
        workspace=str(workspace),
    )
    options = parent.start_options(port=18790)

    child = ServerInstance.resolve(
        config_path=options.config_path or "",
        workspace=options.workspace,
    )

    assert child == parent
    assert parent.paths.state_path.name == "gateway.json"


def test_start_background_writes_state_and_child_command(tmp_path, monkeypatch):
    calls: list[dict] = []

    def fake_popen(command, **kwargs):
        calls.append({"command": command, "kwargs": kwargs})
        return FakeProcess()

    runtime = ServerRuntime(
        paths=_paths(tmp_path),
        platform_name="Linux",
        python_executable="/python",
        popen=fake_popen,
        sleep=lambda _seconds: None,
    )
    monkeypatch.setattr(runtime, "_is_pid_running", lambda _pid: True)
    monkeypatch.setattr(runtime, "_process_identity", lambda _pid: 12345)

    result = runtime.start_background(
        ServerStartOptions(
            port=18790,
            verbose=True,
            workspace="/tmp/workspace",
            config_path="/tmp/config.json",
        )
    )

    assert result.ok is True
    assert result.status.running is True
    assert calls[0]["command"] == [
        "/python",
        "-m",
        "cirno",
        "--health-port",
        "18790",
        "--verbose",
        "--workspace",
        "/tmp/workspace",
        "--config",
        "/tmp/config.json",
    ]
    assert calls[0]["kwargs"]["start_new_session"] is True
    child_env = calls[0]["kwargs"]["env"]
    assert child_env[BACKGROUND_LOG_PATH_ENV] == str(runtime.paths.log_path)
    assert child_env[BACKGROUND_LOG_MAX_BYTES_ENV] == str(DEFAULT_MAX_BYTES)
    assert child_env[BACKGROUND_LOG_BACKUP_COUNT_ENV] == str(DEFAULT_BACKUP_COUNT)
    state = json.loads(runtime.paths.state_path.read_text(encoding="utf-8"))
    assert state["pid"] == 12345
    assert state["identity"] == 12345
    assert state["port"] == 18790
    assert state["launch_mode"] == "background"
    assert result.status.launch_mode == "background"


def test_read_log_tail_spans_rotated_files(tmp_path: Path) -> None:
    runtime = ServerRuntime(paths=_paths(tmp_path))
    runtime.paths.logs_dir.mkdir(parents=True)
    runtime.paths.log_path.write_text("current-1\ncurrent-2\n", encoding="utf-8")
    runtime.paths.log_path.with_name("gateway.log.1").write_text(
        "backup-1\nbackup-2\n", encoding="utf-8"
    )
    runtime.paths.log_path.with_name("gateway.log.2").write_text(
        "oldest\n", encoding="utf-8"
    )

    assert runtime.read_log_tail(tail=5) == [
        "oldest",
        "backup-1",
        "backup-2",
        "current-1",
        "current-2",
    ]


def test_foreground_gateway_claim_is_discoverable_and_released(tmp_path, monkeypatch):
    runtime = ServerRuntime(
        paths=_paths(tmp_path),
        platform_name="Darwin",
        python_executable="/python",
    )
    monkeypatch.setattr(runtime, "_process_identity", lambda _pid: 54321)
    monkeypatch.setattr(runtime, "_is_pid_running", lambda _pid: True)
    options = ServerStartOptions(
        port=18790,
        workspace="/tmp/workspace",
        config_path="/tmp/config.json",
    )

    with runtime.foreground_instance(options):
        status = runtime.status()
        assert status.running is True
        assert status.pid == os.getpid()
        assert status.port == 18790
        assert status.launch_mode == "foreground"
        assert status.command == tuple(runtime._build_child_command(options))

    assert runtime.status().running is False
    assert not runtime.paths.state_path.exists()




def test_foreground_gateway_release_preserves_a_replacement_state(tmp_path, monkeypatch):
    runtime = ServerRuntime(paths=_paths(tmp_path), platform_name="Darwin")
    monkeypatch.setattr(runtime, "_process_identity", lambda pid: pid)
    with runtime.foreground_instance(ServerStartOptions(port=18790)):
        replacement = json.loads(runtime.paths.state_path.read_text(encoding="utf-8"))
        replacement["pid"] = os.getpid() + 1
        replacement["identity"] = replacement["pid"]
        runtime.paths.state_path.write_text(json.dumps(replacement), encoding="utf-8")

    assert runtime.paths.state_path.exists()


def test_foreground_gateway_clears_its_state_after_an_error(tmp_path, monkeypatch):
    runtime = ServerRuntime(paths=_paths(tmp_path), platform_name="Darwin")
    monkeypatch.setattr(runtime, "_process_identity", lambda pid: pid)

    with pytest.raises(RuntimeError, match="startup failed"):
        with runtime.foreground_instance(ServerStartOptions(port=18790)):
            raise RuntimeError("startup failed")

    assert not runtime.paths.state_path.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX signal escalation regression")
def test_stop_allows_a_foreground_gateway_to_release_before_timeout(tmp_path):
    runtime = ServerRuntime(paths=_paths(tmp_path))
    marker = tmp_path / "foreground.marker"
    child = _foreground_child(tmp_path, 30, marker)
    try:
        _wait_for_claim(child, marker)

        result = runtime.stop(timeout_s=1)
        child.wait(timeout=3)

        assert result.ok is True
        assert child.returncode == 0
        assert not runtime.paths.state_path.exists()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=3)


def test_competing_foreground_claim_preserves_the_live_gateway(tmp_path):
    runtime = ServerRuntime(paths=_paths(tmp_path))
    first_marker = tmp_path / "first.marker"
    first = _foreground_child(tmp_path, 30, first_marker)
    try:
        first_pid = _wait_for_claim(first, first_marker)
        second_marker = tmp_path / "second.marker"
        second = _foreground_child(tmp_path, 0, second_marker)
        try:
            second.wait(timeout=3)
            assert second_marker.read_text(encoding="utf-8") == "occupied"
            assert second.returncode == 17
        finally:
            if second.poll() is None:
                second.kill()
                second.wait(timeout=3)

        state = json.loads(runtime.paths.state_path.read_text(encoding="utf-8"))
        assert state["pid"] == first_pid
        assert runtime.status().pid == first_pid
    finally:
        if first.poll() is None:
            first.terminate()
            first.wait(timeout=3)
        runtime.status()


def test_stop_reaps_an_owned_child_without_consuming_the_shutdown_timeout(
    tmp_path,
    monkeypatch,
):
    process = PollableProcess()
    sleeps: list[float] = []
    runtime = ServerRuntime(
        paths=_paths(tmp_path),
        platform_name="Darwin",
        popen=lambda *_args, **_kwargs: process,
        sleep=sleeps.append,
    )
    monkeypatch.setattr(runtime, "_process_identity", lambda _pid: 12345)
    monkeypatch.setattr(
        "cirno_core.runtime.processes.os.getpgid",
        lambda _pid: process.pid,
        raising=False,
    )
    monkeypatch.setattr(
        "cirno_core.runtime.processes.os.killpg",
        lambda _pgid, _signal: setattr(process, "returncode", -15),
        raising=False,
    )

    assert runtime.start_background(ServerStartOptions(port=18790)).ok is True
    sleeps.clear()
    result = runtime.stop(timeout_s=20)

    assert result.ok is True
    assert sleeps == []


def test_repeated_background_starts_create_only_one_process(tmp_path, monkeypatch):
    calls: list[list[str]] = []

    def fake_popen(command, **_kwargs):
        calls.append(command)
        return FakeProcess()

    first = ServerRuntime(
        paths=_paths(tmp_path),
        platform_name="Linux",
        popen=fake_popen,
        sleep=lambda _seconds: None,
    )
    second = ServerRuntime(
        paths=_paths(tmp_path),
        platform_name="Linux",
        popen=fake_popen,
        sleep=lambda _seconds: None,
    )
    for runtime in (first, second):
        monkeypatch.setattr(runtime, "_is_pid_running", lambda _pid: True)
        monkeypatch.setattr(runtime, "_process_identity", lambda _pid: 12345)

    results = [
        first.start_background(ServerStartOptions(port=18790)),
        second.start_background(ServerStartOptions(port=18790)),
    ]

    assert len(calls) == 1
    assert sorted((result.ok, result.message) for result in results) == [
        (False, "server_already_running"),
        (True, "server_started_background"),
    ]


def test_restart_does_not_start_a_gateway_that_is_not_running(tmp_path):
    spawned: list[list[str]] = []
    runtime = ServerRuntime(
        paths=_paths(tmp_path),
        platform_name="Linux",
        popen=lambda command, **_kwargs: spawned.append(command),
    )

    result = runtime.restart(ServerStartOptions(port=18790))

    assert result.ok is False
    assert result.message == "server_not_running"
    assert spawned == []


def test_restart_does_not_detach_a_foreground_gateway(tmp_path, monkeypatch):
    runtime = ServerRuntime(paths=_paths(tmp_path), platform_name="Linux")
    status = ServerStatus(
        running=True,
        pid=12345,
        state_path=runtime.paths.state_path,
        log_path=runtime.paths.log_path,
        launch_mode="foreground",
    )
    monkeypatch.setattr(runtime, "status", lambda **_kwargs: status)
    monkeypatch.setattr(
        runtime,
        "_stop",
        lambda **_kwargs: pytest.fail("foreground gateway must not be stopped"),
    )

    result = runtime.restart(ServerStartOptions(port=18790))

    assert result.ok is False
    assert result.message == "server_foreground_restart_required"


def test_restart_stops_then_starts_the_background_gateway(tmp_path, monkeypatch):
    runtime = ServerRuntime(paths=_paths(tmp_path), platform_name="Linux")
    status = ServerStatus(
        running=True,
        pid=12345,
        state_path=runtime.paths.state_path,
        log_path=runtime.paths.log_path,
        launch_mode="background",
    )
    monkeypatch.setattr(runtime, "status", lambda **_kwargs: status)

    def stop(*, timeout_s: int):
        assert timeout_s == 20
        return SimpleNamespace(ok=True, message="server_stopped", status=status)

    monkeypatch.setattr(runtime, "_stop", stop)
    monkeypatch.setattr(
        runtime,
        "_start_background",
        lambda _options: RuntimeResult(True, "server_started_background", status),
    )

    result = runtime.restart(ServerStartOptions(port=18790))

    assert result.ok is True






























def test_start_background_uses_windows_process_group_flags(tmp_path, monkeypatch):
    calls: list[dict] = []

    def fake_popen(command, **kwargs):
        calls.append({"command": command, "kwargs": kwargs})
        return FakeProcess()

    runtime = ServerRuntime(
        paths=_paths(tmp_path),
        platform_name="Windows",
        python_executable="python.exe",
        popen=fake_popen,
        sleep=lambda _seconds: None,
    )
    monkeypatch.setattr(runtime, "_is_pid_running", lambda _pid: True)
    monkeypatch.setattr(runtime, "_process_identity", lambda _pid: "created-at")

    result = runtime.start_background(ServerStartOptions(port=18790))

    assert result.ok is True
    assert "creationflags" in calls[0]["kwargs"]
    assert "start_new_session" not in calls[0]["kwargs"]


@pytest.mark.skipif(
    os.name != "nt" or sys.prefix == sys.base_prefix,
    reason="requires a Windows virtualenv launcher",
)
def test_managed_background_hands_off_virtualenv_launcher_pid(tmp_path: Path) -> None:
    marker = tmp_path / "managed-foreground.marker"
    runtime = _ManagedForegroundChildRuntime(data_dir=tmp_path, marker=marker)

    result = runtime.start_background(ServerStartOptions(port=18790))
    launcher = runtime._owned_process
    assert isinstance(launcher, subprocess.Popen)
    try:
        claimed_pid = _wait_for_claim(launcher, marker)

        status = runtime.status()
        assert result.ok is True
        assert claimed_pid != launcher.pid
        assert status.pid == claimed_pid
        assert status.launch_mode == "background"
    finally:
        if runtime.status().running:
            runtime.stop(timeout_s=3)
        launcher.wait(timeout=3)


@pytest.mark.skipif(os.name != "nt", reason="requires Windows process identity APIs")
def test_windows_identity_polling_reuses_pointer_types(tmp_path, monkeypatch):
    import ctypes

    pointer_types = set()
    pointer = ctypes.POINTER

    def record_pointer_type(cls):
        result = pointer(cls)
        pointer_types.add(result)
        return result

    monkeypatch.setattr(ctypes, "POINTER", record_pointer_type)
    runtime = ServerRuntime(paths=_paths(tmp_path))
    pid = os.getpid()
    identity = runtime.process_identity(pid)
    assert isinstance(identity, str) and identity.isdecimal()
    warmed_types = pointer_types.copy()

    for _ in range(100):
        assert runtime.process_identity(pid) == identity

    # Fresh pointer types remain cached on Python versions before 3.14.
    assert pointer_types == warmed_types


def test_windows_process_probe_never_sends_ctrl_c(monkeypatch):
    monkeypatch.setattr(
        "cirno_core.runtime.processes._windows_process_identity",
        lambda pid: "created-at" if pid == 12345 else None,
    )
    monkeypatch.setattr(
        "cirno_core.runtime.processes.os.kill",
        lambda *_args: pytest.fail("Windows process probes must not call os.kill(pid, 0)"),
    )

    assert process_is_running(12345, platform_name="Windows") is True
    assert process_is_running(54321, platform_name="Windows") is False


def test_windows_host_probe_stays_safe_when_target_platform_is_posix(monkeypatch):
    monkeypatch.setattr("cirno_core.runtime.processes._platform_name", lambda: "Windows")
    monkeypatch.setattr(
        "cirno_core.runtime.processes._windows_process_identity",
        lambda pid: "created-at" if pid == 12345 else None,
    )
    monkeypatch.setattr(
        "cirno_core.runtime.processes.os.kill",
        lambda *_args: pytest.fail("Windows process probes must not call os.kill(pid, 0)"),
    )

    assert process_is_running(12345, platform_name="Linux") is True
    assert process_is_running(54321, platform_name="Darwin") is False


def test_posix_process_probe_treats_a_zombie_as_stopped(monkeypatch):
    monkeypatch.setattr("cirno_core.runtime.processes._platform_name", lambda: "Darwin")
    monkeypatch.setattr("cirno_core.runtime.processes.os.kill", lambda *_args: None)
    monkeypatch.setattr(
        "cirno_core.runtime.processes.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="Z+"),
    )

    assert process_is_running(12345, platform_name="Darwin") is False


def test_windows_host_identity_stays_safe_when_target_platform_is_posix(tmp_path, monkeypatch):
    runtime = ServerRuntime(paths=_paths(tmp_path), platform_name="Linux")
    monkeypatch.setattr("cirno_core.runtime.processes._platform_name", lambda: "Windows")
    monkeypatch.setattr(
        "cirno_core.runtime.processes._windows_process_identity",
        lambda pid: "created-at" if pid == 12345 else None,
    )
    monkeypatch.setattr(
        "cirno_core.runtime.processes.os.getpgid",
        lambda *_args: pytest.fail("Windows process identities must not use POSIX APIs"),
        raising=False,
    )

    assert runtime.process_identity(12345) == "created-at"




def test_status_clears_stale_state(tmp_path, monkeypatch):
    runtime = ServerRuntime(paths=_paths(tmp_path), platform_name="Linux")
    runtime.paths.run_dir.mkdir(parents=True)
    runtime.paths.state_path.write_text('{"pid": 12345, "identity": 12345}', encoding="utf-8")
    monkeypatch.setattr(runtime, "_is_pid_running", lambda _pid: False)

    status = runtime.status()

    assert status.running is False
    assert status.reason == "stale_state"
    assert not runtime.paths.state_path.exists()


def test_status_clears_state_when_pid_identity_changes(tmp_path, monkeypatch):
    runtime = ServerRuntime(paths=_paths(tmp_path), platform_name="Linux")
    runtime.paths.run_dir.mkdir(parents=True)
    runtime.paths.state_path.write_text('{"pid": 12345, "identity": 111}', encoding="utf-8")
    monkeypatch.setattr(runtime, "_is_pid_running", lambda _pid: True)
    monkeypatch.setattr(runtime, "_process_identity", lambda _pid: 222)

    status = runtime.status()

    assert status.running is False
    assert status.reason == "stale_state"
    assert not runtime.paths.state_path.exists()


def test_status_keeps_live_state_when_identity_probe_is_temporarily_unavailable(
    tmp_path,
    monkeypatch,
):
    runtime = ServerRuntime(paths=_paths(tmp_path), platform_name="Darwin")
    runtime.paths.run_dir.mkdir(parents=True)
    runtime.paths.state_path.write_text(
        '{"pid": 12345, "identity": "created-at"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime, "_is_pid_running", lambda _pid: True)
    monkeypatch.setattr(runtime, "_process_identity", lambda _pid: None)

    status = runtime.status()

    assert status.running is True
    assert status.reason == "identity_unavailable"
    assert runtime.paths.state_path.exists()


def test_status_distinguishes_live_process_from_degraded_gateway_readiness(
    tmp_path,
    monkeypatch,
):
    runtime = ServerRuntime(paths=_paths(tmp_path), platform_name="Linux")
    runtime.paths.run_dir.mkdir(parents=True)
    runtime.paths.state_path.write_text(
        json.dumps(
            {
                "pid": 12345,
                "identity": 42,
                "port": 18791,
                "health_host": "127.0.0.1",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime, "_is_pid_running", lambda _pid: True)
    monkeypatch.setattr(runtime, "_process_identity", lambda _pid: 42)
    monkeypatch.setattr(
        "cirno_server.lifecycle.runtime.health_ready",
        lambda _host, _port: False,
    )

    status = runtime.status()

    assert status.running is True
    assert status.ready is False
    assert status.reason == "websocket_unavailable"


def test_stop_refuses_to_signal_a_process_when_identity_cannot_be_verified(
    tmp_path,
    monkeypatch,
):
    runtime = ServerRuntime(paths=_paths(tmp_path), platform_name="Darwin")
    runtime.paths.run_dir.mkdir(parents=True)
    runtime.paths.state_path.write_text(
        '{"pid": 12345, "identity": "created-at"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime, "_is_pid_running", lambda _pid: True)
    monkeypatch.setattr(runtime, "_process_identity", lambda _pid: None)
    monkeypatch.setattr(
        runtime,
        "_terminate",
        lambda *_args, **_kwargs: pytest.fail("an unverified PID must not be signalled"),
    )

    result = runtime.stop()

    assert result.ok is False
    assert result.message == "server_identity_unavailable"
    assert result.status.running is True
    assert runtime.paths.state_path.exists()


def test_posix_process_identity_includes_start_time(
    tmp_path,
    monkeypatch,
):
    runtime = ServerRuntime(paths=_paths(tmp_path), platform_name="Linux")
    monkeypatch.setattr("cirno_core.runtime.processes._platform_name", lambda: "Linux")
    monkeypatch.setattr("cirno_core.runtime.processes.os.getpgid", lambda _pid: 42, raising=False)
    monkeypatch.setattr(runtime, "_posix_process_started_at", lambda _pid: "987654")

    assert runtime.process_identity(12345) == "42:987654"
    assert runtime._record_matches_process({"identity": 42}, 12345) is False


def test_darwin_process_identity_is_locale_independent(tmp_path, monkeypatch):
    runtime = ServerRuntime(
        paths=_paths(tmp_path),
        platform_name="Darwin",
        subprocess_run=lambda *_args, **_kwargs: pytest.fail(
            "Darwin identities must not depend on localized subprocess output"
        ),
    )
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    monkeypatch.setenv("LC_ALL", "zh_CN.UTF-8")
    monkeypatch.setattr("cirno_core.runtime.processes._platform_name", lambda: "Darwin")
    started_at = int(time.mktime((2026, 8, 18, 2, 17, 54, -1, -1, -1)))
    monkeypatch.setattr(
        "cirno_core.runtime.processes._darwin_process_birth",
        lambda _pid: (42, started_at, 123456),
    )

    identity = f"darwin:42:{started_at}:123456"
    assert runtime.process_identity(12345) == identity
    assert runtime.process_identity_record(12345) == {
        "identity": identity,
    }
    assert runtime._record_matches_process({"identity": 42}, 12345) is False


@pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS proc_pidinfo")
def test_darwin_live_process_identity_is_stable(tmp_path):
    runtime = ServerRuntime(paths=_paths(tmp_path), platform_name="Darwin")

    first = runtime.process_identity(os.getpid())
    second = runtime.process_identity(os.getpid())

    assert isinstance(first, str)
    assert first.startswith("darwin:")
    assert second == first


def test_stop_terminates_recorded_process(tmp_path, monkeypatch):
    runtime = ServerRuntime(paths=_paths(tmp_path), platform_name="Linux")
    runtime.paths.run_dir.mkdir(parents=True)
    runtime.paths.state_path.write_text('{"pid": 12345, "identity": 12345}', encoding="utf-8")
    monkeypatch.setattr(runtime, "_is_pid_running", lambda _pid: True)
    monkeypatch.setattr(runtime, "_process_identity", lambda _pid: 12345)
    terminated: list[int] = []

    def fake_terminate(pid, timeout_s):
        terminated.append(pid)
        return True

    monkeypatch.setattr(runtime, "_terminate", fake_terminate)

    result = runtime.stop()

    assert result.ok is True
    assert terminated == [12345]
    assert not runtime.paths.state_path.exists()


def test_stop_keeps_state_when_process_survives_timeout(tmp_path, monkeypatch):
    runtime = ServerRuntime(paths=_paths(tmp_path), platform_name="Linux")
    runtime.paths.run_dir.mkdir(parents=True)
    runtime.paths.state_path.write_text('{"pid": 12345, "identity": 12345}', encoding="utf-8")
    monkeypatch.setattr(runtime, "_is_pid_running", lambda _pid: True)
    monkeypatch.setattr(runtime, "_process_identity", lambda _pid: 12345)
    monkeypatch.setattr(runtime, "_terminate", lambda _pid, timeout_s: False)

    result = runtime.stop(timeout_s=0)

    assert result.ok is False
    assert result.message == "server_stop_timeout"
    assert result.status.running is True
    assert result.status.reason == "stop_timeout"
    assert runtime.paths.state_path.exists()


def test_stop_succeeds_when_process_exits_at_timeout_boundary(tmp_path, monkeypatch):
    runtime = ServerRuntime(paths=_paths(tmp_path), platform_name="Linux")
    running = ServerStatus(
        running=True,
        pid=12345,
        state_path=runtime.paths.state_path,
        log_path=runtime.paths.log_path,
    )
    stopped = ServerStatus(
        running=False,
        pid=None,
        state_path=runtime.paths.state_path,
        log_path=runtime.paths.log_path,
        reason="stop_timeout",
    )
    statuses = iter([running, stopped])
    monkeypatch.setattr(runtime, "status", lambda **_kwargs: next(statuses))
    monkeypatch.setattr(runtime, "_read_state", lambda: {"pid": 12345, "identity": 12345})
    monkeypatch.setattr(runtime, "_process_identity_match", lambda *_args: "match")
    monkeypatch.setattr(runtime, "_terminate", lambda *_args, **_kwargs: False)

    result = runtime.stop(timeout_s=0)

    assert result.ok is True
    assert result.message == "server_stopped"
    assert result.status.running is False


def test_terminate_windows_targets_only_the_recorded_process_tree(tmp_path, monkeypatch):
    taskkill_calls: list[dict] = []
    wait_timeouts: list[int | float] = []

    def fake_run(command, **kwargs):
        taskkill_calls.append({"command": command, "kwargs": kwargs})

    runtime = ManagedProcessRuntime(
        paths=_paths(tmp_path),
        platform_name="Windows",
        subprocess_run=fake_run,
        sleep=lambda _seconds: None,
    )

    monkeypatch.setattr(
        "cirno_core.runtime.processes.os.kill",
        lambda *_args: pytest.fail("Windows termination must not broadcast a console event"),
    )

    def fake_wait_for_exit(_pid, _timeout_s):
        wait_timeouts.append(_timeout_s)
        # Simulate a process that exits only after its tree is forcibly terminated.
        return bool(taskkill_calls)

    monkeypatch.setattr(runtime, "_wait_for_exit", fake_wait_for_exit)

    assert runtime._terminate_windows(12345, timeout_s=20) is True
    assert wait_timeouts == [2]
    assert taskkill_calls == [
        {
            "command": ["taskkill", "/PID", "12345", "/T", "/F"],
            "kwargs": {
                "check": False,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "timeout": 2,
            },
        }
    ]




def test_windows_stop_does_not_force_a_pid_reused_during_grace(tmp_path, monkeypatch):
    killed = []
    runtime = ServerRuntime(
        paths=_paths(tmp_path), platform_name="Windows",
        subprocess_run=lambda *args, **kwargs: killed.append(args),
    )
    identity = "original-process"
    runtime._write_state({"pid": 12345, "identity": identity, "shutdown_token": "a" * 32})
    monkeypatch.setattr(runtime, "_process_identity", lambda _pid: identity)
    monkeypatch.setattr(runtime, "_is_pid_running", lambda _pid: True)
    monkeypatch.setattr("cirno_server.lifecycle.runtime.request_windows_shutdown", lambda *_args: True)

    def exit_and_reuse_pid(_pid, _timeout):
        nonlocal identity
        identity = "replacement-process"
        return False

    monkeypatch.setattr(runtime, "_wait_for_exit", exit_and_reuse_pid)

    result = runtime.stop(timeout_s=1)

    assert result.status.running is False
    assert killed == []


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups are unavailable")
def test_terminate_posix_tolerates_process_group_disappearing_before_sigkill(
    tmp_path,
    monkeypatch,
) -> None:
    runtime = ServerRuntime(
        paths=_paths(tmp_path),
        platform_name="Darwin",
        sleep=lambda _seconds: None,
    )
    waits = iter([False, True])
    monkeypatch.setattr(
        "cirno_core.runtime.processes.os.getpgid",
        lambda _pid: 1234,
        raising=False,
    )

    def fake_killpg(_pgid, sent_signal):
        if sent_signal == signal.SIGKILL:
            raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr("cirno_core.runtime.processes.os.killpg", fake_killpg, raising=False)
    monkeypatch.setattr(runtime, "_wait_for_exit", lambda *_args: next(waits))

    assert runtime._terminate_posix(1234, timeout_s=1) is True
