"""MCP credentials behavior through the settings operations."""

from __future__ import annotations

import json

import pytest
from cirno_core.config.loader import load_config, save_config
from cirno_server.webui.mcp.actions import mcp_presets_action
from cirno_server.webui.mcp.contracts import McpPresetError

from .fixtures import _use_config


def test_enable_browserbase_writes_scrubbed_config_payload(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)

    payload = mcp_presets_action(
        "enable",
        {
            "name": ["browserbase"],
            "browserbase_api_key": ["bb_live_secret"],
        },
    )

    assert payload["requires_restart"] is True
    assert payload["last_action"]["ok"] is True
    assert payload["last_action"]["installed"] is True
    assert payload["last_action"]["verification"] == ["config_present"]
    preset = next(row for row in payload["presets"] if row["name"] == "browserbase")
    assert preset["installed"] is True
    assert preset["configured"] is True
    assert "bb_live_secret" not in str(payload)
    config = load_config()
    assert "browserbaseApiKey=bb_live_secret" in config.tools.mcp_servers["browserbase"].url


@pytest.mark.parametrize(
    ("name", "field", "header", "expected"),
    [
        ("deepnote", "deepnote_api_key", "Authorization", "Bearer preset-test-secret"),
        ("agentmail", "agentmail_api_key", "x-api-key", "preset-test-secret"),
    ],
)
def test_service_key_survives_reconnect_without_leaking_to_catalog(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    field: str,
    header: str,
    expected: str,
) -> None:
    _use_config(tmp_path, monkeypatch)
    payload = mcp_presets_action("enable", {"name": [name], field: ["preset-test-secret"]})
    assert load_config().tools.mcp_servers[name].headers[header] == expected
    assert "preset-test-secret" not in json.dumps(payload)

    config = load_config()
    config.tools.mcp_servers[name].enabled_tools = ["search"]
    config.tools.mcp_servers[name].tool_timeout = 90
    save_config(config)

    payload = mcp_presets_action("enable", {"name": [name]})
    saved = load_config().tools.mcp_servers[name]
    assert saved.headers[header] == expected
    assert saved.enabled_tools == ["search"]
    assert saved.tool_timeout == 90
    assert next(row for row in payload["presets"] if row["name"] == name)["configured"]


def test_service_bearer_key_resolves_environment_reference(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cirno_core.config.loader import resolve_config_env_vars

    _use_config(tmp_path, monkeypatch)
    monkeypatch.setenv("DEEPNOTE_API_KEY", "environment-test-secret")
    payload = mcp_presets_action("enable", {"name": ["deepnote"]})

    config = load_config()
    assert config.tools.mcp_servers["deepnote"].headers == {
        "Authorization": "Bearer ${DEEPNOTE_API_KEY}"
    }
    resolved = resolve_config_env_vars(config)
    assert resolved.tools.mcp_servers["deepnote"].headers == {
        "Authorization": "Bearer environment-test-secret"
    }
    assert "environment-test-secret" not in json.dumps(payload)


def test_account_endpoint_and_token_are_saved_together(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)
    payload = mcp_presets_action(
        "enable",
        {
            "name": ["datadog"],
            "mcp_url": ["https://mcp.example.com/datadog"],
            "datadog_access_token": ["datadog-test-secret"],
        },
    )

    saved = load_config().tools.mcp_servers["datadog"]
    assert saved.url == "https://mcp.example.com/datadog"
    assert saved.headers == {"Authorization": "Bearer datadog-test-secret"}
    row = next(item for item in payload["presets"] if item["name"] == "datadog")
    assert row["configured"] is True
    assert row["connection_summary"] == saved.url
    assert "datadog-test-secret" not in json.dumps(payload)


@pytest.mark.parametrize("from_environment", [False, True])
def test_redis_url_is_passed_to_cli_and_kept_secret(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    from_environment: bool,
) -> None:
    from cirno_core.config.loader import resolve_config_env_vars

    _use_config(tmp_path, monkeypatch)
    url = "rediss://default:redis-test-secret@cache.example.com:16380/3"
    query = {"name": ["redis"]}
    if from_environment:
        monkeypatch.setenv("REDIS_URL", url)
    else:
        query["redis_url"] = [url]

    payload = mcp_presets_action("enable", query)
    config = load_config()
    saved = config.tools.mcp_servers["redis"]
    assert saved.args == [
        "--from",
        "redis-mcp-server@latest",
        "redis-mcp-server",
        "--url",
        "${REDIS_URL}" if from_environment else url,
    ]
    resolved = resolve_config_env_vars(config)
    assert resolved.tools.mcp_servers["redis"].args[-1] == url
    row = next(item for item in payload["presets"] if item["name"] == "redis")
    assert row["configured"] is True
    assert row["required_fields"][0]["secret"] is True
    assert "redis-test-secret" not in json.dumps(payload)


def test_enable_requires_missing_secret(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_config(tmp_path, monkeypatch)

    with pytest.raises(McpPresetError) as exc:
        mcp_presets_action("enable", {"name": ["browserbase"]})

    assert exc.value.status == 400
    assert "Browserbase API key" in exc.value.message
