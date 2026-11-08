"""One task owns its outcome, inbox and process cleanup until settlement."""

from __future__ import annotations

import asyncio
import time
from copy import deepcopy
from dataclasses import dataclass, field, replace

from cirno_core.agent.subagents.contracts import SubagentOrigin, SubagentOutcome
from cirno_core.agent.subagents.status import SubagentStatus
from cirno_core.processes.sessions import ExecSessionManager
from cirno_core.security.workspace_access import WorkspaceScope
from cirno_core.session.model import Session
from cirno_core.utils.llm_runtime import LLMRuntime


@dataclass(slots=True)
class SubagentTask:
    """Own one execution, its inbox, and resources until cleanup succeeds."""

    status: SubagentStatus
    session: Session
    runtime: LLMRuntime
    origin: SubagentOrigin
    origin_message_id: str | None = None
    workspace_scope: WorkspaceScope | None = None
    announce: bool = True
    begun: bool = False
    suppress_notice: bool = False
    inbox: list[tuple[str, str]] = field(default_factory=list)
    outcome: SubagentOutcome | None = None
    exec_manager: ExecSessionManager = field(default_factory=ExecSessionManager)
    cleanup_task: asyncio.Task[int] | None = None

    def raise_if_stopping(self) -> None:
        if self.outcome is not None:
            raise asyncio.CancelledError

    def decide(self, outcome: SubagentOutcome) -> bool:
        """Seal execution once, before cancellation or cleanup can yield."""
        if self.outcome is not None:
            return False
        self.outcome = outcome
        self.status.state = self.status.phase = "stopping"
        return True

    def finish(self, max_chars: int, cleanup_error: str | None = None) -> SubagentOutcome:
        execution_outcome = self.outcome
        if execution_outcome is None:
            raise RuntimeError("cannot finish a task before execution has an outcome")
        outcome = execution_outcome
        if cleanup_error is not None:
            outcome = SubagentOutcome("error", cleanup_error, "error", cleanup_error)
        status = self.status
        has_partial_result = outcome.state != "done" and bool(status.result)
        if outcome.state != "done" and status.result:
            outcome = replace(outcome, result=status.result)
        status.state = status.phase = outcome.state
        status.finished_at = time.monotonic()
        status.completed_at = time.time()
        status.result = outcome.result[:max_chars]
        status.partial = has_partial_result
        status.stop_reason = outcome.stop_reason
        status.error = outcome.error[:max_chars] if outcome.error else None
        status.task_description = status.task_description[:max_chars]
        status.label = status.label[:256]
        status.tool_events = []
        for message_id, _ in self.inbox:
            status.receipts[message_id] = "undelivered"
        self.inbox.clear()
        # Failed cleanup can retain this task after its public status is evicted.
        self.outcome = replace(
            execution_outcome,
            result=execution_outcome.result[:max_chars],
            error=execution_outcome.error[:max_chars] if execution_outcome.error else None,
        )
        return outcome

    def snapshot(self) -> SubagentStatus:
        return deepcopy(self.status)
