"""Optional title generation cannot recreate a removed display destination."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.session.webui_turns.titles import maybe_generate_webui_title_after_turn


@pytest.mark.parametrize("destination", ["missing", "deleted", "existing", "manual", "deleted-during-request"])
async def test_title_generation_respects_destination_lifetime(history, destination):
    sessions = history.sessions
    source = await sessions.state.get("websocket:shared-title-source")
    source.metadata["webui"] = True
    source.add_message("user", "Review the experiment")
    source.add_message("assistant", "Experiment reviewed")
    await sessions.state.finish_turn(source)
    target_key = "websocket:display-title-target"
    if destination != "missing":
        await sessions.state.get(target_key)
        if destination == "deleted":
            await sessions.state.delete(target_key)
        elif destination == "manual":
            await sessions.state.update_metadata(target_key, {"title": "Owner title", "title_user_edited": True})

    async def generate(*_args, **_kwargs):
        if destination == "deleted-during-request":
            await sessions.state.delete(target_key)
        return SimpleNamespace(content="Experiment review", finish_reason="stop")

    provider = SimpleNamespace(chat_stream_with_retry=AsyncMock(side_effect=generate))
    result = await maybe_generate_webui_title_after_turn(
        channel="websocket", chat_id="display-title-target", metadata={"webui": True},
        sessions=sessions, session_key=source.key, provider=provider, model="fake-title-model",
    )
    target = await sessions.state.read_header(target_key)
    if destination in {"missing", "deleted", "deleted-during-request"}:
        assert not result
        assert target is None
    elif destination == "manual":
        assert not result
        assert target.metadata["title"] == "Owner title"
    else:
        assert result
        assert target.metadata["title"] == "Experiment review"
    if destination in {"missing", "deleted", "manual"}:
        provider.chat_stream_with_retry.assert_not_awaited()
    else:
        provider.chat_stream_with_retry.assert_awaited_once()
