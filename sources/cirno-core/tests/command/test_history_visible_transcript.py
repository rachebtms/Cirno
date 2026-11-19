"""History commands display the persisted conversation, not model replay state."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.bus.events import InboundMessage
from cirno_core.command.builtin.history import cmd_history
from cirno_core.command.router import CommandContext
from cirno_core.runtime.context import (
    RUNTIME_CONTEXT_HISTORY_META,
    RuntimeContextBlock,
    append_runtime_context,
)
from cirno_core.session.history_visibility import HIDDEN_HISTORY_META
from cirno_core.session.model import Session


def context(session, *, with_session=True):
    msg = InboundMessage(channel="cli", sender_id="user", chat_id="fixture", content="/history 4")
    loop = SimpleNamespace(sessions=SimpleNamespace(state=SimpleNamespace(get=AsyncMock(return_value=session))))
    return CommandContext(msg=msg, key=session.key, raw=msg.content, args="4", session=session if with_session else None, loop=loop)


@pytest.mark.parametrize("with_session", [False, True])
async def test_history_keeps_visible_messages_before_a_consolidation_checkpoint(with_session):
    session = Session(key="cli:fixture")
    session.add_message("user", "archived question")
    session.add_message("assistant", "archived answer")
    session.commit_summary_checkpoint("internal summary")
    session.add_message("user", "recent question")
    session.add_message("assistant", "recent answer")
    out = await cmd_history(context(session, with_session=with_session))
    assert out.content == "Last 4 message(s):\n👤 You: archived question\n🤖 Bot: archived answer\n👤 You: recent question\n🤖 Bot: recent answer"
    assert out.metadata["render_as"] == "text"


@pytest.mark.parametrize("marker", [True, {"kind": "internal"}])
async def test_history_excludes_hidden_model_input_and_preserves_visible_commands(marker):
    session = Session(key="cli:fixture")
    session.add_message("user", "visible question")
    session.add_message("user", "internal input", **{HIDDEN_HISTORY_META: marker})
    session.add_message("user", "/goal visible task", _command=True)
    session.add_message("assistant", "visible answer")
    out = await cmd_history(context(session))
    assert out.content == "Last 3 message(s):\n👤 You: visible question\n👤 You: /goal visible task\n🤖 Bot: visible answer"


async def test_visible_history_still_removes_runtime_context_and_retains_media_breadcrumbs():
    session = Session(key="cli:fixture")
    content, metadata = append_runtime_context("visible question", [RuntimeContextBlock(source="fixture", content="internal metadata")])
    session.add_message("user", content, **{RUNTIME_CONTEXT_HISTORY_META: metadata})
    session.add_message("user", "", media=["fixture.png"])
    session.add_message("assistant", [{"type": "text", "text": "visible answer"}])
    out = await cmd_history(context(session))
    assert "internal metadata" not in out.content
    assert "visible question" in out.content
    assert "[image: fixture.png]" in out.content
    assert "visible answer" in out.content
