import pytest

from cirno.config.home import get_home_path
from cirno.config.schema import Config
from cirno.providers.factory import make_provider
from cirno.webui.settings.contracts import WebUISettingsError
from cirno.webui.settings.profiles import profile_payload, update_profile
from cirno.webui.settings.runtime import update_runtime_config


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
        "agents.defaults.dream.cron": "0 3 * * *",
        "gateway.heartbeat.enabled": False,
        "gateway.heartbeat.interval_s": 3600,
        "network.request_timeout_s": 180,
        "network.stream_idle_timeout_s": 150,
        "network.provider_max_retries": 4,
    }, local_browser=True)
    provider = make_provider(config)
    assert provider.request_timeout_s == 180
    assert provider.stream_idle_timeout_s == 150
    assert len(provider._CHAT_RETRY_DELAYS) == 4
    assert config.agents.defaults.dream.build_schedule("UTC").expr == "0 3 * * *"
    assert not config.gateway.heartbeat.enabled


def test_invalid_maintenance_settings_do_not_change_saved_values():
    config = Config()
    with pytest.raises(WebUISettingsError, match="cron"):
        update_runtime_config(config, {"agents.defaults.dream.cron": "not a schedule"}, local_browser=True)
    assert config.agents.defaults.dream.cron is None
    with pytest.raises(WebUISettingsError):
        update_runtime_config(config, {"network.provider_max_retries": 2}, local_browser=True)
    assert config.network.provider_max_retries == 3


@pytest.mark.asyncio
async def test_home_file_routes_require_authenticated_socket_requests(tmp_path):
    from types import SimpleNamespace
    from urllib.parse import parse_qs, urlsplit

    from websockets.datastructures import Headers

    from cirno.bus.queue import MessageBus
    from cirno.webui.http_utils import http_json_response
    from cirno.webui.settings.routes import WebUISettingsRouter
    from cirno.webui.settings.services import WebUISettingsServices

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
