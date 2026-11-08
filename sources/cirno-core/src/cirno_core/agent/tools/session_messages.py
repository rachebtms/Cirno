"""Tools for sending bounded messages between persisted sessions."""

# pyright: reportIncompatibleMethodOverride=false

from __future__ import annotations

import asyncio
import json
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from cirno_core.agent.tools.base import Tool, ToolResult, tool_parameters
from cirno_core.agent.tools.context import RequestContext, ToolContext, current_request_context
from cirno_core.agent.tools.schema import (
    BooleanSchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from cirno_core.bus.events import InboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.runtime.context import RuntimeContextBlock
from cirno_core.session.manager import SessionManager
from cirno_core.session.session_handles import (
    SessionHandleResolver,
    session_handle_for_name,
)
from cirno_core.session.session_messages import (
    SESSION_MESSAGE_METADATA_KEY,
    SessionMessageEnvelope,
    session_message_envelope,
)
from loguru import logger

_RATE_LIMIT_WINDOW_SECONDS = 60.0
MIN_REPLY_TIMEOUT_SECONDS = 5
MAX_REPLY_TIMEOUT_SECONDS = 60


class SessionMessageError(ValueError):
    pass


class _CancelHandle(Protocol):
    def cancel(self) -> None: ...


@dataclass(slots=True)
class _PendingReply:
    timeout_seconds: int
    target_handle: str
    request: SessionMessageEnvelope
    source_generation: str
    timer: _CancelHandle | None = None


@tool_parameters(
    tool_parameters_schema(
        to=StringSchema("Target stable conversation id (preferred) or current @name from conversations.list, including the personal Router Agent."),
        content=StringSchema("Message."),
        expect_reply=BooleanSchema(description="Notify this session if no reply arrives."),
        reply_timeout_seconds=IntegerSchema(
            description="Timeout before that notification; required when expect_reply is true.",
            minimum=MIN_REPLY_TIMEOUT_SECONDS,
            maximum=MAX_REPLY_TIMEOUT_SECONDS,
        ),
        required=["to", "content", "expect_reply"],
    )
)
class SendSessionMessageTool(Tool):
    """Send text to another persisted session."""

    def __init__(
        self,
        *,
        sessions: SessionManager,
        bus: MessageBus,
        max_outgoing_messages_per_minute: int = 6,
        schedule_later: Callable[[float, Callable[[], None]], _CancelHandle] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._bus = bus
        self._sessions = sessions
        self._handles = SessionHandleResolver(sessions)
        self._max_outgoing_messages_per_minute = max_outgoing_messages_per_minute
        self._schedule_later = schedule_later
        self._clock = clock or time.monotonic
        self._sent_at: OrderedDict[str, deque[float]] = OrderedDict()
        self._pending_replies: dict[tuple[str, str], _PendingReply] = {}
        self._expiry_tasks: set[asyncio.Task[None]] = set()
        self._send_lock = asyncio.Lock()

    @classmethod
    def create(cls, ctx: ToolContext) -> Tool:
        if ctx.sessions is None or ctx.bus is None:
            raise RuntimeError("send_session_message requires sessions and a message bus")
        return cls(
            sessions=ctx.sessions,
            bus=ctx.bus,
            max_outgoing_messages_per_minute=ctx.config.max_outgoing_session_messages_per_minute,
        )

    @classmethod
    def enabled(cls, ctx: ToolContext) -> bool:
        return ctx.sessions is not None and ctx.bus is not None

    @property
    def name(self) -> str:
        return "send_session_message"

    @property
    def description(self) -> str:
        return "Queue a request or reply to another conversation by stable id or current @name. Prefer IDs for saved follow-ups. Use conversations__report for structured work status. This is not a user-facing reply in the current conversation. Delivery to its persistent inbox does not mean its model has read it."

    def runtime_context_provider(self):
        return self._provide_runtime_context

    async def _provide_runtime_context(
        self,
        request: RequestContext,
    ) -> RuntimeContextBlock | None:
        envelope = session_message_envelope(request.metadata)
        if envelope is None:
            return None
        source = session_handle_for_name(
            envelope["source_session_key"],
            envelope["source_handle"],
        )
        content = f"Message from @{source.name}."
        if envelope["expect_reply"]:
            content += " Reply with send_session_message."
        return RuntimeContextBlock(source="session_message", content=content)

    async def execute(
        self,
        to: str,
        content: str,
        expect_reply: bool,
        reply_timeout_seconds: int | None = None,
        **kwargs: Any,
    ) -> str:
        from cirno_core.utils.reasoning import strip_think

        request = current_request_context()
        if request is None or not request.session_key:
            return ToolResult.error("Error: session context is unavailable")
        try:
            import hashlib
            identity = request.turn_id or request.message_id
            delivery_id = hashlib.sha256(json.dumps(
                [request.session_key, identity, to, strip_think(content), expect_reply],
                ensure_ascii=False,
            ).encode()).hexdigest() if identity else None
            target = await self.enqueue(
                source_session_key=request.session_key,
                source_generation=request.session_generation,
                target_handle=to,
                content=strip_think(content),
                expect_reply=expect_reply,
                reply_timeout_seconds=reply_timeout_seconds,
                message_id=delivery_id,
            )
        except SessionMessageError as exc:
            return ToolResult.error(f"Error: {exc}")
        if expect_reply:
            return (
                f"Queued to {target}. A timeout notice will arrive after "
                f"{reply_timeout_seconds}s unless it replies."
            )
        return f"Queued to {target}."

    async def enqueue(
        self,
        *,
        source_session_key: str,
        source_generation: str | None = None,
        target_handle: str,
        content: str,
        expect_reply: bool,
        reply_timeout_seconds: int | None = None,
        message_id: str | None = None,
        report: dict[str, Any] | None = None,
    ) -> str:
        timeout_seconds = self._validate_reply_timeout(expect_reply, reply_timeout_seconds)
        target = await self._handles.aresolve(target_handle)
        if target is None:
            raise SessionMessageError(f"conversation {target_handle!r} was not found")

        source = await self._handles.ahandle_for_session(source_session_key)
        if source is None:
            raise SessionMessageError("source session was not found")
        envelope: SessionMessageEnvelope = {
            "message_id": message_id or uuid4().hex,
            "created_at_ms": int(time.time() * 1000),
            "expect_reply": expect_reply,
            "source_handle": source.name,
            "source_session_key": source.session_key,
            "target_session_key": target.session_key,
        }
        reverse_wait_key = (target.session_key, source.session_key)
        wait_key = (source.session_key, target.session_key)

        async with self._send_lock:
            source_header = await self._sessions.state.read_header(source.session_key)
            target_header = await self._sessions.state.read_header(target.session_key)
            if source_header is None or target_header is None:
                raise SessionMessageError("The source or target conversation no longer exists")
            if source_generation is not None and source_generation != source_header.generation:
                raise SessionMessageError("The sending conversation was replaced")
            now = self._clock()
            cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
            self._prune_expired_rate_limits(cutoff)
            sent_at = self._sent_at.get(source.session_key)
            if sent_at is None:
                sent_at = deque[float]()
            while sent_at and sent_at[0] <= cutoff:
                sent_at.popleft()
            if len(sent_at) >= self._max_outgoing_messages_per_minute:
                raise SessionMessageError(
                    f"session message rate limit reached ({self._max_outgoing_messages_per_minute}/minute)",
                )

            message = InboundMessage(
                channel="system",
                sender_id="session",
                chat_id=target.session_key,
                content=content,
                metadata={SESSION_MESSAGE_METADATA_KEY: envelope,
                          **({"_work_report": report, "_hidden_history": {"kind": "work_report"}} if report else {})},
                session_key_override=target.session_key,
                require_existing_session=True,
                session_generation=target_header.generation,
                input_role="system" if report else "user",
            )
            from dataclasses import replace

            from cirno_core.session.recovery.contracts import PENDING_FOLLOWUP_ID_KEY
            identifier = await self._sessions.state.queue_followup(target.session_key, message)
            if identifier is None:
                return f"@{target.name}"
            message = replace(message, metadata={**message.metadata, PENDING_FOLLOWUP_ID_KEY: identifier})
            await self._bus.publish_inbound(message)
            sent_at.append(now)
            self._sent_at[source.session_key] = sent_at
            self._sent_at.move_to_end(source.session_key)
            self._cancel_pending_reply(reverse_wait_key)
            if timeout_seconds is not None:
                self._cancel_pending_reply(wait_key)
                self._schedule_pending_reply(
                    wait_key,
                    timeout_seconds,
                    target.name,
                    envelope,
                    source_header.generation,
                )

        return f"@{target.name}"

    def _prune_expired_rate_limits(self, cutoff: float) -> None:
        """Drop sources ordered by their most recent successful send."""
        while self._sent_at:
            _, sent_at = next(iter(self._sent_at.items()))
            if sent_at[-1] > cutoff:
                return
            self._sent_at.popitem(last=False)

    @staticmethod
    def _validate_reply_timeout(
        expect_reply: bool,
        reply_timeout_seconds: int | None,
    ) -> int | None:
        if not expect_reply:
            return None
        if (
            reply_timeout_seconds is None
            or not MIN_REPLY_TIMEOUT_SECONDS
            <= reply_timeout_seconds
            <= MAX_REPLY_TIMEOUT_SECONDS
        ):
            raise SessionMessageError(
                "expect_reply=true requires reply_timeout_seconds between "
                f"{MIN_REPLY_TIMEOUT_SECONDS} and {MAX_REPLY_TIMEOUT_SECONDS}",
            )
        return reply_timeout_seconds

    def _cancel_pending_reply(self, key: tuple[str, str]) -> None:
        pending = self._pending_replies.pop(key, None)
        if pending is not None and pending.timer is not None:
            pending.timer.cancel()

    def _schedule_pending_reply(
        self,
        key: tuple[str, str],
        timeout_seconds: int,
        target_handle: str,
        request: SessionMessageEnvelope,
        source_generation: str,
    ) -> None:
        pending = _PendingReply(
            timeout_seconds=timeout_seconds,
            target_handle=target_handle,
            request=request,
            source_generation=source_generation,
        )
        self._pending_replies[key] = pending

        def expire() -> None:
            task = asyncio.create_task(self._expire_pending_reply(key, pending))
            self._expiry_tasks.add(task)
            task.add_done_callback(self._on_expiry_task_done)

        schedule = self._schedule_later or asyncio.get_running_loop().call_later
        pending.timer = schedule(float(timeout_seconds), expire)

    def _on_expiry_task_done(self, task: asyncio.Task[None]) -> None:
        self._expiry_tasks.discard(task)
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("Session reply timeout delivery failed")

    async def _expire_pending_reply(
        self,
        key: tuple[str, str],
        expected: _PendingReply,
    ) -> None:
        async with self._send_lock:
            if self._pending_replies.get(key) is not expected:
                return
            self._pending_replies.pop(key, None)
            source_session_key = expected.request["source_session_key"]
            source = await self._sessions.state.read_header(source_session_key)
            if source is None or source.generation != expected.source_generation:
                return
            await self._bus.publish_inbound(InboundMessage(
                channel="system",
                sender_id="session_timeout",
                chat_id=source_session_key,
                content=(
                    f"No reply from @{expected.target_handle} after "
                    f"{expected.timeout_seconds} seconds."
                ),
                session_key_override=source_session_key,
                require_existing_session=True,
                session_generation=expected.source_generation,
                input_role="user",
            ))
