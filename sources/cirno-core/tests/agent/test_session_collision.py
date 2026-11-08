"""Session keys remain distinct without filename normalization."""

from cirno_core.session.model import Session
from cirno_core.session.manager import SessionManager


def test_colliding_display_names_roundtrip_independently(tmp_path):
    manager = SessionManager(tmp_path)
    keys = ("telegram:a_b", "telegram:a:b", "telegram:a/b", "telegram:你好")
    for key in keys:
        session = Session(key=key)
        session.add_message("user", key)
        manager.save(session)
    assert len(manager.list_sessions()) == len(keys)
    for key in keys:
        assert manager.read_session_file(key)["messages"][0]["content"] == key
    manager.delete_session(keys[0])
    assert manager.read_session_snapshot(keys[1]) is not None
