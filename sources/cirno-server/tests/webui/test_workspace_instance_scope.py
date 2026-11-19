"""Default access and folder preferences never move to another instance."""

import pytest
from cirno_core.config.loader import load_config, set_config_path
from cirno_server.webui import workspaces
from cirno_server.webui.settings import api, capabilities


def sources(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    (first / "config.json").write_text("{}")
    set_config_path(first / "config.json")
    workspaces.write_webui_default_access_mode("review")
    controller = workspaces.WebUIWorkspaceController(session_manager=None, default_workspace=tmp_path,
                                                    default_restrict_to_workspace=True)
    set_config_path(second / "config.json")
    workspaces.write_webui_default_access_mode("full")
    return first, second, controller


@pytest.mark.parametrize("operation", ["scope", "favorite"])
def test_workspace_controller_retains_its_original_preferences(tmp_path, operation):
    first, second, controller = sources(tmp_path)
    if operation == "scope":
        assert controller.default_scope().access_mode == "review"
    else:
        controller.set_favorite_project(str(tmp_path), True)
        set_config_path(first / "config.json")
        assert workspaces.read_webui_workspace_state()["favorite_projects"] == [str(tmp_path)]
        set_config_path(second / "config.json")
        assert workspaces.read_webui_workspace_state()["favorite_projects"] == []


def test_network_settings_reads_the_config_source_access_mode(tmp_path):
    first, _, _ = sources(tmp_path)
    payload = capabilities.network_safety_payload(load_config(first / "config.json"))
    assert payload["webui_default_access_mode"] == "review"


def test_network_settings_writes_only_the_config_source_preferences(tmp_path, monkeypatch):
    first, second, _ = sources(tmp_path)
    monkeypatch.setattr(api, "settings_payload", lambda **_kwargs: {})
    api.update_network_safety_settings({"webui_default_access_mode": ["default"]}, config_path=first / "config.json")
    set_config_path(first / "config.json")
    assert workspaces.read_webui_default_access_mode() == "default"
    set_config_path(second / "config.json")
    assert workspaces.read_webui_default_access_mode() == "full"


def test_webui_gateway_media_and_uploads_use_the_explicit_server_instance(tmp_path):
    from cirno_core.bus.queue import MessageBus
    from cirno_server.channels.websocket.config import WebSocketConfig
    from cirno_server.webui.services import build_server_services

    first, _, _ = sources(tmp_path)
    gateway = build_server_services(
        config=WebSocketConfig(), bus=MessageBus(), session_manager=None, static_dist_path=None,
        workspace_path=tmp_path, default_restrict_to_workspace=True,
        config_path=first / "config.json", runtime_model_name=None,
    )
    assert gateway.uploads.store.media_dir == first / "state" / "media" / "websocket"
    assert gateway.media._media_dir(None) == first / "state" / "media"
