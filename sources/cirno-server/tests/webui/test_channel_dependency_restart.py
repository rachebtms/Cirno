"""Dependency installation cannot hot-apply replacement code before a restart."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.runtime.admission import RuntimeAdmission
from cirno_server.webui.settings.contracts import SettingsRequest
from cirno_server.webui.settings.services import WebUISettingsServices
from cirno_server.webui.settings.system import SystemSettingsHandler, SystemSettingsOperations
from cirno_server.webui.settings.feature_settings import FeatureSettings


@pytest.mark.parametrize("failed", [False, True])
async def test_runtime_feedback_preserves_the_configuration_receipt_without_mutating_it(tmp_path, failed):
    from copy import deepcopy

    receipt = {"features": [], "requires_restart": True,
               "last_action": {"ok": True, "persisted": True, "message": "Settings saved"}}
    original = deepcopy(receipt)
    values = {name: MagicMock() for name in SystemSettingsOperations.__dataclass_fields__}
    values["cirno_feature_instance_target"] = lambda _: "instance"
    values["channel_feature_action"] = AsyncMock(
        side_effect=ValueError("reload failed") if failed else None,
        return_value={"handled": True, "ok": True, "requires_restart": False, "message": "Applied"},
    )
    features = FeatureSettings(WebUISettingsServices.create(tmp_path / "config.json"), MagicMock())
    result = await features.apply_runtime_change("enable", {"name": ["telegram"]}, receipt, SystemSettingsOperations(**values))
    assert receipt == original
    assert result["last_action"]["persisted"] is True
    assert result["last_action"]["ok"] is True
    assert result["last_action"]["hot_reload"] is not failed
    assert result["requires_restart"] is failed
    assert result["last_action"]["message"].startswith("Settings saved. ")


@pytest.mark.parametrize("installed_now", [False, True])
async def test_enable_defers_hot_activation_after_new_dependency_install(tmp_path, installed_now):
    runtime = AsyncMock(return_value={"handled": True, "ok": True, "requires_restart": False})

    def feature_action(action, query, *, config_path):
        return {"features": [{"name": "telegram", "type": "channel", "enabled": action == "enable"}],
                "requires_restart": installed_now if query.get("install_only") else True,
                "last_action": {"ok": True, "message": "Saved"}}

    values = {name: MagicMock() for name in SystemSettingsOperations.__dataclass_fields__}
    values.update(cirno_features_action=feature_action,
                  cirno_features_payload=lambda **kwargs: feature_action("read", {}, **kwargs),
                  channel_feature_action=runtime,
                  channel_runtime_status=None, cirno_feature_instance_target=lambda _: None)
    operations = SystemSettingsOperations(**values)
    handler = SystemSettingsHandler(WebUISettingsServices.create(tmp_path / "config.json"), MagicMock(), RuntimeAdmission())
    installed = await handler.handle("features-enable", SettingsRequest(query={
        "name": ["telegram"], "install_only": ["true"],
    }), operations)
    assert installed.payload["features"][0]["restart_pending"] is installed_now
    runtime.assert_not_awaited()
    enabled = await handler.handle("features-enable", SettingsRequest(query={"name": ["telegram"]}), operations)
    assert enabled.payload["requires_restart"] is installed_now
    if installed_now:
        runtime.assert_not_awaited()
        assert enabled.payload["last_action"]["hot_reload"] is False
    else:
        runtime.assert_awaited_once_with("enable", "telegram", None)
    runtime.reset_mock()
    stopped = await handler.handle("features-disable", SettingsRequest(query={"name": ["telegram"]}), operations)
    runtime.assert_awaited_once_with("disable", "telegram", None)
    assert stopped.payload["requires_restart"] is False


async def test_direct_enable_and_followup_configure_defer_new_dependency_code(tmp_path):
    runtime = AsyncMock(return_value={"handled": True, "ok": True, "requires_restart": False})
    calls = []

    def payload(**kwargs):
        return {"features": [{"name": "telegram", "type": "channel", "enabled": True}],
                "last_action": {"ok": True, "message": "Saved"}}

    def feature_action(action, query, *, config_path):
        calls.append(action)
        return {**payload(), "requires_restart": True,
                "last_action": {"ok": True, "message": "Saved", "dependencies_installed": True}}

    values = {name: MagicMock() for name in SystemSettingsOperations.__dataclass_fields__}
    values.update(cirno_features_action=feature_action, cirno_features_payload=payload,
                  channel_feature_action=runtime, channel_runtime_status=None,
                  cirno_feature_instance_target=lambda _: None)
    handler = SystemSettingsHandler(WebUISettingsServices.create(tmp_path / "config.json"), MagicMock(), RuntimeAdmission())
    operations = SystemSettingsOperations(**values)
    enabled = await handler.handle("features-enable", SettingsRequest(query={"name": ["telegram"]}), operations)
    assert enabled.payload["requires_restart"] is True
    assert enabled.payload["features"][0]["restart_pending"] is True
    runtime.assert_not_awaited()
    handler._save_channel_config_values = lambda *args: ["token"]
    saved = await handler.handle("channel-configure", SettingsRequest(
        query={"name": ["telegram"], "enable": ["true"]}, payload={"values": {"token": "fixture"}},
    ), operations)
    assert saved.payload["saved"] is True
    assert saved.payload["cirno_features"]["requires_restart"] is True
    assert calls == ["enable"], "Pending restart must bypass runtime-class loading in feature action"
    runtime.assert_not_awaited()


@pytest.mark.parametrize("invalid_value", ["invalid", ""])
async def test_pending_restart_still_validates_feature_action(tmp_path, invalid_value):
    from cirno_server.features.service import OptionalFeatureError

    values = {name: MagicMock() for name in SystemSettingsOperations.__dataclass_fields__}
    values["cirno_features_action"] = MagicMock(side_effect=OptionalFeatureError("install_only must be boolean"))
    values["channel_feature_action"] = AsyncMock()
    handler = SystemSettingsHandler(WebUISettingsServices.create(tmp_path / "config.json"), MagicMock(), RuntimeAdmission())
    handler.features.pending_restarts.add("telegram")
    result = await handler.handle("features-enable", SettingsRequest(query={
        "name": ["telegram"], "install_only": [invalid_value],
    }), SystemSettingsOperations(**values))
    assert result.status == 400
    values["cirno_features_action"].assert_called_once()
    values["channel_feature_action"].assert_not_awaited()
