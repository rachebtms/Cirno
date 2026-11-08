"""CLI subprocess ownership with bounded in-memory output and cancellation."""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import BinaryIO

_CAPTURE_BYTES = 48_000


class CliRunCancelled(RuntimeError):
    """The execution owner stopped this command before returning its result."""


def _read_output(file: BinaryIO) -> str:
    size = file.tell()
    file.seek(0)
    content = file.read(_CAPTURE_BYTES).decode("utf-8", errors="replace")
    if size > _CAPTURE_BYTES:
        content += f"\n... truncated {size - _CAPTURE_BYTES} bytes ..."
    return content


def run_cli(
    argv: list[str],
    *,
    cwd: Path,
    timeout: float,
    env: dict[str, str],
    cancel_event: threading.Event | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run in a worker thread; cancellation settles the owned process group."""
    if cancel_event is not None and cancel_event.is_set():
        raise CliRunCancelled("CLI app execution was cancelled")
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdout=stdout,
            stderr=stderr,
            start_new_session=os.name == "posix",
        )
        deadline = time.monotonic() + timeout
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise CliRunCancelled("CLI app execution was cancelled")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(argv, timeout)
                try:
                    process.wait(timeout=min(0.05, remaining))
                    break
                except subprocess.TimeoutExpired:
                    pass
            return subprocess.CompletedProcess(
                argv, process.returncode, _read_output(stdout), _read_output(stderr)
            )
        except BaseException:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                elif process.poll() is None:
                    process.kill()
            except ProcessLookupError:
                pass
            process.wait()
            raise
