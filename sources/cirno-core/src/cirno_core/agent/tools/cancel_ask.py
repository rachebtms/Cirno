"""Withdraw asynchronous questions through the same durable delivery as asking."""
from __future__ import annotations

import json
import re

from cirno_core.agent.tools.base import ToolResult, tool_parameters
from cirno_core.agent.tools.message import MessageTool
from cirno_core.agent.tools.schema import StringSchema, tool_parameters_schema


@tool_parameters(tool_parameters_schema(
    question_id=StringSchema("Question ID returned by user.ask.", min_length=32, max_length=32),
    reason=StringSchema("Brief reason the question is no longer needed, in the user's language.", max_length=1000),
    required=["question_id"],
))
class CancelAskTool(MessageTool):
    router_only = False

    @property
    def name(self) -> str:
        return "cancel_ask"

    @property
    def description(self) -> str:
        return ("Withdraw an obsolete unanswered user.ask question in this conversation by its returned ID. "
                "Use when the answer is no longer needed; elapsed time alone never grants approval. "
                "Queues withdrawal through the question's delivery channel; answered records are preserved. "
                "Cannot withdraw another conversation's questions.")

    async def execute(self, question_id: str, reason: str = "", **kwargs):
        if not isinstance(question_id, str) or not re.fullmatch(r"[a-f0-9]{32}", question_id):
            return ToolResult.error("question_id must be a question ID returned by user.ask")
        if not isinstance(reason, str) or len(reason) > 1000:
            return ToolResult.error("reason must contain at most 1000 characters")
        data = {"id": question_id, "reason": reason.strip()}
        result = await super().execute(
            f"Question withdrawn ({question_id})" + (f": {reason.strip()}" if reason.strip() else ""),
            _agent_ui={"kind": "user_question_cancelled", "data": data},
        )
        if isinstance(result, ToolResult) and result.is_error:
            return result
        return json.dumps({"status": "cancellation_queued", "question_id": question_id})
