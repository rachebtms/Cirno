"""A rejected settings save must not quietly leave half the requested change."""

import pytest
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.schema import Config
from cirno_server.webui import workspaces
from cirno_server.webui.settings import api


@pytest.fixture
def settings_files(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    save_config(Config(), config_path)
    monkeypatch.setattr(workspaces, "get_webui_dir", lambda: tmp_path / "state" / "webui")
    workspaces.write_webui_default_access_mode("review")
    preference_path = workspaces.webui_workspace_state_path()
    monkeypatch.setattr(api, "settings_payload", lambda **kwargs: {"requires_restart": kwargs["requires_restart"]})
    return config_path, preference_path


@pytest.mark.parametrize("published", [False, True])
def test_preference_write_failure_restores_both_settings_files(settings_files, monkeypatch, published):
    config_path, preference_path = settings_files
    before = {path: path.read_bytes() for path in settings_files}
    write = api.write_webui_default_access_mode

    def fail(mode, **kwargs):
        if published:
            write(mode, **kwargs)
        raise OSError("preference write failed")

    monkeypatch.setattr(api, "write_webui_default_access_mode", fail)
    with pytest.raises(api.WebUISettingsError) as error:
        api.update_network_safety_settings({
            "webui_allow_local_service_access": ["false"],
            "webui_default_access_mode": ["full"],
        }, config_path=config_path)
    assert error.value.status == 500
    assert "restored" in str(error.value).lower()
    assert {path: path.read_bytes() for path in settings_files} == before
    assert load_config(config_path).tools.webui_allow_local_service_access is True


def test_invalid_preferences_reject_before_changing_config(settings_files):
    config_path, preference_path = settings_files
    preference_path.write_bytes(b"broken JSON")
    before = config_path.read_bytes()
    with pytest.raises(api.WebUISettingsError):
        api.update_network_safety_settings({
            "webui_allow_local_service_access": ["false"],
            "webui_default_access_mode": ["full"],
        }, config_path=config_path)
    assert config_path.read_bytes() == before
    assert preference_path.read_bytes() == b"broken JSON"


def test_config_write_failure_after_replace_restores_original(settings_files, monkeypatch):
    config_path, preference_path = settings_files
    before = {path: path.read_bytes() for path in settings_files}
    save = api._save_settings_config

    def fail(config, path):
        save(config, path)
        raise OSError("directory sync failed after replace")

    monkeypatch.setattr(api, "_save_settings_config", fail)
    with pytest.raises(api.WebUISettingsError):
        api.update_network_safety_settings({
            "webui_allow_local_service_access": ["false"],
            "webui_default_access_mode": ["full"],
        }, config_path=config_path)
    assert {path: path.read_bytes() for path in settings_files} == before


def test_failed_save_does_not_leave_new_settings_files(tmp_path, monkeypatch):
    config_path = tmp_path / "new-config.json"
    monkeypatch.setattr(workspaces, "get_webui_dir", lambda: tmp_path / "state" / "webui")
    preference_path = workspaces.webui_workspace_state_path()
    write = api.write_webui_default_access_mode

    def fail(mode, **kwargs):
        write(mode, **kwargs)
        raise OSError("preference directory sync failed")

    monkeypatch.setattr(api, "write_webui_default_access_mode", fail)
    with pytest.raises(api.WebUISettingsError):
        api.update_network_safety_settings({
            "webui_allow_local_service_access": ["false"],
            "webui_default_access_mode": ["full"],
        }, config_path=config_path)
    assert not config_path.exists()
    assert not preference_path.exists()


def test_failed_rollback_reports_possibly_saved_settings(settings_files, monkeypatch):
    config_path, preference_path = settings_files

    def fail_write(*args, **kwargs):
        raise OSError("preference file locked")

    def fail_restore(*args):
        raise OSError("config rollback denied")

    monkeypatch.setattr(api, "write_webui_default_access_mode", fail_write)
    monkeypatch.setattr(api, "atomic_write_bytes", fail_restore)
    with pytest.raises(api.WebUISettingsError) as error:
        api.update_network_safety_settings({
            "webui_allow_local_service_access": ["false"],
            "webui_default_access_mode": ["full"],
        }, config_path=config_path)
    assert error.value.status == 500
    assert "rollback was incomplete for config.json" in str(error.value)
    assert "Some changes may already be saved" in str(error.value)
    assert load_config(config_path).tools.webui_allow_local_service_access is False
    assert workspaces.read_webui_default_access_mode() == "review"


async def test_failed_network_save_returns_a_structured_settings_error(settings_files, monkeypatch):
    from unittest.mock import MagicMock

    from cirno_server.webui.settings.capabilities import (
        CapabilitySettingsHandler,
        CapabilitySettingsOperations,
    )
    from cirno_server.webui.settings.contracts import SettingsRequest
    from cirno_server.webui.settings.services import WebUISettingsServices

    config_path, _ = settings_files

    def fail(mode, **kwargs):
        raise OSError("preference file locked")

    monkeypatch.setattr(api, "write_webui_default_access_mode", fail)
    handler = CapabilitySettingsHandler(WebUISettingsServices.create(config_path), MagicMock())
    result = await handler.handle("network-update", SettingsRequest(query={
        "webui_allow_local_service_access": ["false"], "webui_default_access_mode": ["full"],
    }), CapabilitySettingsOperations(MagicMock(), api.update_network_safety_settings, MagicMock()))
    assert result.status == 500 and result.payload is None
    assert "restored" in result.error
    assert result.decorate_restart is False
    assert load_config(config_path).tools.webui_allow_local_service_access is True
