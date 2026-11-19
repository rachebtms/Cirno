"""Own installer subprocess groups through timeout and interruption cleanup."""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Mapping
from typing import Literal


def _stop_process_group(process: subprocess.Popen[str]) -> None:
    try:
        if os.name == "posix":
            # The leader can have exited while descendants still own work or
            # output pipes. Its original process group remains the cleanup owner.
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass


def run_command(
    arguments: list[str], *, env: Mapping[str, str], timeout: float | None,
    check: bool = False, text: Literal[True] = True, capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a command, draining the whole inherited process group on failure."""
    with subprocess.Popen(
        arguments, env=env, text=text,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        start_new_session=os.name == "posix",
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except BaseException as error:
            _stop_process_group(process)
            stdout, stderr = process.communicate()
            if isinstance(error, subprocess.TimeoutExpired):
                raise subprocess.TimeoutExpired(arguments, timeout, output=stdout, stderr=stderr) from error
            raise
        code = process.returncode
        assert code is not None
        if code:
            _stop_process_group(process)
        if check and code:
            raise subprocess.CalledProcessError(code, arguments, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(arguments, code, stdout, stderr)
