from __future__ import annotations

import json

from cirno_core.config.loader import load_config, save_config
from cirno_core.config.schema import Config
from cirno_core.config.timezone import detect_system_timezone


def test_new_config_detects_backend_timezone(monkeypatch) -> None:
    monkeypatch.setattr(
        "cirno_core.config.timezone.get_localzone_name",
        lambda: "Asia/Shanghai",
    )

    config = Config()

    assert config.agents.defaults.timezone == "Asia/Shanghai"
    assert config.agents.defaults.timezone_mode == "auto"


def test_legacy_config_preserves_explicit_timezone(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "cirno_core.config.timezone.get_localzone_name",
        lambda: "Asia/Shanghai",
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"agents": {"defaults": {"timezone": "America/New_York"}}}),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.agents.defaults.timezone == "America/New_York"
    assert config.agents.defaults.timezone_mode == "manual"


def test_auto_timezone_is_detected_by_backend_on_load(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "cirno_core.config.timezone.get_localzone_name",
        lambda: "Asia/Shanghai",
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "agents": {
                    "defaults": {
                        "timezone": "UTC",
                        "timezoneMode": "auto",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.agents.defaults.timezone == "Asia/Shanghai"
    assert config.agents.defaults.timezone_mode == "auto"


def test_manual_timezone_serializes_explicit_provenance(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config = Config.model_validate(
        {"agents": {"defaults": {"timezone": "America/New_York"}}}
    )

    save_config(config, config_path)

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["agents"]["defaults"]["timezone"] == "America/New_York"
    assert saved["agents"]["defaults"]["timezoneMode"] == "manual"


def test_backend_timezone_detection_falls_back_to_utc(monkeypatch) -> None:
    def unavailable_timezone() -> str:
        raise OSError("timezone unavailable")

    monkeypatch.setattr(
        "cirno_core.config.timezone.get_localzone_name",
        unavailable_timezone,
    )

    assert detect_system_timezone() == "UTC"


def test_backend_timezone_detection_normalizes_utc_aliases(monkeypatch) -> None:
    monkeypatch.setattr(
        "cirno_core.config.timezone.get_localzone_name",
        lambda: "Etc/UTC",
    )

    assert detect_system_timezone() == "UTC"
