"""AgentLifecycle for conversation admission and resource lifetime."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Coroutine
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any

from cirno_core.runtime.admission import RuntimeMaintenanceError
from cirno_core.session.state import SessionOperationQueueFullError
from cirno_core.utils.cancellation import task_is_cancelling
from loguru import logger

if TYPE_CHECKING:
    from cirno_core.agent.loop import AgentLoop


class AgentLifecycle:
    def __init__(self, agent: AgentLoop):
        self.agent = agent

    async def expire_sessions(self) -> None:
        """Scan idle sessions without blocking the event loop."""
        if self.agent.bus.admission.paused:
            return
        now = time.monotonic()
        if now < self.agent._next_idle_compact_check_at:
            return
        self.agent._next_idle_compact_check_at = now + self.agent._idle_compact_check_interval_s
        try:
            with self.agent.bus.admission.activity():
                await self.agent.auto_compact.check_expired(
                    self.schedule_background,
                    self.agent.runtime_for_session,
                    active_session_keys=self.agent._pending_queues.keys(),
                )
        except SessionOperationQueueFullError:
            logger.debug("Skipping idle archival while session storage is busy")

    async def run(self) -> None:
        """Run the agent loop, dispatching messages as tasks to stay responsive to /stop."""
        self.agent._running = True
        try:
            logger.info("Agent loop started")

            while self.agent._running:
                if (
                    time.monotonic() >= self.agent._next_goal_check_at
                    and not self.agent.bus.admission.paused
                    and (self.agent._goal_check_task is None or self.agent._goal_check_task.done())
                ):
                    from cirno_core.agent.goals.scheduler import wake_due_goals

                    self.agent._next_goal_check_at = time.monotonic() + 2
                    self.agent._goal_check_task = self.schedule_background(
                        wake_due_goals(self.agent)
                    )
                try:
                    # Keep dequeue and admission in this task. wait_for would
                    # dequeue in another task, leaving a false-idle handoff gap.
                    async with asyncio.timeout(1.0):
                        msg = await self.agent.bus.consume_inbound()
                except asyncio.TimeoutError:
                    await self.expire_sessions()
                    if (
                        self.agent.memory_idle_callback
                        and not self.agent._active_tasks
                        and not self.agent._background_tasks
                        and not self.agent.bus.has_pending_events
                    ):
                        await self.agent.memory_idle_callback()
                    continue
                except asyncio.CancelledError:
                    # Preserve real task cancellation so shutdown can complete cleanly.
                    # Only ignore non-task CancelledError signals that may leak from integrations.
                    if not self.agent._running or task_is_cancelling():
                        raise
                    logger.warning(
                        "Ignoring leaked CancelledError while consuming inbound messages"
                    )
                    continue
                except Exception as e:
                    logger.warning("Error consuming inbound message: {}, continuing...", e)
                    continue

                with self.agent.bus.admission.activity():
                    try:
                        await self.agent.dispatch.receive(msg)
                    except Exception as error:
                        key = self.agent.dispatch.session_key(msg)
                        await self.agent.dispatch.failed(
                            msg, error, stage="intake",
                            publish_completion=key not in self.agent._pending_queues,
                        )
        finally:
            await self.aclose()

    def maintenance(self) -> AbstractContextManager[None]:
        """Close task intake only when this runtime's accepted work is finished.

        The gateway shares the bus gate with cron and local trigger intake.
        This does not stop other processes or channel/configuration writes;
        those must be shut down before an updater takes a data backup.
        """
        return self.agent.bus.admission.pause_if_idle(self.has_pending_work)

    def has_pending_work(self) -> bool:
        return bool(
            self.agent.bus.inbound_size
            or self.agent._pending_queues
            or self.agent._deferred_automation_turns
            or self.agent.bus.has_pending_events
            or self.agent._active_tasks
            or self.agent._background_tasks
            or self.agent._close_lock.locked()
            or self.agent.subagents.has_pending_work
            or self.agent._exec_session_manager.has_pending_work
        )

    def preserve_inflight_turns_on_shutdown(self) -> None:
        """Keep durable checkpoints when the owning gateway exits.

        Normal cancellation intentionally materializes partial output so a
        user-stopped turn leaves a readable conversation.  Server lifecycle
        shutdown is different: RecoveryCoordinator needs the checkpoint intact
        to safely offer the unfinished turn for explicit continuation later.
        """
        self.agent._preserve_inflight_turns_on_shutdown = True

    async def aclose(self) -> None:
        """Stop active work, then close resources owned by the agent loop.

        Resource teardown must still run if cancellation interrupts task draining.
        Server shutdown deliberately bounds this coroutine, so keeping the cleanup
        phase in ``finally`` prevents a timed-out background task from leaving
        subprocess transports alive after the event loop closes.
        """
        # The loop closes itself from ``run()`` while application shutdown also
        # performs a guaranteed final close. Serialize those owners so they cannot
        # tear down the same resources concurrently.
        close_lock = getattr(self.agent, "_close_lock", None)
        if close_lock is None:
            close_lock = self.agent._close_lock = asyncio.Lock()
        async with close_lock:
            await self.close_resources()

    async def close_resources(self) -> None:
        errors: list[BaseException] = []
        active_task_groups = getattr(self.agent, "_active_tasks", {})
        current_task = asyncio.current_task()
        pending_queues = {
            key: self.agent._pending_queues[key]
            for key, tasks in active_task_groups.items()
            if key in self.agent._pending_queues and any(task is not current_task for task in tasks)
        }
        active_tasks = tuple({task for tasks in active_task_groups.values() for task in tasks})
        active_task_groups.clear()
        active_tasks = tuple(task for task in active_tasks if task is not current_task)
        for task in active_tasks:
            if not task.done():
                task.cancel()
        try:
            if active_tasks:
                await asyncio.gather(*active_tasks, return_exceptions=True)
            for key, pending in pending_queues.items():
                if self.agent._pending_queues.get(key) is pending:
                    self.agent._pending_queues.pop(key)
                    await self.agent.dispatch.cancel_pending(key, pending, asyncio.CancelledError())
            if self.agent._background_tasks:
                await asyncio.gather(*self.agent._background_tasks, return_exceptions=True)
        except BaseException as exc:
            errors.append(exc)
        finally:
            self.agent._background_tasks.clear()

        cleanup_steps = (
            self.agent.subagents.close,
            self.agent._exec_session_manager.close_all,
            self.agent.runtime_resolver.aclose,
            self.agent.sessions.state.aclose,
        )
        for cleanup in cleanup_steps:
            try:
                await cleanup()
            except BaseException as exc:
                errors.append(exc)
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise BaseExceptionGroup("failed to close agent resources", errors)

    def background_done(self, task: asyncio.Task[Any]) -> None:
        self.agent._background_tasks.discard(task)
        if task.cancelled():
            return
        exception = task.exception()
        if exception is not None:
            logger.opt(exception=exception).error(
                "Background task '{}' failed",
                task.get_name(),
            )

    def schedule_background(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        """Schedule a coroutine as a tracked background task (drained on shutdown)."""
        try:
            self.agent.bus.admission.check()
        except RuntimeMaintenanceError:
            coro.close()
            raise
        task = asyncio.create_task(coro)
        self.agent._background_tasks.add(task)
        task.add_done_callback(self.background_done)
        return task

    def stop(self) -> None:
        """Stop the agent loop."""
        self.agent._running = False
        logger.info("Agent loop stopping")
