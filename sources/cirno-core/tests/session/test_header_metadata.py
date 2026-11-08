from cirno_core.session.manager import SessionManager


def test_lightweight_metadata_never_materializes_a_running_checkpoint(tmp_path, monkeypatch):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("websocket:long")
    session.metadata.update(
        {
            "runtime_checkpoint": {"large": "x" * 100_000},
            "workspace_scope": {"project_path": "/work"},
        }
    )
    manager.save(session)

    def forbidden(*args):
        raise AssertionError("A display-only read loaded the runtime checkpoint")

    monkeypatch.setattr(manager._store, "_metadata", forbidden)
    result = manager.read_session_metadata(session.key, include_runtime=False)
    assert result["metadata"]["workspace_scope"] == {"project_path": "/work"}
    assert "runtime_checkpoint" not in result["metadata"]


def test_cached_control_reads_do_not_copy_runtime_payloads(tmp_path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("websocket:long")

    class DoNotCopy:
        def __deepcopy__(self, memo):
            raise AssertionError("Control path copied a model checkpoint")

    session.metadata.update({"runtime_checkpoint": DoNotCopy(), "webui": True})
    manager.state.repository.snapshots[session.key] = session
    assert manager.state.peek_metadata(session.key, include_runtime=False) == {"webui": True}
    assert manager.state.peek_header(session.key, include_runtime=False).metadata == {"webui": True}


async def test_reusing_an_admitted_workspace_does_not_decode_or_rewrite_checkpoint(
    tmp_path, monkeypatch
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("websocket:long")
    session.metadata.update({"runtime_checkpoint": {"large": "x" * 100_000}, "webui": True})
    manager.save(session)
    version = manager.read_session_version(session.key)

    def forbidden(*args):
        raise AssertionError("Unchanged admission touched the running checkpoint")

    monkeypatch.setattr(manager._store, "_metadata", forbidden)
    monkeypatch.setattr(manager._store, "replace_metadata", forbidden)
    try:
        generation, created = await manager.state.open_with_metadata(
            session.key, {"webui": True}, expected_generation=session.generation
        )
        assert generation == session.generation and created is False
        assert manager.read_session_version(session.key) == version
    finally:
        await manager.state.aclose()
