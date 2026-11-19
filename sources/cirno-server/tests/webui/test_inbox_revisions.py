"""Inbox read receipts and content versions describe an ordered write snapshot."""

import json
import sqlite3

import pytest
from cirno_core.notifications.inbox import NotificationInbox


def test_read_and_later_notification_updates_have_distinct_versions(tmp_path):
    inbox = NotificationInbox(tmp_path)
    inbox.record("one", "system", "fixture", status="pending")
    original = inbox.list()
    assert original["revision"] == original["items"][0]["revision"]
    receipt = inbox.read()
    assert receipt["revision"] > original["revision"]
    inbox.record("one", "system", "fixture", status="failed")
    current = inbox.list()
    assert current["revision"] > receipt["revision"]
    assert current["items"][0]["revision"] > receipt["revision"]
    assert current["items"][0]["read_at"] is None
    assert current["unread"]["system"] == 1


def test_repeated_unchanged_notice_and_read_are_idempotent(tmp_path):
    inbox = NotificationInbox(tmp_path)
    inbox.record("one", "system", "fixture")
    first = inbox.read()
    inbox.record("one", "system", "fixture")
    assert inbox.read()["revision"] == first["revision"]
    assert inbox.list()["revision"] == first["revision"]


@pytest.mark.parametrize("operation", ["answer", "cancel", "unavailable"])
def test_terminal_question_and_availability_changes_advance_notice_versions(tmp_path, operation):
    inbox = NotificationInbox(tmp_path)
    identity, session = "a" * 32, "websocket:fixture"
    identifier = "question:" + identity
    inbox.record(identifier, "operations", "question", status="pending", session_key=session,
                 data={"id": identity, "session_generation": "fixture"})
    before = inbox.list()["revision"]
    if operation == "answer":
        assert inbox.answer(session, f"> [!QUOTE]\n> <!-- cirno-question:{identity} -->\n> Fixture\n\nAnswer", session_generation="fixture")
    elif operation == "cancel":
        inbox.record(identifier, "operations", "question", status="cancelled", session_key=session,
                     data={"reason": "Fixture cancellation", "session_generation": "fixture"})
    else:
        inbox.unavailable(identifier)
    assert inbox.get(identifier)["revision"] > before
    assert inbox.list()["revision"] > before


def test_existing_inbox_upgrades_without_changing_rows_or_pagination_ids(tmp_path):
    inbox = NotificationInbox(tmp_path)
    inbox.path.parent.mkdir(parents=True)
    with sqlite3.connect(inbox.path) as db:
        db.execute("""CREATE TABLE notices (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,kind TEXT NOT NULL,status TEXT NOT NULL,
            session_key TEXT,body TEXT NOT NULL,data TEXT NOT NULL,created_at INTEGER NOT NULL,read_at INTEGER
        )""")
        db.execute("INSERT INTO notices VALUES (1,'legacy','system','fixture','info',NULL,'original',?,1,NULL)", (json.dumps({}),))
    page = inbox.list()
    assert page["revision"] == 0
    assert page["items"][0]["revision"] == 0
    assert page["items"][0]["id"] == "legacy"
    assert page["items"][0]["seq"] == page["latest_seq"] == 1
    assert inbox.read()["revision"] == 1
    assert inbox.get("legacy")["body"] == "original"


@pytest.mark.parametrize("operation", ["notice", "read"])
def test_revision_failure_rolls_back_the_notice_or_read_change(tmp_path, operation):
    inbox = NotificationInbox(tmp_path)
    inbox.record("original", "system", "fixture")
    before = inbox.list()
    with inbox.connect() as db:
        if operation == "notice":
            db.execute("""CREATE TRIGGER fail_revision BEFORE INSERT ON notice_revisions
                WHEN NEW.id='new' BEGIN SELECT RAISE(ABORT,'Fixture revision failure'); END""")
        else:
            db.execute("""CREATE TRIGGER fail_clock BEFORE UPDATE ON inbox_clock
                BEGIN SELECT RAISE(ABORT,'Fixture revision failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="revision failure"):
        if operation == "notice":
            inbox.record("new", "system", "fixture")
        else:
            inbox.read()
    assert inbox.list() == before
