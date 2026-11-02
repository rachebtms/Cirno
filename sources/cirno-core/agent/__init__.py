"""Agent core module."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cirno_core.agent.context import ContextBuilder
    from cirno_core.agent.hook import (
        AgentHook,
        AgentHookContext,
        AgentRunHookContext,
        AgentTurnHookContext,
        AgentTurnHookFactory,
        CompositeHook,
    )
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.memory.consolidation import MemoryStore
    from cirno_core.skills.loader import SkillsLoader
    from cirno_core.agent.subagents.manager import SubagentManager


_EXPORTS = {
    "AgentHook": "cirno_core.agent.hook",
    "AgentHookContext": "cirno_core.agent.hook",
    "AgentRunHookContext": "cirno_core.agent.hook",
    "AgentTurnHookContext": "cirno_core.agent.hook",
    "AgentTurnHookFactory": "cirno_core.agent.hook",
    "AgentLoop": "cirno_core.agent.loop",
    "CompositeHook": "cirno_core.agent.hook",
    "ContextBuilder": "cirno_core.agent.context",
    "MemoryStore": "cirno_core.memory.consolidation",
    "SkillsLoader": "cirno_core.skills.loader",
    "SubagentManager": "cirno_core.agent.subagents.manager",
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
