"""Server-specific configuration for the shared background process runtime."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Generator

from cirno_core.runtime.processes import (
    ManagedProcessRuntime,
    ProcessResult,
)
from cirno_server.lifecycle.contracts import (
    RuntimeResult,
    ServerAlreadyRunningError,
    ServerHealthIdentity,
    ServerLaunchMode,
    ServerStartOptions,
    ServerStatus,
)
from cirno_server.lifecycle.health import health_ready
from cirno_server.lifecycle.instance import ServerRuntimePaths, build_server_command
from cirno_server.lifecycle.windows_shutdown import WindowsShutdownEvent, request_windows_shutdown
from filelock import FileLock
from loguru import logger


class ServerRuntime(ManagedProcessRuntime[ServerStartOptions]):
    """Own the lifecycle of one Cirno service process."""

    service_name = "server"

    def __init__(
        self,
        *,
        paths: ServerRuntimePaths | None = None,
        platform_name: str | None = None,
        python_executable: str | None = None,
        popen: Callable[..., Any] = subprocess.Popen,
        subprocess_run: Callable[..., Any] = subprocess.run,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(
            paths=paths or ServerRuntimePaths.for_instance(),
            platform_name=platform_name,
            python_executable=python_executable,
            popen=popen,
            subprocess_run=subprocess_run,
            sleep=sleep,
        )
        self._shutdown_signal: WindowsShutdownEvent | None = None

    def _build_child_command(self, options: ServerStartOptions) -> list[str]:
        return build_server_command(self.python_executable, options)

    def _transition_lock(self) -> FileLock:
        """Serialize long lifecycle transitions without blocking child cleanup."""
        return FileLock(f"{self.paths.state_path}.transition.lock")

    def start_background(self, options: ServerStartOptions) -> RuntimeResult:
        """Start the gateway detached from the current terminal."""
        with self._transition_lock(), self._lifecycle_lock():
            return self._start_background(options)

    def _start_background(self, options: ServerStartOptions) -> RuntimeResult:
        result = super()._start_background(options)
        if not result.ok:
            return self._result(result)
        state = self._read_state()
        if state and result.status.pid == state.get("pid"):
            state["launch_mode"] = "background"
            state["pending_pid_handoff"] = True
            self._write_state(state)
        return RuntimeResult(True, result.message, self.status())

    def stop(self, *, timeout_s: int = 20) -> RuntimeResult:
        """Stop the gateway recorded by this runtime."""
        with self._transition_lock():
            result = self._stop(timeout_s=timeout_s)
            return self._result(result)

    def status(self, *, reason: str | None = None) -> ServerStatus:
        """Return the process state and health-listener readiness."""
        process = super().status(reason=reason)
        state = self._read_state() if process.running else None
        raw_mode = state.get("launch_mode") if state else None
        launch_mode: ServerLaunchMode = (
            raw_mode if raw_mode in {"foreground", "background"} else "unknown"
        )
        ready: bool | None = None
        health_host = state.get("health_host") if state else None
        if (
            process.running
            and process.pid != os.getpid()
            and isinstance(health_host, str)
            and process.port is not None
        ):
            ready = health_ready(health_host, process.port)
        status_reason = process.reason
        if ready is False and reason is None and status_reason == "running":
            status_reason = "websocket_unavailable"
        return ServerStatus(
            running=process.running,
            pid=process.pid,
            state_path=process.state_path,
            log_path=process.log_path,
            started_at=process.started_at,
            port=process.port,
            command=process.command,
            reason=status_reason,
            launch_mode=launch_mode,
            ready=ready,
        )

    def publish_health_host(self, host: str) -> None:
        """Record the management bind host for out-of-process readiness diagnostics."""
        with self._lifecycle_lock():
            state = self._read_state()
            if not state or not self._record_matches_process(state, os.getpid()):
                return
            state["health_host"] = host
            self._write_state(state)

    def verify_ready(
        self, expected: ServerHealthIdentity, *, maintenance: bool | None = None
    ) -> bool:
        """Bind health to one live local process, not merely a responding port.

        This is local lifecycle evidence, not remote authentication. Missing
        identity metadata on an older host cannot confirm an update restart.
        """
        state = self._read_state()
        if not state:
            return False
        pid, host, port = state.get("pid"), state.get("health_host"), state.get("port")
        if (
            type(pid) is not int
            or type(port) is not int
            or not 0 < port < 65536
            or not isinstance(host, str)
            or not self._is_pid_running(pid)
            or not self._record_matches_process(state, pid)
        ):
            return False
        if not health_ready(host, port, expected=expected, maintenance=maintenance):
            return False
        # The process may have exited or been replaced while the HTTP probe ran.
        return (
            self._read_state() == state
            and self._is_pid_running(pid)
            and self._record_matches_process(state, pid)
        )

    @contextmanager
    def foreground_instance(self, options: ServerStartOptions) -> Generator[None]:
        """Publish this process and own its stop signal across asyncio.run()."""
        shutdown_signal = None
        if self.platform_name == "Windows" and os.name == "nt":
            identity = self.process_identity(os.getpid())
            if not isinstance(identity, str):
                raise OSError("Cannot identify the gateway process for Windows shutdown")
            shutdown_signal = WindowsShutdownEvent(os.getpid(), identity)
        self._shutdown_signal = shutdown_signal
        try:
            self._claim_current_process(options)
            try:
                yield
            finally:
                self._release_current_process()
        finally:
            self._shutdown_signal = None
            if shutdown_signal is not None:
                shutdown_signal.close()

    async def wait_for_shutdown_request(self, shutdown_event: asyncio.Event) -> None:
        """Bridge the local Windows signal to the application's existing shutdown."""
        signal = self._shutdown_signal
        if signal is None:
            return
        waiter = asyncio.create_task(asyncio.to_thread(signal.wait))
        try:
            await asyncio.shield(waiter)
            logger.info("Server shutdown requested by local CLI")
            shutdown_event.set()
        finally:
            # Cancelling to_thread alone leaves its native wait alive. Wake it
            # before asyncio.run drains the executor and the owner closes the handle.
            signal.signal()
            await waiter

    def _terminate_windows(self, pid: int, *, timeout_s: int) -> bool:
        state = self._read_state()
        identity = self._process_identity(pid)
        if identity is None:
            return not self._is_pid_running(pid)
        if self._process_identity_match(state, pid) != "match":
            return False
        requested = False
        if isinstance(identity, str) and state is not None:
            try:
                requested = request_windows_shutdown(pid, identity, state.get("shutdown_token"))
            except OSError as exc:
                logger.warning("Could not request gateway shutdown: {}", exc)
        if requested and self._wait_for_exit(pid, timeout_s):
            return True
        current_identity = self._process_identity(pid)
        if current_identity is None:
            return not self._is_pid_running(pid)
        if current_identity != identity:
            return False
        if requested:
            logger.warning("Server did not exit within {}s; forcing PID tree {}", timeout_s, pid)
        else:
            logger.warning("Server shutdown signal unavailable; forcing PID tree {}", pid)
        return super()._terminate_windows(pid, timeout_s=timeout_s)

    def _claim_current_process(self, options: ServerStartOptions) -> ServerLaunchMode:
        pid = os.getpid()
        with self._transition_lock(), self._lifecycle_lock():
            current = self.status()
            state = self._read_state() or {}
            pid_handoff = (
                self.platform_name == "Windows"
                and current.running
                and current.pid != pid
                and current.pid == os.getppid()
                and state.get("pid") == current.pid
                and state.get("launch_mode") == "background"
                and state.get("pending_pid_handoff") is True
            )
            if current.running and current.pid != pid and not pid_handoff:
                raise ServerAlreadyRunningError(current)
            launch_mode: ServerLaunchMode = (
                "background"
                if state.get("launch_mode") == "background"
                and (state.get("pid") == pid or pid_handoff)
                else "foreground"
            )
            state.update(
                {
                    "pid": pid,
                    "started_at": datetime.now(UTC).isoformat(),
                    "platform": self.platform_name,
                    "port": options.port,
                    "workspace": options.workspace,
                    "config_path": options.config_path,
                    "command": self._build_child_command(options),
                    "log_path": str(self.paths.log_path),
                    "launch_mode": launch_mode,
                }
            )
            state.pop("pending_pid_handoff", None)
            state.update(self.process_identity_record(pid))
            state.pop("shutdown_token", None)
            if self._shutdown_signal is not None:
                state["shutdown_token"] = self._shutdown_signal.token
            self._write_state(state)
            return launch_mode

    def _release_current_process(self) -> None:
        with self._lifecycle_lock():
            state = self._read_state()
            if state and self._record_matches_process(state, os.getpid()):
                self._clear_state()

    def restart(self, options: ServerStartOptions, *, timeout_s: int = 20) -> RuntimeResult:
        """Restart an existing gateway without creating a new persistent instance."""
        with self._transition_lock():
            with self._lifecycle_lock():
                status = self.status()
                if not status.running:
                    return RuntimeResult(False, "server_not_running", status)
                if status.launch_mode == "foreground":
                    return RuntimeResult(
                        False,
                        "server_foreground_restart_required",
                        status,
                    )
            stop_result = self._stop(timeout_s=timeout_s)
            if not stop_result.ok:
                return self._result(stop_result)
            with self._lifecycle_lock():
                return self._start_background(options)

    def _result(self, result: ProcessResult) -> RuntimeResult:
        status = result.status
        gateway_status = status if isinstance(status, ServerStatus) else self.status()
        return RuntimeResult(result.ok, result.message, gateway_status)
