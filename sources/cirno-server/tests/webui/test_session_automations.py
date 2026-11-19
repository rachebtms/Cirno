"""Linked-chat titles must use the same session metadata as the sidebar."""

from pathlib import Path
from typing import Any

import pytest
from cirno_core.cron.types import CronJob, CronPayload
from cirno_core.session.manager import SessionManager
from cirno_core.triggers.local_types import LocalTrigger
from cirno_server.webui.session_automations import serialize_automation_jobs


@pytest.mark.parametrize(
    ("metadata", "title"),
    [
        ({"title": "推特大战场"}, "推特大战场"),
        ({"title": "<think>internal</think>Release planning"}, "Release planning"),
        ({"title": "<think>literal</think>", "title_user_edited": True}, "<think>literal</think>"),
        ({"title": 42}, ""),
        ({}, ""),
    ],
)
def test_linked_chat_title_reads_current_session_metadata(
    tmp_path: Path,
    metadata: dict[str, Any],
    title: str,
) -> None:
    manager = SessionManager(tmp_path)
    key = "websocket:linked-chat"
    session = manager.get_or_create(key)
    session.metadata.update(metadata)
    session.add_message("user", "Original message preview")
    manager.save(session)
    cron = CronJob(
        id="reminder",
        name="Drink water",
        payload=CronPayload(
            message="Take a break",
            session_key=key,
            origin_channel="websocket",
            origin_chat_id="linked-chat",
        ),
    )
    trigger = LocalTrigger(
        id="trigger",
        name="Build finished",
        enabled=True,
        channel="websocket",
        chat_id="linked-chat",
        session_key=key,
    )

    for expected in (title, "Updated title"):
        rows = serialize_automation_jobs(
            [cron, trigger],
            include_details=True,
            session_manager=manager,
            trigger_root=tmp_path / "triggers",
        )
        for row in rows:
            assert row["origin"] == {
                "session_key": key,
                "channel": "websocket",
                "chat_id": "linked-chat",
                "title": expected,
                "preview": "Original message preview",
            }
        manager.update_session_metadata(key, {"title": "Updated title"})

    assert cron.payload.session_key == key
    assert cron.payload.message == "Take a break"
    assert trigger.session_key == key


@pytest.mark.parametrize(
    "key,channel,expected",
    [
        ("websocket:bound-worker", "websocket", "websocket:bound-worker"),
        ("telegram:private-chat", "telegram", None),
    ],
)
def test_serialized_binding_uses_the_execution_session_without_exposing_external_keys(
    tmp_path, key, channel, expected
):
    cron = CronJob(
        id="job",
        name="Job",
        payload=CronPayload(
            session_key=key,
            origin_channel=channel,
            origin_chat_id="delivery-address",
        ),
    )
    trigger = LocalTrigger(
        id="trigger",
        name="Trigger",
        enabled=True,
        channel=channel,
        chat_id="delivery-address",
        session_key=key,
    )
    rows = serialize_automation_jobs(
        [cron, trigger],
        include_details=True,
        trigger_root=tmp_path / "triggers",
    )
    assert [row["webui_session_key"] for row in rows] == [expected, expected]
    if channel == "websocket":
        assert rows[0]["origin"]["session_key"] != rows[0]["webui_session_key"]
