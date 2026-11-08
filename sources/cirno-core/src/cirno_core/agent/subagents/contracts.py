"""Private-task control, execution limits and immutable outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

from cirno_usage.context import LLMUsageSource


class SubagentOrigin(TypedDict):
    channel: str
    chat_id: str
    session_key: str | None
    llm_usage_source: NotRequired[LLMUsageSource]


class SubagentControlError(ValueError):
    """A task control request violates ownership or admission rules."""


class SubagentMessageReceipt(TypedDict):
    task_id: str
    message_id: str
    receipt: Literal["accepted"]
    delivered: Literal[False]


@dataclass(frozen=True, slots=True)
class SubagentOutcome:
    """Execution outcome, independent of process cleanup errors."""

    state: Literal["done", "incomplete", "error", "cancelled"]
    result: str
    stop_reason: str | None = None
    error: str | None = None


@dataclass(slots=True)
class SubagentLimits:
    max_iterations: int
    max_tool_result_chars: int
