"""Deliver terminal task facts to the still-owning parent conversation."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from cirno_core.agent.subagents.contracts import SubagentOrigin
from cirno_core.agent.subagents.sessions import SubagentSessions
from cirno_core.bus.events import InboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.utils.prompt_templates import render_template


class SubagentReports:
    def __init__(self, bus: MessageBus, sessions: SubagentSessions | None):
        self.bus, self.sessions = bus, sessions

    async def announce(
        self,
        task_id: str,
        label: str,
        task: str,
        result: str,
        origin: SubagentOrigin,
        status: str,
        origin_message_id: str | None = None,
        *,
        receipts: dict[str, str] | None = None,
        stop_reason: str | None = None,
        error: str | None = None,
        partial_result: bool = False,
    ) -> None:
        """Announce the subagent result to the main agent via the message bus."""
        status_text = {
            "ok": "completed successfully",
            "cancelled": "was cancelled",
            "incomplete": "stopped before completing the task",
        }.get(status, "failed")

        announce_content = render_template(
            "agent/subagent_announce.md",
            label=label,
            status_text=status_text,
            task=task,
            result=result,
            stop_reason=stop_reason,
            error=error,
            partial_result=partial_result,
        )

        # Inject as system message to trigger main agent.
        # Use session_key_override to align with the main agent's effective
        # session key (which accounts for unified sessions) so the result is
        # routed to the correct pending queue (mid-turn injection) instead of
        # being dispatched as a competing independent task.
        override = origin.get("session_key") or f"{origin['channel']}:{origin['chat_id']}"
        if self.sessions is not None and (
            not self.sessions.exists(override) or not self.sessions.contains(task_id, override)
        ):
            return
        metadata: dict[str, Any] = {
            "injected_event": "subagent_result",
            "subagent_task_id": task_id,
            "subagent_state": "done" if status == "ok" else status,
            "subagent_stop_reason": stop_reason,
            "subagent_partial": partial_result,
        }
        metadata["subagent_message_receipts"] = receipts or {}
        if receipts:
            announce_content += "\nMessage receipts: " + json.dumps(receipts)
        if origin_message_id:
            metadata["origin_message_id"] = origin_message_id
        msg = InboundMessage(
            channel="system",
            sender_id="subagent",
            chat_id=f"{origin['channel']}:{origin['chat_id']}",
            content=announce_content,
            session_key_override=override,
            require_existing_session=True,
            metadata=metadata,
        )

        await self.bus.publish_inbound(msg)
        logger.debug(
            "Subagent [{}] announced result to {}:{}", task_id, origin["channel"], origin["chat_id"]
        )
