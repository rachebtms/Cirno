import sqlite3

import pytest
from cirno_core.observability.request_snapshots import RequestSnapshots


def test_snapshots_deduplicate_messages_and_page_request_details(tmp_path):
    trace = RequestSnapshots(tmp_path / "trace.sqlite3")
    messages = [{"role": "system", "content": "system instructions"}] + [
        {"role": "user", "content": str(n)} for n in range(25)
    ]
    identifier = trace.start("recording-a", messages, [{"type": "function"}])
    trace.finish(identifier, {"content": "done"}, "completed")
    with sqlite3.connect(trace.path) as db:
        assert db.execute("SELECT count(*) FROM blobs").fetchone()[0] == 28
    first = trace.detail("recording-a", identifier)
    assert len(first["messages"]) == 10 and first["total"] == 26
    assert first["messages"][0]["role"] == "system"
    assert first["response"] == {"content": "done"}
    assert trace.detail("recording-a", identifier, offset=20)["messages"] == messages[20:]
    with pytest.raises(KeyError):
        trace.detail("other-chat", identifier)
