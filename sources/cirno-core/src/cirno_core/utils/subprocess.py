"""Reap a stopped subprocess without retaining or blocking on unread output."""

from __future__ import annotations

import asyncio
import os
import signal

from cirno_core.utils.cancellation import shield_and_drain


async def kill_and_drain(process: asyncio.subprocess.Process, *, process_group: bool = False) -> None:
    """Call after the process's existing pipe readers have stopped.

    Killing a child alone does not unblock wait() when its pipe transports are
    paused on full buffers. Drain both pipes in bounded chunks while reaping it.
    """
    if process_group:
        # Only callers that created a new POSIX session may request this. A
        # proxy can retain the pipes even after the SSH process itself exits.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass  # The child exited before the signal reached it.

    async def discard(stream: asyncio.StreamReader | None) -> None:
        if stream is not None:
            while await stream.read(65536):
                pass

    async def settle() -> None:
        await asyncio.gather(discard(process.stdout), discard(process.stderr), process.wait())

    await shield_and_drain(settle())
