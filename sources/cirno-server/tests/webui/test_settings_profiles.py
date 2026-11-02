import pytest

from cirno_core.config.home import get_home_path
from cirno_core.config.schema import Config
from cirno_core.providers.factory import make_provider
from cirno_server.webui.settings.contracts import WebUISettingsError
from cirno_server.webui.settings.profiles import profile_payload, update_profile
from cirno_server.webui.settings.runtime import update_runtime_config


def test_profile_edit_preserves_home_scope_and_detects_a_new_revision(tmp_path):
    before = profile_payload("soul")
    saved = update_profile("soul", "Quiet and precise.", before["revision"])
    assert (get_home_path() / "SOUL.md").read_text() == "Quiet and precise."
    assert saved["revision"] != before["revision"]
    with pytest.raises(WebUISettingsError, match="changed"):
        update_profile("soul", "Stale browser edit", before["revision"])
    with pytest.raises(WebUISettingsError, match="Unknown Home file"):
        profile_payload("../../outside")


def test_maintenance_and_model_connection_settings_reach_the_runtime():
    config = Config()
    config.agents.defaults.provider = "custom"
    config.agents.defaults.model = "test-model"
    config.providers.custom.api_base = "https://example.test/v1"
    config.providers.custom.api_key = "test-key"
    update_runtime_config(config, {
        "agents.defaults.dream.interval_h": 6,
        "agents.defaults.heartbeat.enabled": False,
        "agents.defaults.heartbeat.interval_s": 3600,
        "network.request_timeout_s": 180,
        "network.stream_idle_timeout_s": 150,
        "network.provider_max_retries": 4,
    }, local_browser=True)
    provider = make_provider(config)
    assert provider.request_timeout_s == 180
    assert provider.stream_idle_timeout_s == 150
    assert len(provider._CHAT_RETRY_DELAYS) == 4
    assert config.agents.defaults.dream.build_schedule("UTC").every_ms == 6 * 3_600_000
    assert not config.agents.defaults.heartbeat.enabled


def test_invalid_maintenance_settings_do_not_change_saved_values():
    config = Config()
    with pytest.raises(WebUISettingsError):
        update_runtime_config(config, {"network.provider_max_retries": 2}, local_browser=True)
    assert config.network.provider_max_retries == 3


@pytest.mark.asyncio
async def test_home_file_routes_require_authenticated_socket_requests(tmp_path):
    from types import SimpleNamespace
    from urllib.parse import parse_qs, urlsplit

    from websockets.datastructures import Headers

    from cirno_core.bus.queue import MessageBus
    from cirno_server.webui.http_utils import http_json_response
    from cirno_server.webui.settings.routes import WebUISettingsRouter
    from cirno_server.webui.settings.services import WebUISettingsServices

    def router(authorized):
        return WebUISettingsRouter(
            settings=WebUISettingsServices.create(tmp_path / "config.json"), bus=MessageBus(),
            logger=SimpleNamespace(exception=lambda *args: None, warning=lambda *args: None),
            check_api_token=lambda request: authorized,
            parse_query=lambda path: parse_qs(urlsplit(path).query), json_response=http_json_response,
            error_response=lambda status, message: http_json_response({"error": message}, status=status),
            runtime_surface="browser", runtime_capabilities={},
        )

    path = "/api/settings/profile/read"
    request = SimpleNamespace(path=path, headers=Headers())
    assert (await router(True).dispatch(None, request, path)).status_code == 405
    request._cirno_webui_mutation_request = True
    request._cirno_webui_mutation_payload = {"name": "soul"}
    assert (await router(False).dispatch(None, request, path)).status_code == 401
    assert (await router(True).dispatch(None, request, path)).status_code == 200
