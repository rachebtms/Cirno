from __future__ import annotations

import json
from pathlib import Path

import pytest
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.schema import Config
from cirno_server.webui.settings.api import update_runtime_config_settings
from cirno_server.webui.settings.contracts import WebUISettingsError
from cirno_server.webui.settings.runtime import (
    runtime_config_payload,
    update_runtime_config,
)
from cirno_server.webui.settings.services import WebUISettingsServices


def test_shared_proxy_roundtrip_preserves_independent_feature_switches(tmp_path):
    path = tmp_path / "config.json"
    config = Config()
    config.tools.web.enable = False
    config.providers.openai.use_proxy = True
    save_config(config, path)
    for proxy in ("http://shared-proxy.example:7890", "http://shared-proxy.example:7891"):
        payload = update_runtime_config_settings({"network.proxy": proxy}, config_path=path)
        assert payload["runtime_config"]["network.proxy"] == proxy
        assert payload["requires_restart"]
        saved = load_config(path)
        assert saved.network.proxy == proxy
        assert saved.tools.web.enable is False
        assert saved.tools.web.use_proxy is False
        assert saved.providers.openai.use_proxy is True
    update_runtime_config_settings({"tools.web.use_proxy": True}, config_path=path)
    assert load_config(path).tools.web.use_proxy is True


def test_enabling_web_proxy_without_an_address_preserves_config(tmp_path):
    path = tmp_path / "config.json"
    save_config(Config(), path)
    before = path.read_bytes()
    with pytest.raises(WebUISettingsError, match="Advanced"):
        update_runtime_config_settings({"tools.web.use_proxy": True}, config_path=path)
    assert path.read_bytes() == before


def test_runtime_patch_persists_and_preserves_other_domains(tmp_path):
    path = tmp_path / "config.json"
    config = Config.model_validate({
        "providers": {"openai": {"apiKey": "${PRIVATE_API_KEY}"}},
        "channels": {"telegram": {"token": "keep-me", "streaming": False}},
    })
    save_config(config, path)
    payload = update_runtime_config_settings({
        "agents.defaults.max_tool_iterations": 71,
        "agents.defaults.timezone_mode": "manual",
        "agents.defaults.timezone": "Asia/Shanghai",
        "tools.exec.max_runtime": 0,
        "tools.exec.allowed_env_keys": ["MY_TOKEN"],
    }, config_path=path)
    saved = load_config(path)
    assert saved.agents.defaults.max_tool_iterations == 71
    assert saved.agents.defaults.timezone == "Asia/Shanghai"
    assert saved.tools.exec.max_runtime == 0
    assert saved.tools.exec.allowed_env_keys == ["MY_TOKEN"]
    assert saved.providers.openai.api_key == "${PRIVATE_API_KEY}"
    assert saved.channels.telegram == {"token": "keep-me", "streaming": False}
    assert payload["requires_restart"]
    assert "api.api_key" not in runtime_config_payload(saved)
    assert "PRIVATE_API_KEY" not in json.dumps(runtime_config_payload(saved))


@pytest.mark.parametrize("values", [
    {"channels.telegram.token": "bad"},
    {"agents.defaults.workspace": "relative-directory"},
    {"providers.openai.api_key": "bad"},
    {"tools.exec": {"enable": False}},
    {"agents.defaults.max_concurrent_subagents": 0},
    {"agents.defaults.max_tool_iterations": True},
    {"agents.defaults.idle_compact_after_minutes": -1},
    {"agents.defaults.idle_compact_min_tokens": -1},
    {"agents.defaults.idle_compact_keep_recent_tokens": -1},
    {"agents.defaults.idle_compact_after_minutes": 1.5},
    {"agents.defaults.idle_compact_after_minutes": 15.0},
    {"agents.defaults.idle_compact_after_minutes": "15"},
    {"agents.defaults.idle_compact_after_minutes": True},
    {"agents.defaults.idle_compact_after_minutes": False},
    {"agents.defaults.idle_compact_after_minutes": None},
    {"tools.exec.max_runtime": -1},
    {"tools.exec.max_runtime": 86401},
    {"tools.exec.max_runtime": "60"},
    {"tools.exec.enable": "false"},
    {"tools.exec.allowed_env_keys": "TOKEN"},
    {"tools.exec.allowed_env_keys": [3]},
    {"tools.exec.deny_patterns": ["["]},
    {"tools.ssrf_whitelist": ["not-a-network"]},
    {"tools.exec.sandbox": "unknown"},
    {"agents.defaults.dream.cron": "not a cron"},
    {"agents.defaults.dream.model_override": "missing"},
    {"agents.defaults.timezone_mode": "manual", "agents.defaults.timezone": "Mars/Olympus"},
    {"server.health_port": 65536},
    {"agents.defaults.heartbeat.interval_s": 0},
    {"api.host": "192.168.1.2"},
    {"api.timeout": float("nan")},
])
def test_invalid_patch_is_atomic(tmp_path, values):
    path = tmp_path / "config.json"
    save_config(Config(), path)
    before = path.read_bytes()
    with pytest.raises(WebUISettingsError):
        update_runtime_config_settings({
            "agents.defaults.max_tool_iterations": 71, **values,
        }, config_path=path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("limit", [120, 86400, 172800])
def test_shell_runtime_editor_uses_the_configured_limit(tmp_path, limit):
    path = tmp_path / "config.json"
    config = Config.model_validate({"tools": {"exec": {"maxRuntimeLimit": limit}}})
    save_config(config, path)
    before = path.read_bytes()

    with pytest.raises(WebUISettingsError, match=f"1–{limit} seconds"):
        update_runtime_config_settings({"tools.exec.max_runtime": limit + 1}, config_path=path)
    assert path.read_bytes() == before

    payload = update_runtime_config_settings({"tools.exec.max_runtime": limit}, config_path=path)
    assert payload["advanced"]["exec_max_runtime_limit"] == limit
    assert payload["runtime_config"]["tools.exec.max_runtime"] == limit
    saved = load_config(path).tools.exec
    assert saved.max_runtime == limit
    assert saved.max_runtime_limit == limit


def test_other_settings_preserve_a_longer_trusted_shell_runtime(tmp_path):
    path = tmp_path / "config.json"
    save_config(Config.model_validate({"tools": {"exec": {
        "maxRuntime": 172800, "maxRuntimeLimit": 86400,
    }}}), path)

    update_runtime_config_settings({"tools.exec.path_append": "extra-bin"}, config_path=path)

    saved = load_config(path).tools.exec
    assert saved.max_runtime == 172800
    assert saved.max_runtime_limit == 86400
    assert saved.path_append == "extra-bin"




def test_timezone_auto_and_nullable_fields():
    config = Config.model_validate({"agents": {"defaults": {
        "timezoneMode": "manual", "timezone": "UTC", "dream": {"cron": "0 2 * * *"},
    }}})
    assert update_runtime_config(config, {
        "agents.defaults.timezone_mode": "auto",
        "network.proxy": None,
    })
    assert config.agents.defaults.timezone_mode == "auto"
    assert not update_runtime_config(config, {})


def test_runtime_payload_matches_shared_catalogue_contract():
    fixture = Path(__file__).with_name("fixtures") / "runtime-config-keys.json"
    paths = json.loads(fixture.read_text(encoding="utf-8"))
    assert len(paths) == len(set(paths))
    assert set(runtime_config_payload(Config())) == set(paths)


def test_disabling_memory_consolidation_preserves_other_memory_settings():
    config = Config()
    before = config.agents.defaults.model_dump()
    assert update_runtime_config(config, {"agents.defaults.consolidation.learn": False})
    after = config.agents.defaults.model_dump()
    before["consolidation"]["learn"] = False
    assert after == before


@pytest.mark.parametrize("backend", ["bwrap", "seatbelt"])
def test_sandbox_backend_persists_with_path_permissions(tmp_path, backend):
    path = tmp_path / "config.json"
    payload = update_runtime_config_settings({
        "tools.exec.sandbox": backend,
        "tools.exec.sandbox_ro_binds": ["shared/read"],
        "tools.exec.sandbox_rw_binds": ["shared/write"],
    }, config_path=path)
    saved = load_config(path).tools.exec
    assert saved.sandbox == backend
    assert saved.sandbox_ro_binds == ["shared/read"]
    assert saved.sandbox_rw_binds == ["shared/write"]
    assert payload["runtime_config"]["tools.exec.sandbox"] == backend
    assert payload["requires_restart"]


def test_idle_compaction_settings_roundtrip_and_restart_contract(tmp_path):
    path = tmp_path / "config.json"
    config = Config()
    config.providers.openai.api_key = "${PRIVATE_API_KEY}"
    save_config(config, path)
    services = WebUISettingsServices.create(path)
    key = "agents.defaults.idle_compact_after_minutes"
    assert runtime_config_payload(config)[key] == 15

    for minutes in (0, 720, 721, 37, 15):
        payload = services.mutate(update_runtime_config_settings, {key: minutes})
        assert payload["runtime_config"][key] == minutes
        assert payload["requires_restart"] is True
        saved = load_config(path)
        assert saved.agents.defaults.idle_compact_after_minutes == minutes
        assert saved.agents.defaults.idle_compact_check_interval_seconds == 60
        assert saved.providers.openai.api_key == "${PRIVATE_API_KEY}"
        defaults = json.loads(path.read_text(encoding="utf-8"))["agents"]["defaults"]
        assert defaults["idleCompactAfterMinutes"] == minutes
        assert "sessionTtlMinutes" not in defaults
        assert "idle_compact_after_minutes" not in defaults

        unchanged = services.mutate(update_runtime_config_settings, {key: minutes})
        assert unchanged["runtime_config"][key] == minutes
        assert unchanged["requires_restart"] is False


def test_idle_compaction_config_can_be_read_and_updated(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"agents": {"defaults": {
        "idleCompactAfterMinutes": 720, "idleCompactCheckIntervalSeconds": 91,
    }}}), encoding="utf-8")
    key = "agents.defaults.idle_compact_after_minutes"
    assert runtime_config_payload(load_config(path))[key] == 720

    payload = update_runtime_config_settings({key: 0}, config_path=path)
    assert payload["runtime_config"][key] == 0
    assert payload["requires_restart"] is True
    saved = load_config(path)
    assert saved.agents.defaults.idle_compact_after_minutes == 0
    assert saved.agents.defaults.idle_compact_check_interval_seconds == 91
    defaults = json.loads(path.read_text(encoding="utf-8"))["agents"]["defaults"]
    assert defaults["idleCompactAfterMinutes"] == 0
    assert "sessionTtlMinutes" not in defaults


def test_default_workspace_and_approval_settings_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    save_config(Config(), path)
    workspace = tmp_path / "new-workspace"
    result = update_runtime_config_settings({
        "agents.defaults.workspace": str(workspace),
        "agents.defaults.approval.enabled": False,
        "agents.defaults.approval.timeout_seconds": 45,
    }, config_path=path)
    saved = load_config(path)
    assert saved.workspace_path == workspace
    assert saved.agents.defaults.approval.enabled is False
    assert saved.agents.defaults.approval.timeout_seconds == 45
    assert result["requires_restart"]
    assert not workspace.exists()  # A settings edit does not move or create task files.


def test_active_compaction_channel_delivery_and_command_silence_are_editable(tmp_path):
    path = tmp_path / 'config.json'
    save_config(Config(), path)
    values = {'agents.defaults.active_compact_percent': 75, 'channels.show_reasoning': False,
              'tools.exec.idle_timeout': 600, 'tools.exec.idle_action': 'terminate'}
    update_runtime_config_settings(values, config_path=path)
    loaded = load_config(path)
    assert loaded.agents.defaults.active_compact_percent == 75
    assert loaded.channels.show_reasoning is False
    assert loaded.tools.exec.idle_timeout == 600
    assert loaded.tools.exec.idle_action == 'terminate'
    before = path.read_bytes()
    with pytest.raises(WebUISettingsError):
        update_runtime_config_settings({'agents.defaults.active_compact_percent': 0}, config_path=path)
    assert path.read_bytes() == before
    with pytest.raises(WebUISettingsError):
        update_runtime_config_settings({'tools.exec.max_runtime_limit': 10}, config_path=path)
    assert path.read_bytes() == before

def test_embedding_settings_mask_preserve_rotate_and_clear_api_key():
    from cirno_server.webui.settings.runtime import runtime_config_payload, update_runtime_config
    config = Config()
    key = 'agents.defaults.memory.embedding_api_key'
    assert update_runtime_config(config, {key: 'private-value'})
    masked = runtime_config_payload(config)[key]
    assert masked != 'private-value' and masked
    assert not update_runtime_config(config, {key: masked})
    assert update_runtime_config(config, {key: 'replacement-value'})
    assert config.agents.defaults.memory.embedding_api_key == 'replacement-value'
    assert update_runtime_config(config, {key: ''})
    assert runtime_config_payload(config)[key] == ''


def test_unlimited_requested_command_duration_persists_and_accepts_long_default(tmp_path):
    path = tmp_path / "config.json"
    save_config(Config(), path)
    payload = update_runtime_config_settings({"tools.exec.max_runtime_limit": 0, "tools.exec.max_runtime": 172800}, config_path=path)
    assert payload["runtime_config"]["tools.exec.max_runtime_limit"] == 0
    reloaded = load_config(path)
    assert reloaded.tools.exec.max_runtime_limit == 0
    assert reloaded.tools.exec.max_runtime == 172800
    with pytest.raises(WebUISettingsError):
        update_runtime_config_settings({"tools.exec.max_runtime_limit": 60}, config_path=path)
    assert load_config(path).tools.exec.max_runtime_limit == 0


def test_setup_is_not_an_application_setting_or_saved_configuration(tmp_path):
    path = tmp_path / "config.json"
    config = Config.model_validate({"tools": {"startup": {"components": ["presets.rachebtms"]}}})
    save_config(config, path)
    assert "startup" not in json.loads(path.read_text())["tools"]
    before = path.read_bytes()
    with pytest.raises(WebUISettingsError):
        update_runtime_config_settings({"tools.startup.components": ["presets.rachebtms"]}, config_path=path)
    assert path.read_bytes() == before


def test_fixed_context_settings_are_saved_without_requiring_restart(tmp_path):
    from cirno_core.config.loader import save_config, load_config
    path = tmp_path / 'config.json'
    save_config(Config(), path)
    payload = update_runtime_config_settings({
        'agents.defaults.always_skills': ['paper-review'],
        'agents.defaults.memory.context_files': ['memory/research.md'],
        'agents.defaults.memory.context_files_tokens': 3072,
    }, config_path=path)
    assert not payload['requires_restart']
    config = load_config(path)
    assert config.agents.defaults.always_skills == ['paper-review']
    assert config.agents.defaults.memory.context_files == ['memory/research.md']
    assert config.agents.defaults.memory.context_files_tokens == 3072


@pytest.mark.parametrize("field", ["context_tokens", "context_files_tokens"])
def test_memory_injection_budget_limit_roundtrip(tmp_path, field):
    path = tmp_path / "config.json"
    save_config(Config(), path)
    key = f"agents.defaults.memory.{field}"
    payload = update_runtime_config_settings({key: 32768}, config_path=path)
    assert payload["runtime_config"][key] == 32768
    assert getattr(load_config(path).agents.defaults.memory, field) == 32768
    with pytest.raises(WebUISettingsError):
        update_runtime_config_settings({key: 32769}, config_path=path)
    assert getattr(load_config(path).agents.defaults.memory, field) == 32768
