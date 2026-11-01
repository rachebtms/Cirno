"""Reset a corrupt last_archived offset instead of hiding history (#4066)."""

import json
from pathlib import Path

from cirno.session.manager import Session, SessionManager


def _session(count: int, last_archived: object) -> Session:
    msgs = [{"role": "user", "content": f"msg{i}"} for i in range(count)]
    return Session(key="chan:chat", messages=msgs, last_archived=last_archived)


def test_out_of_range_offset_is_reset():
    assert _session(10, 999).last_archived == 0
    assert _session(3, -5).last_archived == 0


def test_non_integer_offset_is_reset():
    for offset in ("999", None, 0.5, True):
        assert _session(3, offset).last_archived == 0


def test_valid_offset_is_preserved():
    session = _session(10, 4)
    assert session.last_archived == 4
    assert session.last_archived == 4
    assert session.get_history() == [
        {"role": "user", "content": f"msg{i}"} for i in range(4, 10)
    ]


def test_loaded_null_metadata_becomes_empty_dict(tmp_path: Path):
    """Session jsonl metadata:null must load as {} so agent .pop/.get work."""
    path = tmp_path / "sessions" / "old.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "_type": "metadata",
            "key": "chan:chat",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "metadata": None,
            "last_archived": 0,
        }) + "\n",
        encoding="utf-8",
    )
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("chan:chat")
    assert session.metadata == {}
    session.metadata["title"] = "ok"
    assert session.metadata["title"] == "ok"
    session.metadata.pop("title", None)
    assert session.metadata == {}


def test_session_post_init_coerces_null_metadata():
    session = Session(key="chan:chat", metadata=None)  # type: ignore[arg-type]
    assert session.metadata == {}
