"""Tests for length-recovery prompt construction."""

from cirno_core.utils.runtime import build_length_recovery_message


def test_tool_reply_recovery_does_not_claim_internal_text_was_delivered():
    message = build_length_recovery_message("internal notes", tool_replies=True)
    assert message["_hidden_history"] is True
    assert "not a delivered reply" in message["content"]
    assert "user__message" in message["content"]
    assert "already_delivered_tail" not in message["content"]
    assert "internal notes" not in message["content"]


def test_truncated_tool_calls_must_be_regenerated_instead_of_continued():
    message = build_length_recovery_message("Visible preflight", discarded_tool_calls=True)
    assert "None of the tool calls" in message["content"]
    assert "Do not continue partial JSON" in message["content"]
    assert "new call IDs" in message["content"]
    assert "ordinary prose already streamed" in message["content"]
    assert "user__message" not in message["content"]


def test_length_recovery_message_anchors_the_existing_tail() -> None:
    omitted_prefix = "OMITTED_PREFIX"
    tail = "x" * 64

    message = build_length_recovery_message(omitted_prefix + tail)

    assert message["role"] == "user"
    assert omitted_prefix not in message["content"]
    assert f"<already_delivered_tail>\n{tail}\n</already_delivered_tail>" in message["content"]
    assert "Output only new continuation text" in message["content"]
    assert "Break remaining work into smaller steps" not in message["content"]
