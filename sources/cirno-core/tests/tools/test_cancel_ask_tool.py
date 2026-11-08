"""Cancellation stays in its originating conversation and survives delivery replay."""
import json

import pytest

from cirno_core.agent.tools.ask_user import AskUserTool
from cirno_core.agent.tools.cancel_ask import CancelAskTool
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.message import capture_message_deliveries, current_conversation_has_delivery
from cirno_core.notifications.inbox import NotificationInbox


async def _ask_then_cancel(tmp_path):
    inbox = NotificationInbox(tmp_path)
    queued = []
    async def send(msg):
        queued.append(msg)
    with request_context(RequestContext(channel="websocket", chat_id="worker", session_key="websocket:worker", session_generation="generation")):
        posted = json.loads(await AskUserTool(send_callback=send).execute(question="Which dataset?"))
        with capture_message_deliveries():
            result = json.loads(await CancelAskTool(send_callback=send).execute(
                posted["question_id"], reason="The dataset is specified in the request.", chat_id="another",
            ))
            assert not current_conversation_has_delivery()
    assert result["status"] == "cancellation_queued"
    assert all(msg.chat_id == "worker" for msg in queued)
    for msg in queued:
        inbox.capture(msg)
    notice = inbox.get("question:" + posted["question_id"])
    assert notice["status"] == "cancelled" and notice["read_at"]
    assert notice["body"] == "Which dataset?"
    assert notice["data"]["cancellation_reason"] == "The dataset is specified in the request."
    # Durable outbox retries cannot resurrect the pending question.
    inbox.capture(queued[0])
    assert NotificationInbox(tmp_path).get(notice["id"])["status"] == "cancelled"
    return inbox, queued, posted["question_id"]


async def test_ask_then_cancel_uses_current_target_and_resolves_only_pending_notice(tmp_path):
    inbox, _, _ = await _ask_then_cancel(tmp_path)
    assert inbox.list()["unread"]["operations"] == 0


async def test_answer_and_cancellation_preserve_the_first_terminal_state(tmp_path):
    inbox, queued, identifier = await _ask_then_cancel(tmp_path)
    answer = f"> [!QUOTE]\n> <!-- cirno-question:{identifier} -->\n> Which dataset?\n\nDataset A"
    inbox.answer("websocket:worker", answer)
    assert inbox.get("question:" + identifier)["status"] == "cancelled"
    # On a separately delivered question, answering first wins over withdrawal.
    fresh = NotificationInbox(tmp_path / "fresh")
    fresh.capture(queued[0])
    fresh.answer("websocket:worker", answer)
    fresh.capture(queued[1])
    fresh.capture(queued[0])
    assert fresh.get("question:" + identifier)["status"] == "answered"


async def test_cross_conversation_and_old_generation_cannot_cancel(tmp_path):
    from dataclasses import replace
    inbox, queued, identifier = await _ask_then_cancel(tmp_path)
    fresh = NotificationInbox(tmp_path / "fresh")
    fresh.capture(queued[0])
    cancelled = queued[1]
    fresh.capture(replace(cancelled, chat_id="other", metadata={**cancelled.metadata, "_session_key": "websocket:other"}))
    fresh.capture(replace(cancelled, metadata={**cancelled.metadata, "_session_generation": "obsolete"}))
    assert fresh.get("question:" + identifier)["status"] == "pending"


async def test_invalid_id_and_delivery_failure_are_visible():
    async def offline(_msg):
        raise RuntimeError("delivery offline")
    tool = CancelAskTool(send_callback=offline, default_channel="websocket", default_chat_id="worker")
    assert (await tool.execute("bad-id")).is_error
    result = await tool.execute("f" * 32)
    assert result.is_error and "delivery offline" in result
