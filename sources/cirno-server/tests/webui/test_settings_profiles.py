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


@pytest.mark.parametrize("operation", ["read", "update"])
def test_profile_removed_during_read_is_missing_or_a_revision_conflict(monkeypatch, operation):
    from pathlib import Path

    from cirno_core.utils.atomic_file import read_atomic_bytes
    from cirno_server.webui.settings import profiles

    path = get_home_path() / "SOUL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Original profile", encoding="utf-8")
    before = profile_payload("soul")
    open_path = Path.open
    removed = False

    def disappearing_file(target, *args, **kwargs):
        nonlocal removed
        if target == path and not removed:
            path.unlink()
            removed = True
        return open_path(target, *args, **kwargs)

    def disappearing_snapshot(target):
        nonlocal removed
        if target == path and not removed:
            path.unlink()
            removed = True
        return read_atomic_bytes(target)

    monkeypatch.setattr(Path, "open", disappearing_file)
    monkeypatch.setattr(profiles, "read_atomic_bytes", disappearing_snapshot, raising=False)
    if operation == "update":
        with pytest.raises(WebUISettingsError) as error:
            update_profile("soul", "Stale browser edit", before["revision"])
        assert error.value.status == 409
        assert not path.exists()
    else:
        result = profile_payload("soul")
        assert result["content"] == ""
        assert result["revision"] != before["revision"]


def test_profile_snapshot_preserves_universal_newline_revisions():
    path = get_home_path() / "SOUL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"First\r\nSecond\rThird\n")
    result = profile_payload("soul")
    assert result["content"] == "First\nSecond\nThird\n"
    saved = update_profile("soul", result["content"], result["revision"])
    assert saved["revision"] == result["revision"]


@pytest.mark.parametrize("file_type", ["directory", "fifo"])
def test_non_regular_profile_is_rejected_before_opening(monkeypatch, file_type):
    import stat
    from pathlib import Path
    from types import SimpleNamespace

    from cirno_server.webui.settings import profiles

    path = get_home_path() / "SOUL.md"
    real_stat = Path.stat

    def special_stat(target, *args, **kwargs):
        if target == path:
            return SimpleNamespace(st_mode=stat.S_IFDIR if file_type == "directory" else stat.S_IFIFO)
        return real_stat(target, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", special_stat)
    monkeypatch.setattr(profiles, "read_atomic_bytes", lambda target: pytest.fail("Opened a non-regular Home resource"))
    with pytest.raises(WebUISettingsError) as error:
        profile_payload("soul")
    assert error.value.status == 400
    assert "regular file" in str(error.value)


def test_maintenance_and_model_connection_settings_reach_the_runtime():
    config = Config()
    config.agents.defaults.provider = "custom"
    config.agents.defaults.model = "test-model"
    config.providers.custom.api_base = "https://example.test/v1"
    config.providers.custom.api_key = "test-key"
    update_runtime_config(config, {
        "agents.defaults.consolidation.max_updates": 6,
        "agents.defaults.heartbeat.enabled": False,
        "agents.defaults.heartbeat.interval_s": 3600,
        "network.request_timeout_s": 180,
        "network.stream_idle_timeout_s": 150,
        "network.provider_max_retries": 4,
    })
    provider = make_provider(config)
    assert provider.request_timeout_s == 180
    assert provider.stream_idle_timeout_s == 150
    assert len(provider.retry_policy.delays) == 4
    assert config.agents.defaults.consolidation.max_updates == 6
    assert not config.agents.defaults.heartbeat.enabled


def test_invalid_maintenance_settings_do_not_change_saved_values():
    config = Config()
    with pytest.raises(WebUISettingsError):
        update_runtime_config(config, {"network.provider_max_retries": 2})
    assert config.network.provider_max_retries == 3


@pytest.mark.asyncio
async def test_home_file_routes_require_authenticated_socket_requests(tmp_path):
    from types import SimpleNamespace
    from urllib.parse import parse_qs, urlsplit

    from cirno_core.bus.queue import MessageBus
    from cirno_server.webui.http_utils import http_json_response
    from cirno_server.webui.settings.routes import WebUISettingsRouter
    from cirno_server.webui.settings.services import WebUISettingsServices
    from websockets.datastructures import Headers

    def router(authorized):
        return WebUISettingsRouter(
            settings=WebUISettingsServices.create(tmp_path / "config.json"), bus=MessageBus(),
            logger=SimpleNamespace(exception=lambda *args: None, warning=lambda *args: None),
            check_api_token=lambda request: authorized,
            parse_query=lambda path: parse_qs(urlsplit(path).query), json_response=http_json_response,
            error_response=lambda status, message: http_json_response({"error": message}, status=status),

        )

    path = "/v0/settings/profile/read"
    request = SimpleNamespace(path=path, headers=Headers())
    assert (await router(True).dispatch(None, request, path)).status_code == 405
    request._cirno_webui_mutation_request = True
    request._cirno_webui_mutation_payload = {"name": "soul"}
    assert (await router(False).dispatch(None, request, path)).status_code == 401
    assert (await router(True).dispatch(None, request, path)).status_code == 200
