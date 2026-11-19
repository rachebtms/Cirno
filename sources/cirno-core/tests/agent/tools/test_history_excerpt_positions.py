"""History excerpts stay centered on real matches after display transformations."""

import json

import pytest
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.sessions import ReadSessionTool, SearchSessionsTool
from cirno_core.session.manager import SessionManager


@pytest.mark.parametrize("operation", ["search", "read"])
@pytest.mark.parametrize("variant", ["casefold", "whitespace"])
async def test_history_excerpt_keeps_the_matched_text(tmp_path, operation, variant):
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    if variant == "casefold":
        prefix, query, matched = "ß" * 5000, "STRASSE", "Straße"
    else:
        prefix, query, matched = "x" * 5000, "needle\n \tvalue", "needle\n \tvalue"
    text = prefix + " " + matched + " " + "z" * 6000
    await sessions.state.get_header("sdk:history")
    await sessions.state.import_messages("sdk:history", [{"role": "assistant", "content": text}])
    try:
        with request_context(
            RequestContext(channel="sdk", chat_id="current", session_key="sdk:current")
        ):
            if operation == "search":
                result = json.loads(await SearchSessionsTool(sessions).execute(query=query))
                excerpt = result["results"][0]["excerpts"][0]["content"]
                expected = " ".join(matched.split())
            else:
                result = json.loads(
                    await ReadSessionTool(sessions).execute(session_key="sdk:history", query=query)
                )
                excerpt = result["messages"][0]["content"]
                expected = matched
        assert expected in excerpt, "The selected match was lost from its own excerpt"
        assert len(excerpt) <= (362 if operation == "search" else 4002)
    finally:
        await sessions.state.aclose()
