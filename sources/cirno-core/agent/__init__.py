"""Agent core module."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cirno.agent.context import ContextBuilder
    from cirno.agent.hook import (
        AgentHook,
        AgentHookContext,
        AgentRunHookContext,
        AgentTurnHookContext,
        AgentTurnHookFactory,
        CompositeHook,
    )
    from cirno.agent.loop import AgentLoop
    from cirno.memory.consolidation import MemoryStore
    from cirno.skills.loader import SkillsLoader
    from cirno.agent.subagents.manager import SubagentManager


_EXPORTS = {
    "AgentHook": "cirno.agent.hook",
    "AgentHookContext": "cirno.agent.hook",
    "AgentRunHookContext": "cirno.agent.hook",
    "AgentTurnHookContext": "cirno.agent.hook",
    "AgentTurnHookFactory": "cirno.agent.hook",
    "AgentLoop": "cirno.agent.loop",
    "CompositeHook": "cirno.agent.hook",
    "ContextBuilder": "cirno.agent.context",
    "MemoryStore": "cirno.memory.consolidation",
    "SkillsLoader": "cirno.skills.loader",
    "SubagentManager": "cirno.agent.subagents.manager",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))


__all__ = [
    "AgentHook",
    "AgentHookContext",
    "AgentRunHookContext",
    "AgentTurnHookContext",
    "AgentTurnHookFactory",
    "AgentLoop",
    "CompositeHook",
    "ContextBuilder",
    "MemoryStore",
    "SkillsLoader",
    "SubagentManager",
]
