"""Failed admission must never delete another accepted use of its new session."""

import asyncio
import threading

import pytest
from cirno_core.bus.events import InboundMessage
from cirno_core.session.display_history import HistoryFact, HistoryKind
from cirno_core.session.manager import SessionManager
from cirno_core.session.types import PARENT_SESSION_KEY
from cirno_server.webui.workspaces import WebUIWorkspaceController


@pytest.mark.parametrize("use", ["display", "canonical", "followup", "child", "metadata"])
async def test_scope_rollback_keeps_admitted_content(tmp_path, monkeypatch, use):
    monkeypatch.setattr("cirno_core.config.paths.get_data_dir", lambda: tmp_path / "data")
    sessions = SessionManager(tmp_path)
    controller = WebUIWorkspaceController(
        session_manager=sessions, default_workspace=tmp_path, default_restrict_to_workspace=True,
    )
    key = "websocket:admitted"
    try:
        generation, created = await controller.persist_scope("admitted", controller.default_scope())
        assert created
        if use == "display":
            await sessions.state.append_history(
                key, [HistoryFact(HistoryKind.INPUT, {"text": "An accepted message"})],
                expected_generation=generation,
            )
        elif use == "canonical":
            session = await sessions.state.get(key)
            session.add_message("user", "An accepted message")
            await sessions.state.finish_turn(session)
        elif use == "followup":
            await sessions.state.queue_followup(key, InboundMessage(
                channel="websocket", sender_id="user", chat_id="admitted", content="An accepted message",
            ))
        elif use == "metadata":
            await sessions.state.update_metadata(
                key, {"title": "Saved by the owner", "title_user_edited": True},
                expected_generation=generation,
            )
        else:
            await sessions.state.open_with_metadata("websocket:child", {PARENT_SESSION_KEY: key})
        await controller.rollback_scope_admission(key, generation, created=created)
        assert await sessions.state.read_header(key) is not None
        if use == "display":
            facts = await sessions.state.project_history(key, lambda history: history.all_facts())
            assert facts[0].content["text"] == "An accepted message"
        elif use == "canonical":
            assert (await sessions.state.read(key)).messages[0]["content"] == "An accepted message"
        elif use == "followup":
            assert (await sessions.state.read_header(key)).metadata["pending_user_followups"]
        elif use == "metadata":
            assert (await sessions.state.read_header(key)).metadata["title"] == "Saved by the owner"
        else:
            assert await sessions.state.read_header("websocket:child") is not None
    finally:
        await sessions.state.aclose()


async def test_scope_rollback_removes_only_its_unused_generation(tmp_path, monkeypatch):
    monkeypatch.setattr("cirno_core.config.paths.get_data_dir", lambda: tmp_path / "data")
    sessions = SessionManager(tmp_path)
    controller = WebUIWorkspaceController(
        session_manager=sessions, default_workspace=tmp_path, default_restrict_to_workspace=True,
    )
    key = "websocket:admitted"
    try:
        generation, created = await controller.persist_scope("admitted", controller.default_scope())
        await controller.rollback_scope_admission(key, generation, created=created)
        assert await sessions.state.read_header(key) is None
        await sessions.state.get(key)
        # A stale rollback is harmless after a reset/recreation.
        await controller.rollback_scope_admission(key, generation, created=created)
        assert await sessions.state.read_header(key) is not None
    finally:
        await sessions.state.aclose()


@pytest.mark.parametrize("existing", [False, True])
async def test_cancelled_scope_open_settles_its_owned_result(tmp_path, monkeypatch, existing):
    monkeypatch.setattr("cirno_core.config.paths.get_data_dir", lambda: tmp_path / "data")
    sessions = SessionManager(tmp_path)
    controller = WebUIWorkspaceController(
        session_manager=sessions, default_workspace=tmp_path, default_restrict_to_workspace=True,
    )
    key = "websocket:cancelled-admission"
    if existing:
        session = await sessions.state.get(key)
        session.add_message("user", "Keep this existing history")
        await sessions.state.finish_turn(session)
    committed, release = threading.Event(), threading.Event()
    publish = sessions.state.repository.publish

    def delayed_publish(session, **kwargs):
        if session.key == key:
            committed.set()
            assert release.wait(3), "Test did not release the committed write"
        return publish(session, **kwargs)

    monkeypatch.setattr(sessions.state.repository, "publish", delayed_publish)
    task = asyncio.create_task(controller.persist_scope("cancelled-admission", controller.default_scope()))
    try:
        assert await asyncio.to_thread(committed.wait, 2)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        saved = await sessions.state.read(key)
        if existing:
            assert saved is not None and saved.messages[0]["content"] == "Keep this existing history"
        else:
            assert saved is None
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await sessions.state.aclose()


async def test_scope_auxiliary_write_failure_keeps_the_draft_without_leaking_a_session(tmp_path, monkeypatch):
    monkeypatch.setattr("cirno_core.config.paths.get_data_dir", lambda: tmp_path / "data")
    sessions = SessionManager(tmp_path)
    controller = WebUIWorkspaceController(
        session_manager=sessions, default_workspace=tmp_path, default_restrict_to_workspace=True,
    )
    key = "websocket:failed-recent-project"
    scope = controller.default_scope()
    try:
        await controller.stage_scope("failed-recent-project", scope)

        def fail_recent(_path, **_kwargs):
            raise OSError("Recent projects are not writable")

        monkeypatch.setattr("cirno_server.webui.workspaces.remember_webui_project", fail_recent)
        with pytest.raises(OSError, match="Recent projects are not writable"):
            await controller.persist_scope("failed-recent-project", scope)
        assert await sessions.state.read_header(key) is None
        assert controller.existing_scope_for_session_key(key) == scope
    finally:
        await sessions.state.aclose()


async def test_repeated_cancellation_still_waits_for_admission_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr("cirno_core.config.paths.get_data_dir", lambda: tmp_path / "data")
    sessions = SessionManager(tmp_path)
    controller = WebUIWorkspaceController(
        session_manager=sessions, default_workspace=tmp_path, default_restrict_to_workspace=True,
    )
    key = "websocket:double-cancel"
    opened, finish_open = asyncio.Event(), asyncio.Event()
    cleaning, finish_cleanup = asyncio.Event(), asyncio.Event()
    open_with_metadata = sessions.state.open_with_metadata
    rollback = controller.rollback_scope_admission

    async def delayed_open(*args, **kwargs):
        result = await open_with_metadata(*args, **kwargs)
        opened.set()
        await finish_open.wait()
        return result

    async def delayed_cleanup(*args, **kwargs):
        cleaning.set()
        await finish_cleanup.wait()
        await rollback(*args, **kwargs)

    monkeypatch.setattr(sessions.state, "open_with_metadata", delayed_open)
    monkeypatch.setattr(controller, "rollback_scope_admission", delayed_cleanup)
    task = asyncio.create_task(controller.persist_scope("double-cancel", controller.default_scope()))
    try:
        await asyncio.wait_for(opened.wait(), 2)
        task.cancel()
        finish_open.set()
        await asyncio.wait_for(cleaning.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        finish_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await sessions.state.read_header(key) is None
    finally:
        finish_open.set()
        finish_cleanup.set()
        await asyncio.gather(task, return_exceptions=True)
        await sessions.state.aclose()


@pytest.mark.parametrize("read", ["sync", "async"])
async def test_persisted_workspace_authority_overrides_an_older_draft(tmp_path, monkeypatch, read):
    from cirno_core.security.workspace_access import (
        WORKSPACE_SCOPE_METADATA_KEY,
        build_workspace_scope,
    )
    from cirno_server.webui.file_preview import WebUIFilePreviewError, resolve_file_path

    monkeypatch.setattr("cirno_core.config.paths.get_data_dir", lambda: tmp_path / "data")
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside the restricted workspace")
    sessions = SessionManager(tmp_path)
    controller = WebUIWorkspaceController(
        session_manager=sessions, default_workspace=project, default_restrict_to_workspace=True,
    )
    key = "websocket:draft-authority"
    try:
        await controller.stage_scope("draft-authority", build_workspace_scope(project, "full"))
        current = build_workspace_scope(project, "restricted")
        # Another admission may publish the canonical header before the draft
        # owner can clear its view state, including when that owner is cancelled.
        await sessions.state.open_with_metadata(key, {WORKSPACE_SCOPE_METADATA_KEY: current.metadata()})
        scope = controller.existing_scope_for_session_key(key) if read == "sync" else await controller.async_scope_for_session_key(key)
        assert scope is not None and scope.metadata() == current.metadata()
        with pytest.raises(WebUIFilePreviewError) as error:
            resolve_file_path(str(outside), scope=scope)
        assert error.value.status == 403
        await sessions.state.delete(key)
        assert controller.existing_scope_for_session_key(key) is None
    finally:
        await sessions.state.aclose()


@pytest.mark.parametrize("read", ["sync", "async"])
async def test_private_workspace_never_inherits_default_full_access(tmp_path, monkeypatch, read):
    monkeypatch.setattr("cirno_core.config.paths.get_data_dir", lambda: tmp_path / "data")
    sessions = SessionManager(tmp_path)
    controller = WebUIWorkspaceController(
        session_manager=sessions, default_workspace=tmp_path, default_restrict_to_workspace=False,
    )
    key = "websocket:private-scope"
    try:
        await sessions.state.register_transient(key)
        scope = controller.existing_scope_for_session_key(key) if read == "sync" else await controller.async_scope_for_session_key(key)
        assert scope is not None and scope.restrict_to_workspace
    finally:
        await sessions.state.aclose()


@pytest.mark.parametrize("read", ["sync", "async"])
async def test_removed_project_does_not_revert_to_full_default_access(tmp_path, monkeypatch, read):
    from cirno_core.security.workspace_access import build_workspace_scope
    from cirno_server.webui.file_preview import WebUIFilePreviewError, resolve_file_path

    monkeypatch.setattr("cirno_core.config.paths.get_data_dir", lambda: tmp_path / "data")
    project = tmp_path / "removed-project"
    project.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("not in the project")
    sessions = SessionManager(tmp_path)
    controller = WebUIWorkspaceController(
        session_manager=sessions, default_workspace=tmp_path, default_restrict_to_workspace=False,
    )
    key = "websocket:removed-project"
    try:
        await controller.persist_scope("removed-project", build_workspace_scope(project, "restricted"))
        project.rmdir()
        scope = controller.existing_scope_for_session_key(key) if read == "sync" else await controller.async_scope_for_session_key(key)
        assert scope is not None and scope.project_path == project and scope.restrict_to_workspace
        with pytest.raises(WebUIFilePreviewError) as error:
            resolve_file_path(str(outside), scope=scope)
        assert error.value.status == 403
    finally:
        await sessions.state.aclose()


@pytest.mark.parametrize("can_change", [False, True])
async def test_only_an_explicit_owner_scope_change_can_repair_invalid_metadata(tmp_path, monkeypatch, can_change):
    from cirno_core.security.workspace_access import (
        WORKSPACE_SCOPE_METADATA_KEY,
        WorkspaceScopeError,
        build_workspace_scope,
    )

    monkeypatch.setattr("cirno_core.config.paths.get_data_dir", lambda: tmp_path / "data")
    sessions = SessionManager(tmp_path)
    controller = WebUIWorkspaceController(
        session_manager=sessions, default_workspace=tmp_path, default_restrict_to_workspace=False,
    )
    key = "websocket:invalid-policy"
    original = {"project_path": str(tmp_path), "access_mode": "invalid-mode"}
    repair = build_workspace_scope(tmp_path, "restricted")
    try:
        await sessions.state.open_with_metadata(key, {WORKSPACE_SCOPE_METADATA_KEY: original})
        # A routine file/message envelope cannot silently repair and broaden it.
        with pytest.raises(WorkspaceScopeError):
            await controller.scope_from_envelope(
                {WORKSPACE_SCOPE_METADATA_KEY: repair.metadata()}, session_key=key, can_change_project=can_change,
            )
        if can_change:
            scope = await controller.scope_for_set_request(
                {WORKSPACE_SCOPE_METADATA_KEY: repair.metadata()}, chat_id="invalid-policy",
                chat_running=False, can_change_project=True,
            )
            await controller.stage_scope("invalid-policy", scope)
            assert (await sessions.state.read_header(key)).metadata[WORKSPACE_SCOPE_METADATA_KEY] == repair.metadata()
        else:
            with pytest.raises(WorkspaceScopeError):
                await controller.scope_for_set_request(
                    {WORKSPACE_SCOPE_METADATA_KEY: repair.metadata()}, chat_id="invalid-policy",
                    chat_running=False, can_change_project=False,
                )
            assert (await sessions.state.read_header(key)).metadata[WORKSPACE_SCOPE_METADATA_KEY] == original
    finally:
        await sessions.state.aclose()
