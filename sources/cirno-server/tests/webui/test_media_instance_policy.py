"""Media policy follows the owning service, not a later global instance selection."""

import json
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import quote

import pytest
from cirno_core.security.workspace_access import default_workspace_scope
from cirno_server.channels.websocket.attachment_store import AttachmentStore
from cirno_server.webui.commands.attachments import (
    commit_message_attachments,
    parse_message_attachments,
)
from cirno_server.webui.http.sessions import SessionsRoutes
from cirno_server.webui.media.resources import MediaAccessError
from cirno_server.webui.media_gateway import WebUIMediaServer


@pytest.fixture
def media_owner(tmp_path, monkeypatch):
    project, own, foreign = [tmp_path / name for name in ("project", "own-media", "foreign-media")]
    for folder in (project, own, foreign):
        folder.mkdir()
    for folder in (own, foreign):
        folder.joinpath("notes.txt").write_text(folder.name)
    monkeypatch.setattr("cirno_server.webui.file_preview.get_media_dir", lambda: foreign)
    gateway = WebUIMediaServer(workspace_path=project, logger=Mock(), media_dir=lambda _: own)
    return project, own, foreign, gateway, default_workspace_scope(project, True)


@pytest.mark.parametrize("draft", [False, True])
@pytest.mark.parametrize("location", ["own", "foreign"])
def test_borrowed_reference_uses_the_gateway_media_exception(media_owner, draft, location):
    _, own, foreign, gateway, scope = media_owner
    target = (own if location == "own" else foreign) / "notes.txt"
    url = gateway.workspace_media_url(str(target), scope=scope, session_key=None if draft else "owner")
    sig, payload = url.split("/")[-2:]
    if location == "own":
        assert gateway.resolve_signed_media(sig, payload, scope_for_session=lambda _: scope).path == target
    else:
        with pytest.raises(MediaAccessError) as error:
            gateway.resolve_signed_media(sig, payload, scope_for_session=lambda _: scope)
        assert error.value.status == 403


@pytest.mark.parametrize("mode", ["content", "probe", "metadata"])
@pytest.mark.parametrize("location", ["own", "foreign"])
def test_session_preview_uses_the_gateway_media_exception(media_owner, mode, location):
    _, own, foreign, gateway, scope = media_owner
    target = (own if location == "own" else foreign) / "notes.txt"
    server = SimpleNamespace(check_api_token=lambda _: True, media=gateway,
                             workspaces=SimpleNamespace(scope_for_session_key=lambda _: scope))
    path = "/v0/sessions/websocket:owner/file-preview?path=" + quote(str(target))
    if mode != "content":
        path += "&" + mode + "=1"
    response = SessionsRoutes(server)._handle_file_preview(SimpleNamespace(path=path), "websocket:owner")
    if location == "foreign" and mode != "probe":
        assert response.status_code == 403
    else:
        assert response.status_code == 200
        value = json.loads(response.body)
        if mode == "probe":
            assert value == {"available": location == "own"}
        else:
            assert value["path"] == str(target)


@pytest.mark.parametrize("location", ["own", "foreign"])
@pytest.mark.parametrize("channel", [False, True])
async def test_message_local_attachment_checks_the_store_media_exception(media_owner, location, channel):
    _, own, foreign, _, scope = media_owner
    target = (own if location == "own" else foreign) / "notes.txt"
    store = AttachmentStore(own / "websocket", media_root=own) if channel else AttachmentStore(own)
    parsed = parse_message_attachments([{"path": str(target)}], max_count=2)
    if location == "own":
        result = await commit_message_attachments(parsed, scope=scope, store=store, owner="owner")
        assert result.paths == [str(target)]
    else:
        from cirno_server.webui.file_preview import WebUIFilePreviewError

        with pytest.raises(WebUIFilePreviewError) as error:
            await commit_message_attachments(parsed, scope=scope, store=store, owner="owner")
        assert error.value.status == 403


def test_default_gateway_keeps_its_initial_media_root(tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    for folder in (first, second):
        folder.mkdir()
        folder.joinpath("notes.txt").write_text(folder.name)
    selected = [first]
    monkeypatch.setattr("cirno_server.webui.media_gateway.get_media_dir", lambda _: selected[0])
    gateway = WebUIMediaServer(workspace_path=tmp_path, logger=Mock())
    signed = gateway.sign_or_stage_media_path(first / "notes.txt")
    assert signed is not None
    selected[0] = second
    sig, payload = signed["url"].split("/")[-2:]
    assert gateway.resolve_signed_media(sig, payload).path == first / "notes.txt"
