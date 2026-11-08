from __future__ import annotations

import platform

from cirno_core.config.schema import Config
from cirno_server.channels.registry import load_channel_plugin
from cirno_server.webui.settings.system import (
    coerce_channel_value,
    save_channel_config_values,
    system_settings_payload,
    update_agent_system_settings,
)




def test_system_domain_owns_runtime_dto_and_agent_updates(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cirno_server.webui.settings.system.COMMIT", "a" * 40)
    config = Config()

    changed, restart_required = update_agent_system_settings(
        config,
        {
            "timezone": ["Asia/Shanghai"],
            "tool_status_summary_max_chars": ["120"],
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
    assert config.agents.defaults.tool_status_summary_max_chars == 120
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


