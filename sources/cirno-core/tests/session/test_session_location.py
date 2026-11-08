"""Conversation storage belongs to the instance, never its working directory."""
from __future__ import annotations

import shutil

import pytest

from cirno_core.config.loader import load_config
from cirno_core.session.manager import SessionManager


def _save(manager, text="Saved research"):
    session = manager.get_or_create("websocket:research")
    session.add_message("user", text)
    manager.save(session)


def test_changing_workspace_and_restarting_preserves_all_conversations(tmp_path):
    original = SessionManager(tmp_path / "old")
    _save(original)
    changed = SessionManager(tmp_path / "workspace")
    assert changed.sessions_dir == original.sessions_dir
    assert changed.get_existing("websocket:research").messages[-1]["content"] == "Saved research"
    assert not (tmp_path / "workspace" / ".cirno").exists()
    assert changed.sessions_dir.name == "instance"
    assert changed.sessions_dir.parent.name == "sessions"
    assert not changed.sessions_dir.is_relative_to(changed.workspace)


def test_workspaces_can_move_copy_or_be_deleted_without_owning_history(tmp_path):
    workspace = tmp_path / "original"
    manager = SessionManager(workspace)
    _save(manager)
    workspace.rename(tmp_path / "moved")
    shutil.copytree(tmp_path / "moved", tmp_path / "copy")
    shutil.rmtree(tmp_path / "moved")
    for path in (tmp_path / "copy", tmp_path / "replacement"):
        reloaded = SessionManager(path)
        assert reloaded.sessions_dir == manager.sessions_dir
        assert reloaded.get_existing("websocket:research") is not None


def test_distinct_instances_remain_isolated(tmp_path):
    first = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "instance-a/sessions")
    second = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "instance-b/sessions")
    _save(first)
    assert second.get_existing("websocket:research") is None
    assert first.sessions_dir != second.sessions_dir


def test_custom_config_owns_session_storage(tmp_path):
    config = load_config(tmp_path / "custom-instance/config.json")
    manager = SessionManager(tmp_path / "workspace", sessions_root=config.runtime_data_dir / "sessions")
    _save(manager)
    assert manager.sessions_dir.parent == tmp_path / "custom-instance/state/sessions"



def test_runtime_does_not_select_an_old_workspace_store(tmp_path):
    root = tmp_path / "state/sessions"
    old = root / ("a" * 32)
    old.mkdir(parents=True)
    (root / ".instance-store").write_text(old.name)
    manager = SessionManager(tmp_path / "workspace", sessions_root=root)
    assert manager.sessions_dir == root / "instance"
    assert old.is_dir()  # Offline migration owns importing/removing old stores.


def test_session_root_inside_workspace_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="must be outside"):
        SessionManager(tmp_path, sessions_root=tmp_path / "sessions")


def test_canonical_store_symlink_cannot_redirect_instance_data(tmp_path):
    root = tmp_path / "state/sessions"
    root.mkdir(parents=True)
    (root / "instance").symlink_to(tmp_path / "other", target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link"):
        SessionManager(tmp_path / "workspace", sessions_root=root)
