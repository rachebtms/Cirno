"""Video previews authorize references without reading or copying their bodies."""

from unittest.mock import Mock

from cirno_core.security.workspace_access import default_workspace_scope
import pytest
from cirno_server.webui.media.resources import MediaAccessError
from cirno_server.webui.media_gateway import WebUIMediaServer
from cirno_server.webui.workspace_files import read_workspace_file


def test_large_draft_video_is_not_read_or_copied_for_preview(tmp_path, monkeypatch):
    source = tmp_path / "experiment #1.mp4"
    with source.open("wb") as stream:
        stream.truncate(128 * 1024 * 1024)
    scope = default_workspace_scope(tmp_path, True)
    gateway = WebUIMediaServer(workspace_path=tmp_path, logger=Mock())
    monkeypatch.setattr(
        type(source),
        "read_bytes",
        lambda *_: (_ for _ in ()).throw(AssertionError("eager file read")),
    )
    preview = read_workspace_file(
        str(source),
        scope=scope,
        media_url=lambda path: gateway.workspace_media_url(
            str(path), scope=scope, session_key=None
        ),
    )
    assert preview["kind"] == "video" and preview["editable"] is False
    assert preview["size"] == source.stat().st_size
    sig, payload = preview["url"].split("/")[-2:]
    resource = gateway.resolve_signed_media(sig, payload)
    assert resource.path == source
    assert resource.headers["Cache-Control"] == "no-store"
    assert list(tmp_path.iterdir()) == [source]


def test_video_reference_rechecks_changed_session_scope(tmp_path):
    source = tmp_path / "clip.webm"
    source.write_bytes(b"0123456789")
    scope = default_workspace_scope(tmp_path, True)
    gateway = WebUIMediaServer(workspace_path=tmp_path, logger=Mock())
    url = gateway.workspace_media_url(str(source), scope=scope, session_key="websocket:worker")
    sig, payload = url.split("/")[-2:]
    assert (
        gateway.resolve_signed_media(sig, payload, scope_for_session=lambda _: scope).path == source
    )
    other = tmp_path / "other"
    other.mkdir()
    denied = default_workspace_scope(other, True)
    with pytest.raises(MediaAccessError) as error:
        gateway.resolve_signed_media(sig, payload, scope_for_session=lambda _: denied)
    assert error.value.status == 403


def test_draft_video_does_not_follow_replaced_symlink_outside_workspace(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    source = project / "clip.mp4"
    source.write_bytes(b"original")
    outside = tmp_path / "private.mp4"
    outside.write_bytes(b"private")
    scope = default_workspace_scope(project, True)
    gateway = WebUIMediaServer(workspace_path=project, logger=Mock())
    sig, payload = gateway.workspace_media_url(str(source), scope=scope, session_key=None).split(
        "/"
    )[-2:]
    source.unlink()
    source.symlink_to(outside)
    with pytest.raises(MediaAccessError) as error:
        gateway.resolve_signed_media(sig, payload)
    assert error.value.status == 403
