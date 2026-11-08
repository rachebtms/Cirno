"""Conversation roles share storage and execution, with distinct capabilities."""
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass

from cirno_core.session.keys import ROUTER_SESSION_KEY

_ROUTER_TOOLS = frozenset({"message", "control_session", "control_goal", "project"})


@dataclass(frozen=True)
class ConversationRole(ABC):
    name: str
    profile_files: tuple[str, ...]
    prompt_template: str
    can_fork: bool
    tool_replies: bool

    def allows_tool(self, name: str) -> bool:
        return name not in _ROUTER_TOOLS


class RouterConversation(ConversationRole):
    def __init__(self):
        super().__init__("router", ("SOUL.md",), "agent/router_conversation.md", False, True)

    def allows_tool(self, name: str) -> bool:
        return True


class WorkerConversation(ConversationRole):
    def __init__(self):
        super().__init__("worker", ("WORKER.md",), "agent/regular_conversation.md", True, False)


_ROUTER = RouterConversation()
_WORKER = WorkerConversation()


def conversation_role(key: str | None) -> ConversationRole:
    return _ROUTER if key == ROUTER_SESSION_KEY else _WORKER
