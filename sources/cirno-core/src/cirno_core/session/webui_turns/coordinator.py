"""Coordinator ownership for WebUI session presentation."""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, cast

from cirno_usage.types import LLMUsage
from loguru import logger

from cirno_core.bus.events import INBOUND_META_LOCAL_MEDIA, InboundMessage
from cirno_core.bus.outbound_events import (
    GoalStateSyncEvent,
    RuntimeModelUpdatedEvent,
    SessionUpdatedEvent,
    TurnEndEvent,
    TurnModelUpdatedEvent,
    UserInputEvent,
    outbound_message_for_event,
)
from cirno_core.bus.queue import MessageBus
from cirno_core.bus.runtime_events import (
    GoalStateChanged,
    RuntimeEventContext,
    RuntimeModelChanged,
    SessionTurnStarted,
    SubagentTaskChanged,
    TurnCompleted,
    TurnRunStatusChanged,
    TurnRuntimeAdmitted,
    UserInputAccepted,
)
from cirno_core.session.display_history import HISTORY_GENERATION_METADATA_KEY
from cirno_core.session.goal_state import goal_state_ws_blob
from cirno_core.session.keys import ROUTER_CHAT_ID, ROUTER_SESSION_KEY
from cirno_core.session.manager import SessionManager
from cirno_core.session.recovery.coordinator import RecoveryCoordinator
from cirno_core.session.session_handles import session_handle_for_name
from cirno_core.session.session_identity import is_webui_session_key, webui_session_key
from cirno_core.session.session_messages import (
    SessionMessageEnvelope,
    session_message_envelope,
)
from cirno_core.session.sqlite_store import SessionConflictError
from cirno_core.session.transcript import WebUITranscriptRecorder, append_session_message_input
from cirno_core.session.transport_metadata import (
    WEBUI_TURN_METADATA_KEY,
)
from cirno_core.utils.llm_runtime import LLMRuntime

from . import titles
from .activity import publish_turn_run_status
from .contracts import WEBUI_SESSION_METADATA_KEY


def _session_message_public_metadata(
    envelope: SessionMessageEnvelope,
) -> dict[str, Any]:
    source = session_handle_for_name(
        envelope["source_session_key"],
        envelope["source_handle"],
    )
    return {
        "message_id": envelope["message_id"],
        "session": source.public_payload(),
    }


@dataclass
class WebuiTurnCoordinator:
    """Translate generic runtime events into WebUI/WebSocket wire messages."""

    bus: MessageBus
    sessions: SessionManager
    schedule_background: Callable[[Awaitable[None]], None]
    recovery: RecoveryCoordinator | None = None

    def subscribe(self) -> Callable[[], None]:
        """Subscribe this coordinator to runtime events."""
        unsubscribe = [
            self.bus.subscribe(
                self._handle_user_input_accepted,
                UserInputAccepted,
            ),
            self.bus.subscribe(
                self._handle_session_turn_started,
                SessionTurnStarted,
            ),
            self.bus.subscribe(
                self._handle_run_status_changed,
                TurnRunStatusChanged,
            ),
            self.bus.subscribe(
                self._handle_turn_runtime_admitted,
                TurnRuntimeAdmitted,
            ),
            self.bus.subscribe(
                self._handle_turn_completed_event,
                TurnCompleted,
            ),
            self.bus.subscribe(
                self._handle_goal_state_changed,
                GoalStateChanged,
            ),
            self.bus.subscribe(self._handle_subagent_task_changed, SubagentTaskChanged),
            self.bus.subscribe(
                self._handle_runtime_model_changed,
                RuntimeModelChanged,
            ),
        ]

        def _unsubscribe() -> None:
            for fn in reversed(unsubscribe):
                fn()

        return _unsubscribe

    @contextmanager
    def connected(self) -> Generator[None, None, None]:
        """Keep connections alive through shutdown, then release the coordinator."""
        disconnect = self.subscribe()
        try:
            yield
        finally:
            disconnect()

    @staticmethod
    def _ctx_msg(ctx: RuntimeEventContext) -> InboundMessage:
        return InboundMessage(
            channel=ctx.channel,
            sender_id="runtime",
            chat_id=ctx.chat_id,
            content="",
            metadata=dict(ctx.metadata or {}),
            session_key_override=ctx.session_key,
            session_generation=ctx.session_generation,
        )

    @staticmethod
    def _is_websocket_event(ctx: RuntimeEventContext) -> bool:
        return ctx.channel == "websocket"

    async def _handle_user_input_accepted(self, event: UserInputAccepted) -> None:
        ctx = event.context
        if ctx.channel == "telegram" and ctx.session_key == ROUTER_SESSION_KEY:
            from cirno_core.session.router_session import ensure_router_session

            await ensure_router_session(self.sessions)
            session = await self.sessions.state.get_header(ROUTER_SESSION_KEY)
            telegram_metadata: dict[str, Any] = {**ctx.metadata, HISTORY_GENERATION_METADATA_KEY: session.generation}
            recorder = WebUITranscriptRecorder(self.sessions)
            if await recorder.append_user_message(
                ROUTER_CHAT_ID,
                event.content,
                metadata=telegram_metadata,
                media_paths=telegram_metadata.get(INBOUND_META_LOCAL_MEDIA),
            ):
                await self.bus.publish_outbound(
                    outbound_message_for_event(
                        channel="websocket",
                        chat_id=ROUTER_CHAT_ID,
                        event=UserInputEvent(
                            content=event.content,
                            created_at_ms=int(time.time() * 1000),
                            provenance={"channel": "telegram"},
                        ),
                        metadata=telegram_metadata,
                    )
                )
            return
        envelope = session_message_envelope(event.context.metadata)
        session_key = event.context.session_key
        if (
            event.context.channel != "system"
            or envelope is None
            or envelope["target_session_key"] != session_key
            or not is_webui_session_key(session_key)
        ):
            return
        persisted = await self.sessions.state.read_metadata(session_key)
        metadata_value: object = persisted.get("metadata") if persisted is not None else None
        metadata = (
            cast(dict[str, Any], metadata_value) if isinstance(metadata_value, dict) else None
        )
        if metadata is None or metadata.get(WEBUI_SESSION_METADATA_KEY) is not True:
            return
        public_metadata = _session_message_public_metadata(envelope)
        try:
            await append_session_message_input(
                session_key,
                sessions=self.sessions,
                content=event.content,
                created_at_ms=envelope["created_at_ms"],
                session_message=public_metadata,
                expected_generation=ctx.session_generation,
            )
        except (OSError, TypeError, ValueError, SessionConflictError):
            logger.opt(exception=True).warning(
                "Failed to persist session input {}",
                envelope["message_id"],
            )
            return
        await self.bus.publish_outbound(
            outbound_message_for_event(
                channel="websocket",
                chat_id=session_key.split(":", 1)[1],
                event=UserInputEvent(
                    content=event.content,
                    created_at_ms=envelope["created_at_ms"],
                    provenance={"session_message": public_metadata},
                ),
                metadata={
                    "_session_key": session_key,
                    "_session_generation": ctx.session_generation,
                },
            )
        )

    async def _handle_session_turn_started(self, event: SessionTurnStarted) -> None:
        if (
            event.origin
            and event.origin["kind"] != "conversation"
            and event.content
            and (
                event.origin["kind"] != "continuation"
                or event.context.metadata.get("_show_continuation_input") is True
            )
            and is_webui_session_key(event.context.session_key)
        ):
            import hashlib

            from cirno_core.session.presentation_history import fact_from_record

            origin = dict(event.origin)
            identifier = hashlib.sha256(
                json.dumps([origin, event.content], sort_keys=True).encode()
            ).hexdigest()[:24]
            # A replay uses the same turn/source identity. Do not duplicate its input row.
            source_id = f"system-input:{identifier}"
            origin["id"] = source_id
            key = event.context.session_key
            generation = event.context.session_generation
            created_at_ms = int(time.time() * 1000)
            record = {
                "event": "user",
                "text": event.content,
                "turn_id": event.context.metadata.get(WEBUI_TURN_METADATA_KEY) or source_id,
                "input_origin": origin,
                "created_at_ms": created_at_ms,
            }
            header = await self.sessions.state.read_header(key)
            if header is not None:
                accepted = (
                    not header.policy.persist
                    or await self.sessions.state.append_internal_input(
                        key,
                        fact_from_record(record),
                        identifier=source_id,
                        expected_generation=generation,
                    )
                )
                if accepted:
                    await self.bus.publish_outbound(
                        outbound_message_for_event(
                            channel="websocket",
                            chat_id=key.split(":", 1)[1],
                            event=UserInputEvent(
                                content=event.content,
                                created_at_ms=created_at_ms,
                                provenance={"input_origin": origin},
                            ),
                            metadata=event.context.metadata,
                        )
                    )
        if (
            self._is_websocket_event(event.context)
            and event.context.metadata.get(WEBUI_SESSION_METADATA_KEY) is True
        ):
            await self.sessions.state.update_metadata(
                event.context.session_key,
                {WEBUI_SESSION_METADATA_KEY: True},
                expected_generation=event.context.session_generation,
                create_if_missing=False,
            )

    async def _handle_run_status_changed(self, event: TurnRunStatusChanged) -> None:
        if not self._is_websocket_event(event.context):
            return
        await publish_turn_run_status(
            self.bus,
            self._ctx_msg(event.context),
            event.status,
            started_at=event.started_at,
        )

    async def _handle_turn_runtime_admitted(self, event: TurnRuntimeAdmitted) -> None:
        if not self._is_websocket_event(event.context):
            return
        await self.bus.publish_outbound(
            outbound_message_for_event(
                channel=event.context.channel,
                chat_id=event.context.chat_id,
                event=TurnModelUpdatedEvent(
                    model=event.runtime.model,
                    model_preset=event.runtime.model_preset,
                    context_window_tokens=event.runtime.context_window_tokens,
                ),
                metadata=event.context.metadata,
            )
        )

    async def _handle_turn_completed_event(self, event: TurnCompleted) -> None:
        if not self._is_websocket_event(event.context):
            return
        session = await self.sessions.state.read_header(event.context.session_key)
        if event.context.session_generation is not None and (
            session is None or session.generation != event.context.session_generation
        ):
            return
        msg = self._ctx_msg(event.context)
        await self.handle_turn_end(
            msg,
            session_key=event.context.session_key,
            latency_ms=event.latency_ms,
            usage=event.usage,
            round_usages=event.round_usages,
            context_window_tokens=(
                event.runtime.context_window_tokens if event.runtime is not None else None
            ),
            outcome=event.outcome,
            failure_kind=event.failure_kind,
            failure_error_kind=event.failure_error_kind,
            failure_attempts=event.failure_attempts,
        )
        if self.recovery is not None:
            await self.recovery.turn_completed(
                event.context.session_key,
                failure_kind=event.failure_kind,
                failure_error_kind=event.failure_error_kind,
                expected_generation=session.generation
                if session
                else event.context.session_generation,
            )
        self._schedule_title_update_from_event(event)

    async def _handle_goal_state_changed(self, event: GoalStateChanged) -> None:
        if not self._is_websocket_event(event.context):
            return
        cid = str(event.context.chat_id or "").strip()
        if not cid:
            return
        await self.bus.publish_outbound(
            outbound_message_for_event(
                channel=event.context.channel,
                chat_id=cid,
                event=GoalStateSyncEvent(
                    goal_state=goal_state_ws_blob(event.session_metadata),
                ),
                metadata=event.context.metadata,
            ),
        )

    async def _handle_subagent_task_changed(self, event: SubagentTaskChanged) -> None:
        ctx = event.context
        if not self._is_websocket_event(ctx) or ctx.session_key != webui_session_key(ctx.chat_id):
            return
        await self.bus.publish_event(event, channel=ctx.channel, chat_id=ctx.chat_id)

    async def _handle_runtime_model_changed(self, event: RuntimeModelChanged) -> None:
        await self.bus.publish_outbound(
            outbound_message_for_event(
                channel="websocket",
                chat_id="*",
                event=RuntimeModelUpdatedEvent(
                    model=event.model,
                    model_preset=event.model_preset,
                ),
            )
        )

    async def handle_turn_end(
        self,
        msg: InboundMessage,
        *,
        session_key: str,
        latency_ms: int | None,
        usage: LLMUsage | None = None,
        round_usages: tuple[LLMUsage, ...] = (),
        context_window_tokens: int | None = None,
        outcome: str = "completed",
        failure_kind: str | None = None,
        failure_error_kind: str | None = None,
        failure_attempts: int | None = None,
    ) -> None:
        if msg.channel != "websocket":
            return

        session = await self.sessions.state.read_header(session_key)
        if msg.session_generation is not None and (
            session is None or session.generation != msg.session_generation
        ):
            return
        await self.bus.publish_outbound(
            outbound_message_for_event(
                channel=msg.channel,
                chat_id=msg.chat_id,
                event=TurnEndEvent(
                    latency_ms=latency_ms,
                    goal_state=goal_state_ws_blob(session.metadata if session else None),
                    usage=usage,
                    round_usages=round_usages,
                    context_window_tokens=context_window_tokens,
                    outcome=outcome,
                    failure_kind=failure_kind,
                    failure_error_kind=failure_error_kind,
                    failure_attempts=failure_attempts,
                    failure_message=(
                        "No model configured. Open Settings → Models to create and select a model preset."
                        if failure_error_kind == "configuration"
                        else "Model provider request failed. Check the provider configuration or "
                        "service status, then try again."
                        if failure_kind == "model"
                        else "This turn failed and has ended."
                        if outcome == "failed"
                        else None
                    ),
                ),
                metadata=msg.metadata,
            )
        )

    def _schedule_title_update_from_event(self, event: TurnCompleted) -> None:
        title_context = event.runtime
        if event.context.metadata.get("webui") is not True or title_context is None:
            return

        async def _generate_title_and_notify(
            title_llm: LLMRuntime = title_context,
        ) -> None:
            generated = await titles.maybe_generate_webui_title_after_turn(
                channel=event.context.channel,
                chat_id=event.context.chat_id,
                metadata=event.context.metadata,
                sessions=self.sessions,
                session_key=event.context.session_key,
                provider=title_llm.provider,
                model=title_llm.model,
            )
            if generated:
                await self._publish_session_metadata_updated(
                    channel=event.context.channel,
                    chat_id=event.context.chat_id,
                    metadata=event.context.metadata,
                )

        self.schedule_background(_generate_title_and_notify())

    async def _publish_session_metadata_updated(
        self,
        *,
        channel: str,
        chat_id: str,
        metadata: dict[str, Any],
    ) -> None:
        await self.bus.publish_outbound(
            outbound_message_for_event(
                channel=channel,
                chat_id=chat_id,
                event=SessionUpdatedEvent(scope="metadata"),
                metadata=metadata,
            )
        )
