"""Queue non-blocking clarification questions in the current conversation."""
from __future__ import annotations

import json
from uuid import uuid4

from cirno.agent.tools.base import ToolResult, tool_parameters
from cirno.agent.tools.message import MessageTool
from cirno.agent.tools.schema import ArraySchema, ObjectSchema, StringSchema, tool_parameters_schema


def _question_fields():
    return {
        "question": StringSchema("One concise question in the user's language.", min_length=1, max_length=2000),
        "options": ArraySchema(StringSchema("Suggested answer", min_length=1, max_length=200), max_items=6,
                               description="Optional suggested answers; free text is always available."),
        "assumption": StringSchema("Optional plan while awaiting this answer.", max_length=1000),
    }


@tool_parameters(tool_parameters_schema(
    questions=ArraySchema(ObjectSchema(**_question_fields(), required=["question"], additional_properties=False),
                          min_items=1, max_items=8, description="Questions to queue in order. The user answers one at a time in the composer."),
    **_question_fields(),
    description="Provide questions for a batch, or question/options/assumption for one question; do not combine both forms.",
))
class AskUserTool(MessageTool):
    @property
    def name(self) -> str:
        return "ask_user"

    @property
    def description(self) -> str:
        return (
            "Ask asynchronous clarification questions in the current conversation. "
            "Use questions=[{question, options?, assumption?}, ...] to queue up to eight questions "
            "in order, or question/options/assumption for one question. The user answers them "
            "one at a time from the composer; questions from subsequent calls join the queue. "
            "Returns immediately without waiting. Continue useful independent work or follow the "
            "stated assumption; each later reply is quoted guidance injected into the running task, "
            "or starts a follow-up if it has finished. Do not poll or stop merely because a question "
            "is unanswered. Silence is never approval for a required authorization. Use the user's language."
        )

    async def execute(self, question: str | None = None, options: list[str] | None = None,
                      assumption: str = "", questions: list[dict] | None = None, **kwargs):
        if questions is not None:
            if question is not None or options is not None or assumption:
                return ToolResult.error("Use questions or question/options/assumption, not both")
            if not isinstance(questions, list) or not 1 <= len(questions) <= 8:
                return ToolResult.error("questions must contain 1–8 questions")
            rows = questions
        else:
            rows = [{"question": question, "options": options, "assumption": assumption}]
        prepared = []
        for row in rows:
            if not isinstance(row, dict) or set(row) - {"question", "options", "assumption"}:
                return ToolResult.error("Each question supports only question, options and assumption")
            text, choices, plan = row.get("question"), row.get("options"), row.get("assumption", "")
            if not isinstance(text, str) or not text.strip() or len(text) > 2000:
                return ToolResult.error("question must contain 1–2000 characters")
            if not isinstance(plan, str) or len(plan) > 1000:
                return ToolResult.error("assumption must contain at most 1000 characters")
            if choices is not None and (not isinstance(choices, list) or len(choices) > 6 or any(
                not isinstance(option, str) or not option.strip() or len(option) > 200 for option in choices
            )):
                return ToolResult.error("options must contain at most six non-empty answers of at most 200 characters")
            prepared.append({"id": uuid4().hex, "question": text.strip(),
                             "options": list(dict.fromkeys(option.strip() for option in choices or [])),
                             "assumption": plan.strip()})
        posted = []
        for data in prepared:
            text = "\n".join([data["question"], *[f"• {option}" for option in data["options"]],
                              *([data["assumption"]] if data["assumption"] else [])])
            result = await super().execute(text, _agent_ui={"kind": "user_question", "data": data})
            if isinstance(result, ToolResult) and result.is_error:
                return ToolResult.error(json.dumps({"status": "partial" if posted else "failed",
                    "posted_question_ids": posted, "failed_index": len(posted) + 1, "error": str(result),
                    "next": "Do not resend questions already posted; retry only the unposted questions."}))
            posted.append(data["id"])
        return json.dumps({"status": "posted", "question_ids": posted, "count": len(posted),
            **({"question_id": posted[0]} if len(posted) == 1 else {}),
            "next": "Continue independent work now. Answers arrive in order as quoted guidance; do not wait or poll."})
