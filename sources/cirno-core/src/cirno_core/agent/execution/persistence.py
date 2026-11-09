"""TurnPersistence owns its stage of the admitted conversation lifecycle."""

from __future__ import annotations

import time
from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from cirno_core.agent.execution.context import TurnContext, TurnKind
from cirno_core.bus.events import (
    INBOUND_META_TURN_ID,
    InboundMessage,
)
from cirno_core.runtime.context import (
    RUNTIME_CONTEXT_HISTORY_META,
    RUNTIME_CONTEXT_MESSAGE_META,
)
from cirno_core.session import turn_continuation
from cirno_core.session.goal_state import (
    goal_state_raw,
    parse_goal_state,
)
from cirno_core.session.model import Session
from cirno_core.session.recovery.contracts import PENDING_FOLLOWUP_ID_KEY, PENDING_USER_TURN_KEY, RUNTIME_CHECKPOINT_KEY
from cirno_core.session.summary import (
    SessionSummaryCheckpoint,
)
from cirno_core.utils.model_messages import image_placeholder_text
from cirno_core.utils.runtime import (
    EMPTY_FINAL_RESPONSE_MESSAGE,
)
from loguru import logger

if TYPE_CHECKING:
    from cirno_core.agent.loop import AgentLoop


class TurnPersistence:
    def __init__(self, agent: AgentLoop):
        self.agent = agent

    async def release_archive(self, session_key: str) -> None:
        if not self.agent.release_archived_runtime:
            return
        from cirno_memory.repository import MemoryRepository

        home = self.agent.context.memory.workspace

        def archive(messages, project_id):
            return MemoryRepository(home).archive_messages(
                messages, session_key, project_id, preserve_system=True
            )

        released = await self.agent.sessions.state.release_archived_runtime(session_key, archive)
        if released:
            logger.info(
                "Released {} archived runtime messages for {}; original evidence stays in Home",
                released,
                session_key,
            )

    async def commit(self, ctx: TurnContext) -> None:
        session = ctx.require_session()

        if (
            ctx.kind is TurnKind.USER
            and (ctx.final_content is None or not ctx.final_content.strip())
            and not ctx.suppress_response
        ):
            ctx.final_content = EMPTY_FINAL_RESPONSE_MESSAGE

        latency_started_at = (
            ctx.visible_run_started_at
            if (
                ctx.kind is TurnKind.SYSTEM
                or turn_continuation.internal_continuation_inbound(ctx.msg.metadata)
            )
            and ctx.visible_run_started_at is not None
            else ctx.turn_wall_started_at
        )
        ctx.turn_latency_ms = max(0, int((time.time() - latency_started_at) * 1000))
        ctx.delivery.record_latency(ctx.turn_latency_ms)
        turn_continuation.prepare_save_boundary(ctx)
        if ctx.usage is not None and not ctx.ephemeral:
            session.metadata["_last_usage"] = ctx.usage.to_dict()
        if ctx.kind is TurnKind.USER and not ctx.ephemeral:
            turn_continuation.record_iteration_limit(
                session.metadata,
                ctx.stop_reason,
                continuation_pending=ctx.delivery.continuation_pending,
            )
        self.save_messages(
            session,
            ctx.all_messages,
            ctx.save_skip,
            turn_latency_ms=ctx.turn_latency_ms,
            summary_checkpoint=None if ctx.ephemeral else ctx.summary_checkpoint,
            input_persisted_early=ctx.input_persisted_early,
        )
        followup_id = ctx.msg.metadata.get(PENDING_FOLLOWUP_ID_KEY)
        if isinstance(followup_id, str) and followup_id:
            session.consumed_followup_ids |= {followup_id}
        if (
            not ctx.ephemeral
            and ctx.provider_compaction_applied
            and ctx.summary_checkpoint is not None
        ):
            # The next request must rebuild from the portable checkpoint;
            # the opaque continuation predates that transcript rewrite.
            session.provider_state = None
        self.clear_pending(session)
        self.clear_checkpoint(session)
        if ctx.commit_session:
            if ctx.stop_reason not in {"completed", "max_iterations", "empty_final_response"}:
                current = await self.agent.sessions.state.read_metadata(ctx.session_key)
                goal = parse_goal_state(goal_state_raw((current or {}).get("metadata"))) or {}
                if goal.get("status") == "active":
                    await self.agent.sessions.state.update_metadata(
                        ctx.session_key,
                        {
                            "goal_state": {
                                **goal,
                                "status": "blocked",
                                "recap": f"Execution stopped: {ctx.stop_reason}",
                            }
                        },
                    )
            await self.agent.sessions.state.finish_turn(session)
            if not ctx.ephemeral and session.policy.log_content:
                await self.release_archive(ctx.session_key)
        if ctx.commit_session and not ctx.ephemeral:
            await self.agent.reports.publish(ctx)
        if not ctx.ephemeral:
            await self.agent.runtime_event_publisher.session_turn_persisted(
                ctx.msg,
                ctx.session_key,
                turn_id=ctx.turn_id,
                attributes=ctx.attributes,
            )

    def save_messages(
        self,
        session: Session,
        messages: list[dict[str, Any]],
        skip: int,
        *,
        turn_latency_ms: int | None = None,
        summary_checkpoint: SessionSummaryCheckpoint | None = None,
        input_persisted_early: bool = False,
    ) -> None:
        """Commit new-turn messages and an optional summary boundary."""
        declared_tool_call_ids = {
            str(tc["id"])
            for m in session.messages
            if m.get("role") == "assistant"
            for tc_value in cast(Iterable[object], m.get("tool_calls") or [])
            if isinstance(tc_value, dict)
            for tc in (cast(dict[str, Any], tc_value),)
            if tc.get("id")
        }
        fulfilled_tool_call_ids = {
            str(m["tool_call_id"])
            for m in session.messages
            if m.get("role") == "tool" and m.get("tool_call_id")
        }
        last_assistant_idx: int | None = None
        saved_followup_ids: set[str] = set()
        checkpoint_boundary = self.checkpoint_boundary(
            summary_checkpoint,
            skip=skip,
            message_count=len(messages),
            session_key=session.key,
        )

        # The trigger input may already be the session tail while still being
        # the first message after the replacement checkpoint.
        if summary_checkpoint is not None and checkpoint_boundary == skip - 1:
            insert_at = len(session.messages) - (1 if input_persisted_early else 0)
            session.commit_summary_checkpoint(
                summary_checkpoint.summary,
                insert_at=insert_at,
            )

        for message_index, message in enumerate(messages[skip:], start=skip):
            # Insert against the raw transcript index before filtering the
            # message so persistence cleanup cannot shift the H/Δ boundary.
            if summary_checkpoint is not None and checkpoint_boundary == message_index:
                session.commit_summary_checkpoint(summary_checkpoint.summary)

            entry = dict(message)
            followup_id = entry.pop(PENDING_FOLLOWUP_ID_KEY, None)
            internal_meta = cast(object, entry.pop("_meta", None))
            runtime_context_meta = (
                cast(dict[str, Any], internal_meta).get(RUNTIME_CONTEXT_MESSAGE_META)
                if isinstance(internal_meta, dict)
                else None
            )
            role, content = entry.get("role"), entry.get("content")
            if role == "assistant" and not content and not entry.get("tool_calls"):
                continue  # skip empty assistant messages — they poison session context
            if role == "tool":
                tool_call_id = entry.get("tool_call_id")
                tool_call_id_str = str(tool_call_id) if tool_call_id else ""
                if (
                    not tool_call_id_str
                    or tool_call_id_str not in declared_tool_call_ids
                    or tool_call_id_str in fulfilled_tool_call_ids
                ):
                    # Undeclared tool results corrupt future provider requests.
                    logger.warning(
                        "Dropping invalid tool result {} from session {} during persistence",
                        tool_call_id_str or "(missing id)",
                        session.key,
                    )
                    continue
                fulfilled_tool_call_ids.add(tool_call_id_str)
                # Preserve model-visible text for replay; redact only inline images.
                if isinstance(content, list):
                    filtered = self.sanitize_blocks(
                        cast(list[object], content),
                    )
                    if not filtered:
                        # Preserve the tool_call/result pair after block filtering.
                        filtered = [
                            {"type": "text", "text": "[tool result omitted during persistence]"}
                        ]
                    entry["content"] = filtered
            elif role in {"user", "system"}:
                if isinstance(content, list):
                    filtered = self.sanitize_blocks(
                        cast(list[object], content),
                    )
                    if not filtered:
                        continue
                    entry["content"] = filtered
                if isinstance(runtime_context_meta, dict):
                    entry[RUNTIME_CONTEXT_HISTORY_META] = runtime_context_meta
                if isinstance(internal_meta, dict):
                    if isinstance(origin := internal_meta.get("input_origin"), dict):
                        entry["input_origin"] = origin
                    for key in ("timestamp", INBOUND_META_TURN_ID):
                        value = cast(dict[str, Any], internal_meta).get(key)
                        if isinstance(value, str) and value:
                            entry[key] = value
            entry.setdefault("timestamp", datetime.now().isoformat())
            session.messages.append(entry)
            if role in {"user", "system"} and isinstance(followup_id, str) and followup_id:
                saved_followup_ids.add(followup_id)
            if role == "assistant":
                last_assistant_idx = len(session.messages) - 1
                declared_tool_call_ids.update(
                    str(tc["id"])
                    for tc_value in cast(
                        Iterable[object],
                        entry.get("tool_calls") or [],
                    )
                    if isinstance(tc_value, dict)
                    for tc in (cast(dict[str, Any], tc_value),)
                    if tc.get("id")
                )
        if summary_checkpoint is not None and checkpoint_boundary == len(messages):
            session.commit_summary_checkpoint(summary_checkpoint.summary)
        if turn_latency_ms is not None and last_assistant_idx is not None:
            session.messages[last_assistant_idx]["latency_ms"] = int(turn_latency_ms)
        session.consumed_followup_ids |= saved_followup_ids
        session.updated_at = datetime.now()

    def sanitize_blocks(
        self,
        content: list[object],
    ) -> list[object]:
        """Strip volatile multimodal payloads before writing session history."""
        filtered: list[object] = []
        for block in content:
            if not isinstance(block, dict):
                filtered.append(block)
                continue

            block_data = cast(dict[str, Any], block)
            image_url = cast(dict[str, Any], block_data.get("image_url", {}))
            if block_data.get("type") == "image_url" and str(image_url.get("url", "")).startswith(
                "data:image/"
            ):
                internal_meta = cast(dict[str, Any], block_data.get("_meta") or {})
                path = cast(str, internal_meta.get("path", ""))
                reference = {"type": "text", "text": image_placeholder_text(path)}
                if not filtered or filtered[-1] != reference:
                    filtered.append(reference)
                continue

            filtered.append(block_data)

        return filtered

    @staticmethod
    def checkpoint_boundary(
        checkpoint: SessionSummaryCheckpoint | None,
        *,
        skip: int,
        message_count: int,
        session_key: str,
    ) -> int | None:
        """Return a checkpoint boundary only when it belongs to this turn."""
        if checkpoint is None:
            return None
        boundary = checkpoint.transcript_boundary
        if skip - 1 <= boundary <= message_count:
            return boundary
        logger.warning(
            "Ignoring invalid summary boundary {} outside [{}, {}] for {}",
            boundary,
            skip - 1,
            message_count,
            session_key,
        )
        return None

    def persist_subagent(self, session: Session, msg: InboundMessage) -> bool:
        """Persist subagent follow-ups before prompt assembly so history stays durable.

        Returns True if a new entry was appended; False if the follow-up was
        deduped (same ``subagent_task_id`` already in session) or carries no
        content worth persisting.
        """
        if not msg.content:
            return False
        metadata_value = cast(object, msg.metadata)
        task_id = msg.metadata.get("subagent_task_id") if isinstance(metadata_value, dict) else None
        if task_id and any(
            m.get("injected_event") == "subagent_result" and m.get("subagent_task_id") == task_id
            for m in session.messages
        ):
            return False
        session.add_message(
            "assistant",
            msg.content,
            sender_id=msg.sender_id,
            injected_event="subagent_result",
            subagent_task_id=task_id,
        )
        return True

    async def checkpoint(
        self,
        session: Session,
        payload: dict[str, Any],
    ) -> None:
        """Persist the latest in-flight turn state without blocking the event loop."""
        session.metadata[RUNTIME_CHECKPOINT_KEY] = payload
        await self.agent.sessions.state.checkpoint_view(session, payload)

    def mark_pending(self, session: Session) -> None:
        session.metadata[PENDING_USER_TURN_KEY] = True

    def clear_pending(self, session: Session) -> None:
        session.metadata.pop(PENDING_USER_TURN_KEY, None)

    def clear_checkpoint(self, session: Session) -> None:
        if RUNTIME_CHECKPOINT_KEY in session.metadata:
            session.metadata.pop(RUNTIME_CHECKPOINT_KEY, None)
