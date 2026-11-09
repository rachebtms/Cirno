"""FIFO guidance injection and bounded waits for child results."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from cirno_core.agent.execution.scope import _prompt_scope_metadata
from cirno_core.agent.goals.permission import GoalInputScope
from cirno_core.agent.tools.context import (
    RequestContext,
)
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.bus.events import (
    InboundMessage,
)
from cirno_core.bus.input_origin import origin_context
from cirno_core.runtime.context import (
    RUNTIME_CONTEXT_MESSAGE_META,
    RuntimeContextBlock,
    append_runtime_context,
)
from cirno_core.security.workspace_access import WorkspaceScope
from cirno_core.session.history_visibility import HIDDEN_HISTORY_META
from cirno_core.session.model import Session
from cirno_core.session.recovery.contracts import PENDING_FOLLOWUP_ID_KEY
from cirno_core.utils.document import reference_non_image_attachments
from cirno_core.utils.llm_runtime import LLMRuntime
from loguru import logger

if TYPE_CHECKING:
    from cirno_core.agent.loop import AgentLoop

_SUBAGENT_TERMINAL_WAIT_SECONDS = 300.0


class PendingInputInjector:
    def __init__(
        self,
        agent: AgentLoop,
        *,
        session: Session | None,
        queue: asyncio.Queue[InboundMessage] | None,
        runtime: LLMRuntime,
        request: RequestContext,
        scope: WorkspaceScope,
        tools: ToolRegistry,
        goal_inputs: GoalInputScope,
    ):
        self.agent = agent
        self.session = session
        self.queue = queue
        self.runtime = runtime
        self.request = request
        self.scope = scope
        self.tools = tools
        self.goal_inputs = goal_inputs
        self.session_key = session.key if session else request.session_key
        self.deadline: float | None = None

    async def to_user_message(self, pending_msg: InboundMessage) -> dict[str, Any]:
        content = pending_msg.content
        image_paths = pending_msg.media if pending_msg.media else None
        if image_paths:
            content, image_paths = reference_non_image_attachments(
                content,
                image_paths,
            )
            image_paths = image_paths or None
        user_content = self.agent.context.build_user_content(
            content,
            image_paths=image_paths,
        )
        row: dict[str, Any] = {
            "role": pending_msg.input_role or "user",
            "content": user_content,
            "_meta": self.agent.inputs.history_extra(pending_msg),
        }
        if HIDDEN_HISTORY_META in pending_msg.metadata:
            row[HIDDEN_HISTORY_META] = pending_msg.metadata[HIDDEN_HISTORY_META]
        metadata_value = cast(object, pending_msg.metadata)
        metadata = pending_msg.metadata if isinstance(metadata_value, dict) else {}
        blocks: list[RuntimeContextBlock] = []
        if pending_msg.is_user_input:
            scope = await self.agent.runner.prepare_prompt(
                self.agent.workspace_scopes.for_turn,
                channel=pending_msg.channel,
                message_metadata=_prompt_scope_metadata(metadata),
                session_metadata=_prompt_scope_metadata(self.session.metadata)
                if self.session is not None
                else None,
            )
            pending_request = RequestContext(
                channel=pending_msg.channel,
                chat_id=pending_msg.chat_id,
                message_id=metadata.get("message_id"),
                session_key=self.session_key,
                session_generation=self.session.generation if self.session is not None else None,
                original_user_text=pending_msg.content,
                runtime=self.runtime,
                metadata=dict(metadata),
                attributes=dict(self.request.attributes),
                sender_id=pending_msg.sender_id,
                turn_id=self.request.turn_id,
                workspace=scope.project_path,
                # Injected input continues the active run's tool policy.
                workspace_scope=self.scope,
                log_content=self.request.log_content,
            )
            blocks = await self.agent.inputs.resolve_request_context(
                pending_request,
                self.tools,
            )
        if source_block := origin_context(pending_msg):
            blocks.insert(0, source_block)
        row["content"], runtime_marker = append_runtime_context(user_content, blocks)
        if runtime_marker is not None:
            row["_meta"][RUNTIME_CONTEXT_MESSAGE_META] = runtime_marker
        if (
            pending_msg.sender_id == "subagent"
            and metadata.get("injected_event") == "subagent_result"
        ):
            subagent_marker: dict[str, Any] = {"kind": "subagent_result"}
            task_id = metadata.get("subagent_task_id")
            if isinstance(task_id, str) and task_id:
                subagent_marker["subagent_task_id"] = task_id
                row["subagent_task_id"] = task_id
            row[HIDDEN_HISTORY_META] = subagent_marker
            row["injected_event"] = "subagent_result"
        followup_id = metadata.get(PENDING_FOLLOWUP_ID_KEY)
        if isinstance(followup_id, str) and followup_id:
            row[PENDING_FOLLOWUP_ID_KEY] = followup_id
        return row

    async def drain(
        self,
        *,
        first_msg: InboundMessage | None = None,
    ) -> list[dict[str, Any]]:
        """Drain one atomic snapshot of messages already available."""
        if self.queue is None:
            return []

        # Capture the boundary before converting any message. Conversion
        # resolves runtime context and may await, so reading until QueueEmpty
        # afterwards would let later arrivals leak into this model step.
        pending_messages: list[InboundMessage] = []
        if first_msg is not None:
            pending_messages.append(first_msg)
        snapshot_size = self.queue.qsize()
        for _ in range(snapshot_size):
            try:
                pending_messages.append(self.queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        from cirno_core.runtime.heartbeat import discard_paused_heartbeat

        consumed = 0
        try:
            converted: list[dict[str, Any]] = []
            pending_messages = [msg for msg in pending_messages if not await discard_paused_heartbeat(self.agent.sessions, msg)]
            for pending_msg in pending_messages:
                # Independent turns are FIFO barriers. Their worker path
                # owns completion, command dispatch, and control metadata.
                if not self.agent.dispatch.can_inject(pending_msg):
                    break
                converted.append(await self.to_user_message(pending_msg))
            self.goal_inputs.consume_inputs(pending_messages[:len(converted)])
            consumed = len(converted)
            return converted
        finally:
            # Commit only a successfully converted prefix. On failure or
            # cancellation, return the whole snapshot ahead of later arrivals.
            unconsumed = pending_messages[consumed:]
            if unconsumed:
                later = [self.queue.get_nowait() for _ in range(self.queue.qsize())]
                for pending_msg in [*unconsumed, *later]:
                    self.queue.put_nowait(pending_msg)

    async def wait(self) -> list[dict[str, Any]]:
        """Wait for a pending result only when the runner is ready to exit."""

        items = await self.drain()
        if (
            items
            or self.queue is None
            or self.session is None
            or self.agent.subagents.get_running_count_by_session(self.session.key) == 0
        ):
            return items

        now = asyncio.get_running_loop().time()
        if self.deadline is None:
            self.deadline = now + _SUBAGENT_TERMINAL_WAIT_SECONDS
        remaining = self.deadline - now
        if remaining <= 0:
            return []

        try:
            msg = await asyncio.wait_for(self.queue.get(), timeout=remaining)
        except asyncio.TimeoutError:
            logger.warning(
                "Timeout waiting for sub-agent completion before session {} exits",
                self.session.key,
            )
            return []

        return await self.drain(first_msg=msg)
