"""A channel probe must use the config owner of its settings endpoint."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from cirno_core.bus.queue import MessageBus
from cirno_core.config.loader import save_config
from cirno_core.config.schema import Config
from cirno_server.channels.validation import validate_channel_config
from cirno_server.webui.settings.routes import WebUISettingsRouter
from cirno_server.webui.settings.services import WebUISettingsServices


@pytest.fixture
def instances(tmp_path, monkeypatch):
    paths = [tmp_path / name / "config.json" for name in ("first", "second")]
    for index, path in enumerate(paths):
        config = Config.model_validate({"channels": {"telegram": {
            "enabled": False, "token": f"{index + 1}:" + "a" * 24, "useProxy": True,
        }}})
        config.agents.defaults.workspace = str(tmp_path / "workspace")
        config.network.proxy = f"http://proxy-{index}.test:8080"
        save_config(config, path)
    monkeypatch.setattr("cirno_core.config.loader._current_config_path", paths[0])
    observed = []

    def get_me(token, proxy):
        observed.append((token, proxy))
        return {"ok": True, "result": {"id": 1, "username": "fixture"}}

    monkeypatch.setattr("cirno_server.channels.telegram.validation._get_me", get_me)
    return paths, observed


@pytest.mark.parametrize("selected", [0, 1])
@pytest.mark.parametrize("override", [{}, {"token": ""}, {"token": "3:" + "b" * 24}, {"token": None}])
async def test_channel_probe_uses_settings_owner_and_preserves_saved_credentials(
    instances, selected, override
):
    paths, observed = instances
    before = [path.read_bytes() for path in paths]
    router = WebUISettingsRouter(
        settings=WebUISettingsServices.create(paths[selected]), bus=MessageBus(), logger=MagicMock(),
        check_api_token=lambda _: True,
        parse_query=lambda value: parse_qs(urlsplit(value).query),
        json_response=lambda value: value,
        error_response=lambda status, message: {"status": status, "error": message},
    )
    route = "/v0/settings/channels/validate"
    request = SimpleNamespace(
        path=route, headers={}, _cirno_webui_mutation_request=True,
        _cirno_webui_mutation_payload={"name": "telegram", "values": override},
    )
    try:
        result = await router.dispatch(None, request, route)
        if "token" in override and override["token"] is None:
            assert result["status"] == "needs_setup"
            assert "token" in result["missing_fields"]
            assert not observed
        else:
            assert result["status"] == "connected"
            token = override.get("token") or f"{selected + 1}:" + "a" * 24
            assert observed == [(token, f"http://proxy-{selected}.test:8080")]
        assert [path.read_bytes() for path in paths] == before
    finally:
        await router.close()


def test_direct_probe_accepts_an_explicit_owner_and_does_not_change_default(instances):
    paths, observed = instances
    assert validate_channel_config("telegram", config_path=paths[1])["status"] == "connected"
    assert validate_channel_config("telegram")["status"] == "connected"
    assert observed == [
        ("2:" + "a" * 24, "http://proxy-1.test:8080"),
        ("1:" + "a" * 24, "http://proxy-0.test:8080"),
    ]
