"""Process-tree ownership, termination and child reaping."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
from contextlib import suppress
from typing import Protocol, cast

from cirno_core.processes import platform

PROCESS_TREE_OWNER_ATTR = "_cirno_process_tree_owner"


class ProcessTreeOwner(Protocol):
    creation_flags: int

    def assign_and_resume(self, pid: int) -> None: ...

    def release(self) -> None: ...

    def terminate(self) -> None: ...


def reap_pid(pid: int) -> None:
    """Reap completed POSIX children without blocking; report unexpected OS errors."""
    waitpid = getattr(os, "waitpid", None)
    wnohang = getattr(os, "WNOHANG", None)
    if waitpid is None or wnohang is None:
        return
    try:
        waitpid(pid, wnohang)
    except (ProcessLookupError, ChildProcessError):
        # Already reaped, or not our child — both are fine.
        pass


async def kill_process(process: asyncio.subprocess.Process) -> None:
    """Kill a subprocess and reap it to prevent zombies.

    Safe to call when the process has already exited (e.g. generic
    exception handlers after a successful ``communicate()``): skips
    ``kill()`` and only runs the safety-net reap.
    """
    if process.returncode is not None:
        reap_pid(process.pid)
        return
    try:
        with suppress(ProcessLookupError):
            process.kill()
        await asyncio.wait_for(process.wait(), timeout=5.0)
    finally:
        reap_pid(process.pid)


async def kill_process_tree(process: asyncio.subprocess.Process) -> None:
    """Kill a session process and descendants, then reap the root process."""
    owner = process_tree_owner(process)
    tree_error: Exception | None = None
    try:
        if owner is not None:
            owner.terminate()
        elif platform.IS_WINDOWS:
            if process.returncode is None:
                try:
                    await asyncio.to_thread(
                        subprocess.run,
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        check=True,
                        timeout=5.0,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except (OSError, subprocess.SubprocessError) as exc:
                    tree_error = exc
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
        await asyncio.wait_for(process.wait(), timeout=5.0)
        if owner is not None:
            drop_process_tree_owner(process)
        if tree_error is not None:
            raise RuntimeError(
                f"Failed to terminate process tree {process.pid}: {tree_error}"
            ) from tree_error
    finally:
        reap_pid(process.pid)


def process_tree_owner(
    process: asyncio.subprocess.Process,
) -> ProcessTreeOwner | None:
    # spawn_process is the only writer for this ownership marker.
    return cast(ProcessTreeOwner | None, vars(process).get(PROCESS_TREE_OWNER_ATTR))


def create_windows_job() -> ProcessTreeOwner:
    from cirno_core.processes.windows_job import WindowsJob

    return WindowsJob.create()


def drop_process_tree_owner(process: asyncio.subprocess.Process) -> None:
    with suppress(AttributeError):
        delattr(process, PROCESS_TREE_OWNER_ATTR)


def release_process_tree(process: asyncio.subprocess.Process) -> None:
    owner = process_tree_owner(process)
    if owner is None:
        return
    owner.release()
    drop_process_tree_owner(process)
