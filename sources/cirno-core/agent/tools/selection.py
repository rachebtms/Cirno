"""One tool surface for a conversation's turns, compaction and token accounting."""

from cirno_core.session.keys import CIRNO_SESSION_KEY
from cirno_core.agent.tools.registry import ToolRegistry

# Coordination retains references, memory and lifecycle controls; execution is delegated.
_CIRNO_TOOLS = frozenset({
    "message", "ask_user", "create_session", "search_sessions",
    "read_session", "send_session_message", "create_goal", "update_goal", "get_goal",
    "memory", "read_file", "inspect_skill", "cron", "my", "control_session", "control_goal",
})


def conversation_tools(registry, session_key: str | None, *, ptc_mode: bool = False):
    selected = registry
    keep = (lambda name: name in _CIRNO_TOOLS) if session_key == CIRNO_SESSION_KEY else (lambda name: name not in {"message", "control_session", "control_goal"})
    if any(not keep(name) for name in registry.tool_names):
        selected = ToolRegistry()
        for name in registry.tool_names:
            if keep(name):
                selected.register(registry.get(name))
    if ptc_mode:
        from cirno_core.agent.ptc.registry import PtcToolRegistry

        selected = PtcToolRegistry(selected)
    return selected
