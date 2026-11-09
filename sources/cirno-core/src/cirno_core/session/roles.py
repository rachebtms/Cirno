"""Conversation roles share storage and execution, with distinct capabilities."""
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass

from cirno_core.session.keys import ROUTER_SESSION_KEY

_ROUTER_TOOLS = frozenset({"message", "control_session", "control_goal", "project"})


@dataclass(frozen=True)
class DirectExecutionLimits:
    max_calls: int = 9
    max_seconds: float = 10


@dataclass(frozen=True)
class ConversationRole(ABC):
    name: str
    profile_files: tuple[str, ...]
    prompt_template: str
    can_fork: bool
    tool_replies: bool
    excluded_tools: frozenset[str]
    direct_execution: DirectExecutionLimits | None = None

    def allows_tool(self, name: str) -> bool:
        return name not in self.excluded_tools


class RouterConversation(ConversationRole):
    def __init__(self):
        # Durable Workers own substantial work; transient subagents must not
        # become another execution path around that responsibility.
        super().__init__("router", ("SOUL.md",), "agent/router_conversation.md", False, True,
                         frozenset({"subagent"}), DirectExecutionLimits())


class WorkerConversation(ConversationRole):
    def __init__(self):
        super().__init__("worker", ("WORKER.md",), "agent/regular_conversation.md", True, False,
                         _ROUTER_TOOLS)


_ROUTER = RouterConversation()
_WORKER = WorkerConversation()


def conversation_role(key: str | None) -> ConversationRole:
    return _ROUTER if key == ROUTER_SESSION_KEY else _WORKER
