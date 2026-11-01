"""Session storage reads only the current database."""

from cirno.session.manager import SessionManager


def test_list_and_reads_ignore_unrelated_jsonl_files(tmp_path):
    manager = SessionManager(tmp_path)
    (manager.sessions_dir / "cli_test.jsonl").write_text("invalid JSON")
    assert manager.list_sessions() == []
    assert manager.read_session_metadata("cli:test") is None
    assert manager.read_session_file("cli:test") is None
