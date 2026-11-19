"""Read receipts and request cancellation retain ownership of accepted writes."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.config.home import set_instance_path
from cirno_core.notifications.inbox import NotificationInbox
from cirno_server.webui.instance_api import instance_action


@pytest.fixture
def inbox(tmp_path):
    set_instance_path(tmp_path)
    try:
        yield NotificationInbox(tmp_path / "state")
    finally:
        set_instance_path(None)


@pytest.mark.parametrize("values,remaining", [
    ({"ids": ["sys"]}, {"system": 1, "operations": 1, "conversations": 0}),
    ({"category": "system"}, {"system": 0, "operations": 1, "conversations": 0}),
    ({}, {"system": 0, "operations": 0, "conversations": 0}),
])
async def test_read_receipt_matches_committed_rows_and_all_category_counts(inbox, values, remaining):
    for identifier, category in (("sys", "system"), ("sys2", "system"), ("question", "operations")):
        inbox.record(identifier, category, "question", status="pending")
    receipt = await instance_action({"action": "inbox.read", "values": values}, sessions=None, bus=None)
    page = inbox.list()
    assert receipt["ok"] is True
    assert receipt["unread"] == page["unread"] == remaining
    read_rows = [row for row in page["items"] if row["read_at"] is not None]
    assert read_rows and all(row["read_at"] == receipt["read_at"] for row in read_rows)
    assert all(row["status"] == "pending" for row in page["items"])


@pytest.mark.parametrize("action,method", [("inbox.read", "read"), ("inbox.open", "unavailable")])
async def test_cancelled_inbox_request_drains_accepted_thread_write(inbox, monkeypatch, action, method):
    inbox.record("sys", "system", "compaction", session_key="websocket:deleted")
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    original = getattr(NotificationInbox, method)

    def delayed(self, *args, **kwargs):
        started.set()
        assert release.wait(2)
        try:
            return original(self, *args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(NotificationInbox, method, delayed)
    sessions = SimpleNamespace(state=SimpleNamespace(read_header=AsyncMock(return_value=None)))
    task = asyncio.create_task(instance_action({"action": action, "values": {"id": "sys", "ids": ["sys"]}}, sessions=sessions, bus=None))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        # A loop barrier observes cancellation delivery without sleeping.
        for _ in range(3):
            await asyncio.sleep(0)
        assert not task.done(), "The request released a still-running inbox writer"
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(finished.wait, 2)
    assert task.cancelled()
    saved = inbox.get("sys")
    if action == "inbox.read":
        assert saved["read_at"] is not None
    else:
        assert saved["status"] == "unavailable"
