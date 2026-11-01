from __future__ import annotations

import platform

import pytest

from cirno.channels.registry import load_channel_plugin
from cirno.config.schema import Config
from cirno.webui.settings.system import (
    coerce_channel_value,
    pairing_payload,
    save_channel_config_values,
    system_settings_payload,
    update_agent_system_settings,
)


@pytest.mark.parametrize("status", [None, "sending", "sent", "failed", "unknown", []])
def test_pairing_payload_preserves_optional_delivery_state(status):
    item = {"code": "ABCD-EFGH", "channel": "feishu", "sender_id": "alice",
            "created_at": 1000, "expires_at": 1600}
    if status is not None:
        item["delivery_status"] = status
    [request] = pairing_payload(lambda: [item], now=1100)["requests"]
    assert request["code"] == "ABCD-EFGH"
    assert request["expires_in_seconds"] == 500
    if isinstance(status, str) and status in {"sending", "sent", "failed"}:
        assert request["delivery_status"] == status
    else:
        assert "delivery_status" not in request


def test_system_domain_owns_runtime_dto_and_agent_updates(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cirno.webui.settings.system.COMMIT", "a" * 40)
    config = Config()

    changed, restart_required = update_agent_system_settings(
        config,
        {
            "timezone": ["Asia/Shanghai"],
            "tool_hint_max_length": ["120"],
        },
    )
    payload = system_settings_payload(
        config,
        config_path=tmp_path / "config.json",
        version="0.3.0",
    )

    assert changed is True
    assert restart_required is True
    assert config.agents.defaults.timezone == "Asia/Shanghai"
    assert config.agents.defaults.timezone_mode == "manual"
    assert config.agents.defaults.tool_hint_max_length == 120
    assert payload["runtime"]["config_path"] == str(tmp_path / "config.json")
    assert payload["version"] == {"current": "0.3.0", "commit": "a" * 40}
    assert payload["environment"] == {
        "python_version": platform.python_version(),
        "os": platform.system(),
        "os_version": platform.release(),
        "architecture": platform.machine(),
    }
    assert payload["docs"]["version"] == "0.3.0"
    assert set(payload) == {"runtime", "runtime_config", "usage", "advanced", "version", "environment", "docs"}


def test_system_domain_validates_channel_field_values() -> None:
    assert coerce_channel_value("allow_from", "alice, bob", "list") == [
        "alice",
        "bob",
    ]
    assert coerce_channel_value("enabled", "yes", "bool") is True
    assert coerce_channel_value("port", "8765", "int") == 8765
    assert coerce_channel_value("delay", "0.6", "float") == 0.6
    assert coerce_channel_value("overrides", '{"123": "open"}', "json") == {
        "123": "open"
    }
    assert coerce_channel_value("token", None, "secret") == ""


def test_channel_secret_is_cleared_only_by_explicit_null() -> None:
    config = Config.model_validate({
        "channels": {"telegram": {"token": "saved-token"}},
    })

    saved = save_channel_config_values(
        config,
        "telegram",
        {"channels.telegram.token": None},
        load_channel_plugin=load_channel_plugin,
    )

    assert saved == ["channels.telegram.token"]
    assert config.channels.telegram["token"] == ""


def test_saving_other_telegram_settings_does_not_pin_the_global_notice_policy():
    config = Config.model_validate({"channels": {"showCompactionNotices": True}})
    save_channel_config_values(
        config, "telegram", {"token": "saved-token"}, load_channel_plugin=load_channel_plugin,
    )
    assert config.channels.telegram.get("showCompactionNotices") is None


