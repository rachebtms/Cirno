from __future__ import annotations

from cirno_core.agent.tools.mcp.provider import session_extra


def test_mcp_preset_session_extra_only_persists_structured_mentions() -> None:
    assert session_extra({}) == {}
    assert session_extra({
        "mcp_presets": [{"name": "browserbase"}],
    }) == {"mcp_presets": [{"name": "browserbase"}]}
