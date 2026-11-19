"""An inbox page, its unread counts and delivery cursor describe one snapshot."""

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from cirno_core.notifications.inbox import NotificationInbox


def test_notification_arriving_between_page_and_cursor_is_not_skipped(tmp_path):
    reader, writer = NotificationInbox(tmp_path), NotificationInbox(tmp_path)
    writer.record("first", "system", "compaction", body="first")
    ready_to_commit = threading.Event()
    original_read, original_write = reader.connect, writer.connect
    pending = []

    @contextmanager
    def writing():
        with original_write() as db:
            yield db
            ready_to_commit.set()

    writer.connect = writing

    class Cursor:
        def __init__(self, cursor, db, executor):
            self.cursor, self.db, self.executor = cursor, db, executor

        def fetchall(self):
            rows = self.cursor.fetchall()
            task = self.executor.submit(writer.record, "second", "system", "compaction", body="second")
            pending.append(task)
            if self.db.in_transaction:
                # A read snapshot can hold the writer's commit; do not deadlock
                # the test by waiting for that commit inside the reader.
                assert ready_to_commit.wait(2)
            else:
                task.result(2)
            return rows

    class ReadConnection:
        def __init__(self, db, executor):
            self.db, self.executor = db, executor

        def execute(self, sql, *args):
            cursor = self.db.execute(sql, *args)
            return Cursor(cursor, self.db, self.executor) if sql.startswith("SELECT * FROM notices") else cursor

    with ThreadPoolExecutor(max_workers=1) as executor:
        @contextmanager
        def reading():
            with original_read() as db:
                yield ReadConnection(db, executor)

        reader.connect = reading
        page = reader.list()
        for task in pending:
            task.result(2)
    assert [item["id"] for item in page["items"]] == ["first"]
    assert page["unread"]["system"] == 1
    assert page["latest_seq"] == page["items"][0]["seq"]
    next_page = writer.list(after=page["latest_seq"])
    assert [item["id"] for item in next_page["items"]] == ["second"]
