"""Foreground shutdown signals and ordered runtime resource settlement."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable
from contextlib import suppress
from typing import Any, Protocol

from loguru import logger


class RuntimeResource(Protocol):
    async def aclose(self) -> None: ...


class RuntimeChannels(Protocol):
    async def stop_all(self) -> None: ...


def _signal_name(signum: int) -> str:
    with suppress(ValueError):
        return signal.Signals(signum).name
    return f"signal {signum}"


def install_shutdown_handlers(
    loop: asyncio.AbstractEventLoop,
    shutdown_event: asyncio.Event,
    tasks: list[asyncio.Task[Any]],
    print_status: Callable[[str], None],
) -> Callable[[], None]:
    """Install foreground server signal handlers and return a restore callback."""
    loop_signals: list[int] = []
    previous_handlers: list[tuple[int, Any]] = []
    shutdown_requested = False

    def request_shutdown(signum: int) -> None:
        nonlocal shutdown_requested
        sig_name = _signal_name(signum)
        if shutdown_requested:
            logger.warning("Forcing server shutdown after repeated {}", sig_name)
            for task in tasks:
                if not task.done():
                    task.cancel()
            return
        shutdown_requested = True
        logger.info("Server shutdown requested by {}", sig_name)
        print_status("\nShutting down... Press Ctrl+C again to force.")
        shutdown_event.set()

    shutdown_signals = [signal.SIGINT, signal.SIGTERM]
    if sigbreak := getattr(signal, "SIGBREAK", None):
        shutdown_signals.append(sigbreak)

    for signum in shutdown_signals:
        try:
            loop.add_signal_handler(signum, request_shutdown, signum)
        except (NotImplementedError, RuntimeError, ValueError):
            try:
                previous = signal.getsignal(signum)
                signal.signal(signum, lambda sig, _frame: request_shutdown(sig))
            except (RuntimeError, ValueError):
                logger.debug("Could not install server handler for {}", _signal_name(signum))
                continue
            previous_handlers.append((signum, previous))
        else:
            loop_signals.append(signum)

    def restore() -> None:
        for signum in loop_signals:
            with suppress(NotImplementedError, RuntimeError, ValueError):
                loop.remove_signal_handler(signum)
        for signum, handler in previous_handlers:
            with suppress(RuntimeError, ValueError):
                signal.signal(signum, handler)

    return restore


async def close_runtime(
    agent: RuntimeResource,
    mcp_provider: RuntimeResource,
    channels: RuntimeChannels,
    tasks: list[asyncio.Task[Any]],
    runtime_tasks: asyncio.Future[list[Any]] | None,
    *,
    task_wait_timeout: float = 15.0,
    close_timeout: float = 15.0,
) -> None:
    """Cancel runtime tasks, then deterministically close application resources.

    Order matters: runtime tasks (including the agent loop and any in-flight
    turn) are cancelled and awaited -- bounded -- before the loop-owned resources
    and the application-owned MCP provider are torn down. The final close is
    bounded and idempotent, so it also covers a cancelled or incomplete loop
    cleanup without leaving subprocess transports alive past ``loop.close()``.
    """
    # Some SDKs swallow task cancellation while attempting to reconnect.
    # Close channel transports before waiting for their runners to exit.
    failures: list[BaseException] = []
    try:
        await asyncio.wait_for(channels.stop_all(), timeout=close_timeout)
    except BaseException as exc:
        exc.add_note("Stopping application channels")
        failures.append(exc)
    for task in tasks:
        if not task.done():
            task.cancel()
    pending: set[asyncio.Task[Any]] = set()
    if tasks:
        # Bounded: a coroutine that swallows cancellation (e.g. an SDK reconnect
        # loop) must not hold the stop open until systemd's timeout kills the
        # cgroup. Anything still pending is abandoned and closed underneath.
        _done, pending = await asyncio.wait(tasks, timeout=task_wait_timeout)
        # A task can swallow the first cancellation while unwinding. Re-cancel
        # timed-out tasks so an agent loop stuck draining background work reaches
        # its resource-cleanup phase before the explicit final close below.
        for task in pending:
            task.cancel()
    if runtime_tasks is not None and not runtime_tasks.done():
        runtime_tasks.cancel()
    for label, close in (
        ("agent", agent.aclose),
        ("MCP provider", mcp_provider.aclose),
    ):
        try:
            await asyncio.wait_for(close(), timeout=close_timeout)
        except BaseException as exc:
            exc.add_note(f"Closing {label}")
            failures.append(exc)
    # Retrieving an already-finished gather prevents noisy unhandled exceptions,
    # but never wait for it here: its children were bounded individually above.
    if runtime_tasks is not None and runtime_tasks.done():
        try:
            await runtime_tasks
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            failures.append(exc)
    if failures:
        raise BaseExceptionGroup("Cirno shutdown failed", failures)
