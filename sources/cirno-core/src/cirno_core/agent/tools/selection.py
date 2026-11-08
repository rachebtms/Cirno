"""One tool surface for a conversation's turns, compaction and token accounting."""

from cirno_core.session.roles import conversation_role
from cirno_core.agent.tools.registry import ToolRegistry



def conversation_tools(registry, session_key: str | None, *, ptc_mode: bool = False):
    selected = registry
    keep = conversation_role(session_key).allows_tool
    if any(not keep(name) for name in registry.tool_names):
        selected = ToolRegistry()
        for name in registry.tool_names:
            if keep(name):
                selected.register(registry.get(name))
    if ptc_mode:
        from cirno_core.agent.ptc.registry import PtcToolRegistry

        selected = PtcToolRegistry(selected)
    return selected
