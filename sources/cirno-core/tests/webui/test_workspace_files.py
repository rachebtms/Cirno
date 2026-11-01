"""Workspace browser persistence, conflict and boundary behavior."""

import stat

import pytest
from cirno.security.workspace_access import build_workspace_scope
from cirno.webui.file_preview import MAX_FILE_PREVIEW_BYTES, WebUIFilePreviewError
from cirno.webui.workspace_files import (
    create_workspace_entry,
    list_workspace_files,
    read_workspace_file,
    save_workspace_file,
)


def test_directory_navigation_search_and_hidden_files(tmp_path):
    scope = build_workspace_scope(tmp_path, "restricted")
    (tmp_path / "notes").mkdir()
    (tmp_path / "Report.md").write_text("report")
    (tmp_path / ".hidden").write_text("private")
    result = list_workspace_files("", scope=scope)
    assert result["parent"] is None
    assert [entry["name"] for entry in result["entries"]] == ["notes", "Report.md"]
    assert list_workspace_files("notes", scope=scope)["parent"] == str(tmp_path)
    assert list_workspace_files("", scope=scope, query="REPORT")["entries"][0]["name"] == "Report.md"
    assert len(list_workspace_files("", scope=scope, show_hidden=True)["entries"]) == 3


def test_save_uses_literal_filename_preserves_text_and_permissions(tmp_path):
    scope = build_workspace_scope(tmp_path, "restricted")
    path = tmp_path / "script#1.py "
    path.write_bytes("# 中文\r\nprint(1)\r\n".encode())
    path.chmod(0o750)
    preview = read_workspace_file(str(path), scope=scope)
    assert preview["content"] == "# 中文\r\nprint(1)\r\n"
    saved = save_workspace_file(str(path), "# 中文\r\nprint(2)\r\n", preview["revision"], scope=scope)
    assert saved["revision"] != preview["revision"]
    assert path.read_bytes() == "# 中文\r\nprint(2)\r\n".encode()
    assert stat.S_IMODE(path.stat().st_mode) == 0o750


def test_concurrent_external_change_is_not_overwritten(tmp_path):
    scope = build_workspace_scope(tmp_path, "restricted")
    path = tmp_path / "notes.md"
    path.write_text("original")
    preview = read_workspace_file(str(path), scope=scope)
    path.write_text("agent changed this")
    with pytest.raises(WebUIFilePreviewError) as error:
        save_workspace_file(str(path), "browser changed this", preview["revision"], scope=scope)
    assert error.value.status == 409
    assert path.read_text() == "agent changed this"


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_create_never_overwrites_existing_entries(tmp_path, kind):
    scope = build_workspace_scope(tmp_path, "restricted")
    result = create_workspace_entry("new", kind, scope=scope)
    assert result["path"] == str(tmp_path / "new")
    with pytest.raises(FileExistsError):
        create_workspace_entry("new", kind, scope=scope)


def test_preview_only_files_cannot_be_saved(tmp_path):
    scope = build_workspace_scope(tmp_path, "restricted")
    path = tmp_path / "large.txt"
    path.write_bytes(b"a" * (MAX_FILE_PREVIEW_BYTES + 1))
    assert read_workspace_file(str(path), scope=scope)["editable"] is False
    with pytest.raises(WebUIFilePreviewError) as error:
        save_workspace_file(str(path), "short", "", scope=scope)
    assert error.value.status == 415
    path.write_bytes(b"not utf8: \xff")
    assert read_workspace_file(str(path), scope=scope)["editable"] is False
    path.write_bytes(b"binary\0data")
    with pytest.raises(WebUIFilePreviewError) as error:
        read_workspace_file(str(path), scope=scope)
    assert error.value.status == 415


def test_restricted_scope_blocks_parent_and_symlink_escape(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    (project / "link").symlink_to(outside)
    scope = build_workspace_scope(project, "restricted")
    for path in ["../outside.txt", "link"]:
        with pytest.raises(WebUIFilePreviewError) as error:
            read_workspace_file(path, scope=scope)
        assert error.value.status == 403
    with pytest.raises(WebUIFilePreviewError) as error:
        create_workspace_entry("../new.txt", "file", scope=scope)
    assert error.value.status == 403
    full = build_workspace_scope(project, "full")
    assert read_workspace_file("../outside.txt", scope=full)["content"] == "outside"
