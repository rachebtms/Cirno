"""Subagent manager for background task execution."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Mapping
from copy import deepcopy
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, cast

from cirno_usage.context import current_llm_usage_source
from loguru import logger

from cirno_core.agent.subagents.contracts import (
    SubagentControlError,
    SubagentLimits,
    SubagentMessageReceipt,
    SubagentOutcome,
)
from cirno_core.agent.subagents.execution import SubagentExecution
from cirno_core.agent.subagents.reports import SubagentReports
from cirno_core.agent.subagents.sessions import SubagentSessions
from cirno_core.agent.subagents.status import SubagentStatus
from cirno_core.agent.subagents.task import SubagentTask
from cirno_core.agent.subagents.tools import SubagentTools
from cirno_core.agent.tools.base import ToolResult
from cirno_core.bus.events import InboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.bus.runtime_events import RuntimeEventContext, SubagentTaskChanged
from cirno_core.config.agents import AgentDefaults
from cirno_core.config.network import NetworkConfig
from cirno_core.config.tools import ToolsConfig
from cirno_core.security.workspace_access import (
    WorkspaceScope,
)
from cirno_core.session.manager import SessionManager
from cirno_core.session.model import Session, SessionPolicy
from cirno_core.utils.cancellation import shield_and_drain
from cirno_core.utils.llm_runtime import LLMRuntime

if TYPE_CHECKING:
    from cirno_core.memory.consolidation import Consolidator


class SubagentManager:
    """Manages background subagent execution."""

    def __init__(
        self,
        workspace: Path,
        bus: MessageBus,
        max_tool_result_chars: int,
        tools_config: ToolsConfig | None = None,
        restrict_to_workspace: bool = False,
        disabled_skills: list[str] | None = None,
        always_skills: list[str] | None = None,
        max_iterations: int | None = None,
        max_concurrent_subagents: int | None = None,
        *,
        consolidator: Consolidator,
        network_config: NetworkConfig | None = None,
        session_manager: SessionManager | None = None,
    ):
        if cast(object, consolidator) is None:
            raise TypeError("SubagentManager requires a consolidator")
        defaults = AgentDefaults()
        self.bus = bus
        self.limits = SubagentLimits(
            max_iterations if max_iterations is not None else defaults.max_tool_iterations,
            max_tool_result_chars,
        )
        self.tools = SubagentTools(
            workspace, tools_config or ToolsConfig(), network_config or NetworkConfig(),
            restrict_to_workspace, set(disabled_skills or []), set(always_skills or []),
        )
        self.max_concurrent_subagents = (
            max_concurrent_subagents
            if max_concurrent_subagents is not None
            else defaults.max_concurrent_subagents
        )
        self._run_slots = asyncio.Semaphore(self.max_concurrent_subagents)
        self._running_tasks: dict[str, asyncio.Task[str]] = {}
        self._tasks: dict[str, SubagentTask] = {}
        self._terminal_statuses: dict[str, SubagentStatus] = {}
        self._closed = False
        self._admitting = 0
        self.sessions = SubagentSessions(session_manager) if session_manager is not None else None
        self.reports = SubagentReports(bus, self.sessions)
        self.execution = SubagentExecution(
            self.tools, self.limits, consolidator, save_transcript=self._save_transcript,
            save_status=self._save_status, drain_inbox=self._drain_inbox,
        )

    MAX_ACTIVE = 128
    MAX_TERMINAL = 128
    MAX_INBOX = 16
    MAX_MESSAGES = 128
    MAX_MESSAGE_BYTES = 8192

    CANCEL_WAIT_SECONDS = 5.0

    async def _save_status(
        self, status: SubagentStatus,
    ) -> None:
        status.revision += 1
        if self.sessions is not None and not await self.sessions.save(status):
            return
        self._publish_status(status)

    def _publish_status(self, status: SubagentStatus) -> None:
        origin = self._tasks[status.task_id].origin
        self.bus.publish_nowait(SubagentTaskChanged(
            context=RuntimeEventContext(
                channel=origin["channel"], chat_id=origin["chat_id"], session_key=status.owner,
            ),
            task_id=status.task_id,
        ))

    async def recover_interrupted(self) -> None:
        """Recover observations only after the host has claimed execution ownership."""
        if self.sessions is not None:
            await self.sessions.interrupt_pending()

    def _start_cleanup(self, record: SubagentTask, *, retry: bool = False) -> asyncio.Task[int]:
        cleanup = record.cleanup_task
        if retry and cleanup is not None and cleanup.done():
            record.cleanup_task = None
        if record.cleanup_task is None:
            record.cleanup_task = asyncio.create_task(record.exec_manager.close_all())
            record.cleanup_task.add_done_callback(partial(self._cleanup_done, record))
        return record.cleanup_task

    def _cleanup_done(self, record: SubagentTask, task: asyncio.Task[int]) -> None:
        if not task.cancelled() and task.exception() is None:
            self._release_task(record)

    def _release_task(self, record: SubagentTask) -> None:
        cleanup = record.cleanup_task
        if (record.status.finished_at is not None
                and record.status.task_id not in self._running_tasks
                and cleanup is not None and cleanup.done()
                and not cleanup.cancelled() and cleanup.exception() is None):
            self._tasks.pop(record.status.task_id, None)

    async def _finish(self, record: SubagentTask,
                cleanup_error: str | None = None) -> SubagentOutcome:
        outcome = record.finish(self.limits.max_tool_result_chars, cleanup_error)
        await self._save_transcript(record)
        await self._save_status(record.status)
        self._terminal_statuses[record.status.task_id] = record.snapshot()
        while len(self._terminal_statuses) > self.MAX_TERMINAL:
            del self._terminal_statuses[next(iter(self._terminal_statuses))]
        return outcome

    async def _drain_inbox(self, record: SubagentTask) -> list[dict[str, str]]:
        record.raise_if_stopping()
        snapshot, record.inbox = record.inbox, []
        for message_id, _ in snapshot:
            record.status.receipts[message_id] = "delivered"
        if snapshot:
            await self._save_status(record.status)
        return [{"role": "user", "content": content} for _, content in snapshot]

    def _owned_status(self, task_id: str, owner: str | None) -> SubagentStatus:
        status = self._terminal_statuses.get(task_id)
        record = self._tasks.get(task_id)
        if status is None and record is not None and record.status.finished_at is None:
            status = record.status
        if self.sessions is not None and owner:
            if not self.sessions.exists(owner) or not self.sessions.contains(task_id, owner):
                raise SubagentControlError("task unavailable")
            if status is None:
                status = self.sessions.status(task_id, owner)
        if not owner or status is None or status.owner != owner:
            raise SubagentControlError("task unavailable")
        return status

    def check(self, task_id: str, owner: str | None) -> SubagentStatus:
        """Return detached status for one task owned by the caller's session."""
        return deepcopy(self._owned_status(task_id, owner))

    def accepts_result(self, msg: InboundMessage, owner: str) -> bool:
        """Reject a completion whose owning child was removed after publication."""
        task_id = msg.metadata.get("subagent_task_id")
        if msg.sender_id != "subagent" or not isinstance(task_id, str) or self.sessions is None:
            return True
        return self.sessions.contains(task_id, owner)

    def read_session(self, task_id: str, owner: str) -> tuple[SubagentStatus, Session]:
        """Return task status and detached history through the ownership boundary."""
        status = self.check(task_id, owner)
        child = self.sessions.snapshot(task_id, owner) if self.sessions is not None else None
        if child is None:
            raise SubagentControlError("task unavailable")
        return status, child

    async def send(self, task_id: str, owner: str | None,
             message: str | None) -> SubagentMessageReceipt:
        """Accept a bounded follow-up only while execution is open."""
        status = self._owned_status(task_id, owner)
        if status.state not in {"queued", "running"}:
            raise SubagentControlError("task is not accepting messages")
        if not message or not message.strip() or len(message.encode("utf-8")) > self.MAX_MESSAGE_BYTES:
            raise SubagentControlError("message must contain text and be at most 8192 UTF-8 bytes")
        record = self._tasks[task_id]
        if len(record.inbox) >= self.MAX_INBOX or len(status.receipts) >= self.MAX_MESSAGES:
            raise SubagentControlError("task message capacity reached")
        message_id = str(uuid.uuid4())
        record.inbox.append((message_id, message))
        status.receipts[message_id] = "accepted"
        await self._save_status(status)
        return {"task_id": task_id, "message_id": message_id,
                "receipt": "accepted", "delivered": False}

    async def cancel(self, task_id: str, owner: str | None) -> SubagentStatus:
        """Stop an owned task and return its detached state after the bounded wait."""
        status = self._owned_status(task_id, owner)
        record = self._tasks.get(task_id)
        if record is not None and record.status.finished_at is None:
            await self._cancel_task(record)
            status = record.status
        return deepcopy(status)

    async def _cancel_task(self, record: SubagentTask,
                           *, suppress_notice: bool = False) -> None:
        record.suppress_notice |= suppress_notice
        task_id = record.status.task_id
        task = self._running_tasks.get(task_id)
        decided = record.decide(SubagentOutcome("cancelled", "Task cancelled.", "cancelled"))
        try:
            if decided:
                await self._save_status(record.status)
        finally:
            if decided and task is not None and record.begun and not task.done():
                task.cancel()
            if record.status.finished_at is None:
                self._start_cleanup(record)
            if task is not None:
                # Keep resistant work tracked, with its slot held, until it exits.
                await asyncio.wait({task}, timeout=self.CANCEL_WAIT_SECONDS)

    def runtime_statuses(self) -> Mapping[str, SubagentStatus]:
        """Return detached active and retained terminal data, never task resources."""
        return {
            **{tid: record.snapshot() for tid, record in self._tasks.items()
               if record.status.finished_at is None},
            **deepcopy(self._terminal_statuses),
        }

    def _runtime_statuses_for_session(self, session_key: str) -> dict[str, SubagentStatus]:
        return {
            **{tid: record.snapshot() for tid, record in self._tasks.items()
               if record.status.owner == session_key and record.status.finished_at is None},
            **{tid: deepcopy(status) for tid, status in self._terminal_statuses.items()
               if status.owner == session_key},
        }

    def _merge_session_statuses(
        self, session_key: str, runtime: Mapping[str, SubagentStatus], *, include_history: bool,
    ) -> Mapping[str, SubagentStatus]:
        if self.sessions is not None and not self.sessions.exists(session_key):
            return {}
        statuses = self.sessions.load(session_key) if include_history and self.sessions is not None else {}
        for task_id, status in runtime.items():
            if self.sessions is not None and not self.sessions.contains(task_id, session_key):
                continue
            persisted = statuses.get(task_id)
            if persisted is None or status.revision >= persisted.revision:
                statuses[task_id] = status
        return statuses

    def statuses_for_session(
        self, session_key: str | None, *, include_history: bool = True,
    ) -> Mapping[str, SubagentStatus]:
        """Return only tasks owned by the given session, never a global fallback."""
        if not session_key:
            return {}
        return self._merge_session_statuses(
            session_key, self._runtime_statuses_for_session(session_key), include_history=include_history,
        )

    async def read_statuses_for_session(self, session_key: str) -> Mapping[str, SubagentStatus]:
        """Capture runtime observations on the owner loop; read stored metadata on a worker."""
        runtime = self._runtime_statuses_for_session(session_key)
        return await asyncio.to_thread(
            self._merge_session_statuses, session_key, runtime, include_history=True,
        )


    async def _create_task(
        self, task: str, label: str | None, origin_channel: str, origin_chat_id: str,
        session_key: str | None, origin_message_id: str | None,
        temperature: float | None, workspace_scope: WorkspaceScope | None,
        runtime: LLMRuntime, *, announce: bool, origin_turn_id: str | None,
        session_policy: SessionPolicy | None,
    ) -> SubagentTask:
        self.bus.admission.check()
        if temperature is not None:
            runtime = runtime.with_generation_overrides(temperature=temperature)
        # A failed cleanup owns admission even after its status has been evicted.
        if self._closed or len(self._tasks) + self._admitting >= self.MAX_ACTIVE:
            raise SubagentControlError("subagent manager is closed or at task capacity")
        owner = session_key or f"{origin_channel}:{origin_chat_id}"
        task_id = str(uuid.uuid4())
        status = SubagentStatus(
            task_id=task_id,
            revision=1,
            label=label or task[:30] + ("..." if len(task) > 30 else ""),
            task_description=task,
            started_at=time.monotonic(),
            owner=owner,
            origin_message_id=origin_message_id,
            origin_turn_id=origin_turn_id,
        )
        self._admitting += 1
        try:
            if self.sessions is not None:
                admission = asyncio.create_task(self.sessions.create(status, policy=session_policy))
                try:
                    child = await shield_and_drain(admission)
                except asyncio.CancelledError:
                    if not admission.cancelled() and admission.exception() is None:
                        child = admission.result()
                        await shield_and_drain(self.sessions.sessions.state.delete(
                            child.key, expected_generation=child.generation,
                        ))
                    raise
            else:
                child = Session(key=SubagentSessions.key(task_id), policy=session_policy or SessionPolicy())
                child.add_message("user", task)
        finally:
            self._admitting -= 1
        if self._closed:
            if self.sessions is not None:
                await self.sessions.sessions.state.delete(child.key, expected_generation=child.generation)
            raise SubagentControlError("subagent manager is closed")
        record = SubagentTask(
            status=status,
            session=child,
            runtime=runtime,
            origin={
                "channel": origin_channel, "chat_id": origin_chat_id,
                "session_key": owner, "llm_usage_source": current_llm_usage_source(),
            },
            origin_message_id=origin_message_id,
            workspace_scope=workspace_scope,
            announce=announce,
        )
        self._tasks[task_id] = record
        self._publish_status(status)
        execution = asyncio.create_task(self._run_subagent(record))
        self._running_tasks[task_id] = execution
        execution.add_done_callback(partial(self._task_done, record))
        logger.info("Started subagent [{}]: {}", task_id,
                    record.status.label if child.policy.log_content else "[content hidden]")
        return record

    async def spawn(
        self,
        task: str,
        label: str | None = None,
        origin_channel: str = "cli",
        origin_chat_id: str = "direct",
        session_key: str | None = None,
        origin_message_id: str | None = None,
        temperature: float | None = None,
        workspace_scope: WorkspaceScope | None = None,
        *,
        runtime: LLMRuntime,
        origin_turn_id: str | None = None,
        session_policy: SessionPolicy | None = None,
    ) -> str:
        """Start background work and route its terminal result to the parent."""
        try:
            record = await self._create_task(
                task, label, origin_channel, origin_chat_id, session_key,
                origin_message_id, temperature, workspace_scope, runtime, announce=True, origin_turn_id=origin_turn_id,
                session_policy=session_policy,
            )
        except SubagentControlError as exc:
            return ToolResult.error(f"Error: {exc}")
        status = record.status
        return f"Subagent [{status.label}] started (id: {status.task_id}). I'll notify you when it completes."

    async def run_inline(
        self,
        task: str,
        label: str | None = None,
        origin_channel: str = "cli",
        origin_chat_id: str = "direct",
        session_key: str | None = None,
        origin_message_id: str | None = None,
        temperature: float | None = None,
        workspace_scope: WorkspaceScope | None = None,
        *,
        runtime: LLMRuntime,
        origin_turn_id: str | None = None,
        session_policy: SessionPolicy | None = None,
    ) -> str:
        """Wait for the same task lifecycle without a background notice."""
        try:
            record = await self._create_task(
                task, label, origin_channel, origin_chat_id, session_key,
                origin_message_id, temperature, workspace_scope, runtime, announce=False, origin_turn_id=origin_turn_id,
                session_policy=session_policy,
            )
        except SubagentControlError as exc:
            return ToolResult.error(f"Error: {exc}")
        execution = self._running_tasks[record.status.task_id]
        try:
            result = await asyncio.shield(execution)
        except asyncio.CancelledError:
            caller = asyncio.current_task()
            if execution.cancelled() and caller is not None and not caller.cancelling():
                partial_result = record.status.result if record.status.partial else None
                return ToolResult.error(
                    "Task cancelled." + (f"\nPartial result:\n{partial_result}" if partial_result else "")
                )
            await self._cancel_task(record, suppress_notice=True)
            raise
        if record.status.state == "error":
            error = record.status.error or result
            return ToolResult.error(error + (f"\nPartial result:\n{result}" if error != result else ""))
        if record.status.state == "incomplete":
            return ToolResult.error(f"Task incomplete ({record.status.stop_reason}).\n{result}")
        return result

    def _task_done(self, record: SubagentTask, task: asyncio.Task[str]) -> None:
        self._running_tasks.pop(record.status.task_id, None)
        error = None if task.cancelled() else task.exception()
        if error is not None:
            logger.error("Subagent [{}] failed: {}", record.status.task_id,
                         error if record.session.policy.log_content else type(error).__name__)
        if record.status.finished_at is None:
            # An externally cancelled execution still owns cleanup and a terminal result.
            record.decide(
                SubagentOutcome("error", f"Error: {error}", "error", str(error))
                if error is not None
                else SubagentOutcome("cancelled", "Task cancelled.", "cancelled")
            )
            self._start_cleanup(record)
            settlement = asyncio.create_task(self._settle_unfinished_task(record))
            self._running_tasks[record.status.task_id] = settlement
            settlement.add_done_callback(partial(self._task_done, record))
        self._release_task(record)

    async def _save_transcript(self, record: SubagentTask) -> None:
        if self.sessions is not None:
            from cirno_core.session.sqlite_store import SessionConflictError

            try:
                await self.sessions.sessions.state.finish_turn(record.session)
            except SessionConflictError:
                # A removed child must not be recreated by a late observation.
                return

    async def _settle_unfinished_task(self, record: SubagentTask) -> str:
        outcome = await self._finish(record)
        return outcome.result

    async def _run_subagent(self, record: SubagentTask) -> str:
        """Execute once, seal the outcome, then clean up and publish once."""
        status = record.status
        task_text, label = status.task_description, status.label
        record.begun = True
        try:
            record.raise_if_stopping()
            async with self._run_slots:
                record.raise_if_stopping()
                status.state = "running"
                status.phase = "initializing"
                await self._save_status(status)
                outcome = await self.execution.run(record)
                record.decide(outcome)
        except asyncio.CancelledError:
            record.decide(SubagentOutcome("cancelled", "Task cancelled.", "cancelled"))
        except Exception as exc:
            logger.opt(exception=record.session.policy.log_content).error("Subagent [{}] failed", status.task_id)
            record.decide(SubagentOutcome("error", f"Error: {exc}", "error", str(exc)))
        cleanup_error = None
        try:
            await asyncio.shield(self._start_cleanup(record))
        except Exception as exc:
            logger.opt(exception=record.session.policy.log_content).error(
                "Subagent [{}] exec cleanup failed", status.task_id,
            )
            cleanup_error = f"Error cleaning up task processes: {exc}"
        outcome = await self._finish(record, cleanup_error)
        if record.announce and not record.suppress_notice and not self._closed:
            await self.reports.announce(
                status.task_id, label, task_text, outcome.result, record.origin,
                "ok" if outcome.state == "done" else outcome.state, record.origin_message_id,
                receipts=dict(status.receipts),
                stop_reason=status.stop_reason, error=status.error, partial_result=status.partial,
            )
        if outcome.state == "cancelled":
            raise asyncio.CancelledError
        return outcome.result


    async def cancel_by_session(self, session_key: str) -> int:
        """Cancel all subagents for the given session. Returns count cancelled."""
        records = [record for tid, record in self._tasks.items()
                   if record.status.owner == session_key
                   and tid in self._running_tasks and not self._running_tasks[tid].done()]
        # Suppress every notice before cancellation can yield to a sibling.
        for record in records:
            record.suppress_notice = True
        await asyncio.gather(*(self._cancel_task(record, suppress_notice=True) for record in records))
        return len(records)

    async def close(self) -> None:
        """Request cancellation and bounded cleanup, retaining unfinished work."""
        self._closed = True
        await asyncio.gather(*(self._cancel_task(self._tasks[tid], suppress_notice=True)
                               for tid in list(self._running_tasks)))
        cleanups: set[asyncio.Task[int]] = set()
        for record in list(self._tasks.values()):
            cleanup = record.cleanup_task
            retry = cleanup is not None and cleanup.done() and (
                cleanup.cancelled() or cleanup.exception() is not None
            )
            cleanups.add(self._start_cleanup(record, retry=retry))
        if not cleanups:
            return
        done, _ = await asyncio.wait(cleanups, timeout=self.CANCEL_WAIT_SECONDS)
        for task in done:
            task.result()
        if self._tasks:
            logger.warning("Subagent shutdown returned with tasks or cleanup still pending")

    def get_running_count(self) -> int:
        """Return the number of currently running subagents."""
        return len(self._running_tasks)

    @property
    def has_pending_work(self) -> bool:
        """Completed turns may still own exec cleanup, including failed cleanup."""
        return bool(self._tasks)

    def get_running_count_by_session(self, session_key: str) -> int:
        """Return the number of currently running subagents for a session."""
        return sum(
            1 for tid, task in self._running_tasks.items()
            if self._tasks[tid].status.owner == session_key and not task.done()
        )
