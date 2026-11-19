"""Configuration commits and cleanup failures must remain observable and owned."""

import json

import pytest
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.schema import Config
from cirno_core.config.tools import MCPServerConfig
from cirno_server.webui.mcp import actions, configuration
from cirno_server.webui.mcp.contracts import McpPresetError
from cirno_server.webui.settings.services import WebUISettingsServices


@pytest.fixture
def instance(tmp_path):
    path = tmp_path / "config.json"
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    config.tools.mcp_servers = {
        name: MCPServerConfig(
            type="streamableHttp", auth="oauth", url=f"https://fixture.test/{name}"
        )
        for name in ("first", "second")
    }
    save_config(config, path)
    return path


def test_failed_config_removal_preserves_managed_runtime_files(instance, monkeypatch):
    actions.mcp_presets_action("enable", {"name": ["playwright"]}, config_path=instance)
    cwd = instance.parent / "state" / "mcp" / "playwright"
    data = cwd / "keep.txt"
    data.write_text("Managed runtime data")

    def fail_save(*args, **kwargs):
        raise OSError("Fixture config write failed")

    monkeypatch.setattr(actions, "save_config", fail_save)
    with pytest.raises(OSError, match="config write failed"):
        actions.mcp_presets_action("remove", {"name": ["playwright"]}, config_path=instance)
    assert "playwright" in load_config(instance).tools.mcp_servers
    assert data.read_text() == "Managed runtime data"


@pytest.mark.parametrize("error", [OSError, McpPresetError])
def test_failed_runtime_cleanup_does_not_skip_credential_cleanup(instance, monkeypatch, error):
    actions.mcp_presets_action("enable", {"name": ["playwright"]}, config_path=instance)
    cwd = instance.parent / "state" / "mcp" / "playwright"
    data = cwd / "keep.txt"
    data.write_text("Managed runtime data")
    revoked = []

    def fail_runtime_cleanup(*args, **kwargs):
        raise error("Fixture private runtime detail")

    monkeypatch.setattr(actions, "remove_managed_stdio_cwd", fail_runtime_cleanup)
    monkeypatch.setattr(
        actions, "delete_mcp_oauth_credentials", lambda name, **kwargs: revoked.append(name)
    )
    payload = actions.mcp_presets_action("remove", {"name": ["playwright"]}, config_path=instance)
    assert "playwright" not in load_config(instance).tools.mcp_servers
    assert data.read_text() == "Managed runtime data"
    assert revoked == ["playwright"]
    assert payload["last_action"]["ok"] is False
    assert payload["last_action"]["persisted"] is True
    assert payload["last_action"]["verification_failed"] == ["managed_paths_absent"]
    assert "managed_paths_removed" not in payload["last_action"]
    assert "Fixture private runtime detail" not in str(payload)


@pytest.mark.parametrize("action", ["remove", "custom", "import", "import-cursor"])
async def test_credential_cleanup_failure_preserves_commit_receipt_and_runtime_reload(
    instance, monkeypatch, action
):
    cleanups = []
    reloads = []

    def fail_cleanup(name, **kwargs):
        cleanups.append(name)
        raise OSError("Fixture credential store unavailable")

    monkeypatch.setattr(actions, "delete_mcp_oauth_credentials", fail_cleanup)
    monkeypatch.setattr(configuration, "delete_mcp_oauth_credentials", fail_cleanup)
    query = {"name": ["first"]}
    if action == "custom":
        query.update(
            {
                "transport": ["streamableHttp"],
                "url": ["https://replacement.fixture.test/first"],
                "auth": ["oauth"],
            }
        )
    elif action in {"import", "import-cursor"}:
        query = {
            "config": [
                json.dumps(
                    {
                        "mcpServers": {
                            name: {
                                "type": "streamableHttp",
                                "url": f"https://replacement.fixture.test/{name}",
                                "auth": "oauth",
                            }
                            for name in ("first", "second")
                        }
                    }
                )
            ]
        }

    async def reload_mcp():
        reloads.append(load_config(instance).tools.mcp_servers)
        return {"ok": False, "message": "Fixture restart needed", "requires_restart": True}

    payload = await actions.mcp_presets_settings_action(
        action,
        query,
        config=WebUISettingsServices.create(instance).config,
        reload_mcp=reload_mcp,
    )
    assert len(reloads) == 1
    assert (
        ("first" not in reloads[0])
        if action == "remove"
        else reloads[0]["first"].url == "https://replacement.fixture.test/first"
    )
    assert cleanups == (["first", "second"] if action in {"import", "import-cursor"} else ["first"])
    assert payload["requires_restart"] is True
    receipt = payload["last_action"]
    assert receipt["ok"] is False
    assert receipt["persisted"] is True
    assert "cleanup" in receipt["message"].lower()
    assert receipt["verification_failed"] == [
        f"oauth_credentials_absent:{name}" for name in cleanups
    ]


async def test_cleanup_failure_route_tracks_restart_after_runtime_reload_also_fails(
    instance, monkeypatch
):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from urllib.parse import parse_qs, urlsplit

    from cirno_core.bus.queue import MessageBus
    from cirno_server.webui.settings.routes import WebUISettingsRouter

    def fail_cleanup(*args, **kwargs):
        raise OSError("Fixture private cleanup detail")

    async def fail_reload():
        raise OSError("Fixture runtime reload failed")

    monkeypatch.setattr(actions, "delete_mcp_oauth_credentials", fail_cleanup)
    router = WebUISettingsRouter(
        settings=WebUISettingsServices.create(instance),
        bus=MessageBus(),
        logger=MagicMock(),
        check_api_token=lambda _: True,
        parse_query=lambda value: parse_qs(urlsplit(value).query),
        json_response=lambda value: value,
        error_response=lambda status, message: {"status": status, "error": message},
        mcp_reload=fail_reload,
    )
    route = "/v0/settings/mcp-presets/remove"
    request = SimpleNamespace(
        path=route,
        headers={},
        _cirno_webui_mutation_request=True,
        _cirno_webui_mutation_payload={"name": "first"},
    )
    try:
        response = await router.dispatch(None, request, route)
        assert response["last_action"]["persisted"] is True
        assert response["last_action"]["ok"] is False
        assert "Fixture private cleanup detail" not in str(response)
        assert response["hot_reload"]["ok"] is False
        assert response["restart_required_sections"] == ["runtime"]
        assert "first" not in load_config(instance).tools.mcp_servers
    finally:
        await router.close()
