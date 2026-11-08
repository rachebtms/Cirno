"""MCP preset lifecycle behavior through the settings operations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cirno_core.config.loader import load_config, save_config
from cirno_server.webui.mcp.actions import mcp_presets_action
from cirno_server.webui.mcp.configuration import custom_mcp_action

from .fixtures import _use_config


def test_google_workspace_uses_managed_stdio_and_environment_credentials(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)
    payload = mcp_presets_action(
        "enable",
        {
            "name": ["google-workspace"],
            "google_client_id": ["test.apps.googleusercontent.com"],
            "google_client_secret": ["google-test-secret"],
        },
    )

    saved = load_config().tools.mcp_servers["google-workspace"]
    assert saved.command == "uvx"
    assert saved.args == ["workspace-mcp", "--transport", "stdio", "--tool-tier", "core"]
    assert saved.env == {
        "GOOGLE_OAUTH_CLIENT_ID": "test.apps.googleusercontent.com",
        "GOOGLE_OAUTH_CLIENT_SECRET": "google-test-secret",
    }
    assert Path(saved.cwd) == tmp_path / "state" / "mcp" / "google-workspace"
    assert "google-test-secret" not in json.dumps(payload)


def test_enable_context7_optional_api_key_appends_arg(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)

    payload = mcp_presets_action(
        "enable",
        {
            "name": ["context7"],
            "context7_api_key": ["ctx7_secret"],
        },
    )

    assert "ctx7_secret" not in str(payload)
    row = next(item for item in payload["presets"] if item["name"] == "context7")
    assert row["configured"] is True
    config = load_config()
    assert config.tools.mcp_servers["context7"].args == [
        "-y",
        "@upstash/context7-mcp@latest",
        "--api-key",
        "ctx7_secret",
    ]


def test_enable_stdio_preset_uses_config_scoped_cwd(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)

    mcp_presets_action("enable", {"name": ["playwright"]})

    config = load_config()
    cwd = config.tools.mcp_servers["playwright"].cwd
    assert cwd == str(tmp_path / "state" / "mcp" / "playwright")
    assert (tmp_path / "state" / "mcp" / "playwright").is_dir()


def test_enable_no_auth_remote_presets_write_url(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_config(tmp_path, monkeypatch)

    mcp_presets_action("enable", {"name": ["microsoft-learn"]})
    mcp_presets_action("enable", {"name": ["exa"]})
    mcp_presets_action("enable", {"name": ["firecrawl"]})
    mcp_presets_action("enable", {"name": ["parallel-search"]})

    config = load_config()
    assert config.tools.mcp_servers["microsoft-learn"].url == "https://learn.microsoft.com/api/mcp"
    assert config.tools.mcp_servers["exa"].url == "https://mcp.exa.ai/mcp"
    assert config.tools.mcp_servers["firecrawl"].url == "https://mcp.firecrawl.dev/v2/mcp"
    assert config.tools.mcp_servers["parallel-search"].url == "https://search.parallel.ai/mcp"


def test_firecrawl_preset_is_keyless(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_config(tmp_path, monkeypatch)

    payload = mcp_presets_action("enable", {"name": ["firecrawl"]})

    row = next(item for item in payload["presets"] if item["name"] == "firecrawl")
    assert row["transport"] == "streamableHttp"
    assert row["requires"] == "Network access"
    assert row["required_fields"] == []
    assert row["configured"] is True
    assert "Keyless" in row["note"]
    config = load_config()
    assert config.tools.mcp_servers["firecrawl"].type == "streamableHttp"
    assert config.tools.mcp_servers["firecrawl"].url == "https://mcp.firecrawl.dev/v2/mcp"
    assert config.tools.mcp_servers["firecrawl"].env == {}


def test_parallel_search_preset_is_keyless_and_tool_limited(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)

    payload = mcp_presets_action("enable", {"name": ["parallel-search"]})

    row = next(item for item in payload["presets"] if item["name"] == "parallel-search")
    assert row["transport"] == "streamableHttp"
    assert row["requires"] == "Network access"
    assert row["required_fields"] == []
    assert row["configured"] is True
    assert "no API key" in row["note"]
    config = load_config()
    server = config.tools.mcp_servers["parallel-search"]
    assert server.type == "streamableHttp"
    assert server.url == "https://search.parallel.ai/mcp"
    assert server.enabled_tools == ["web_search", "web_fetch"]
    assert server.headers == {}


def test_remove_mcp_preset_updates_config(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_config(tmp_path, monkeypatch)
    mcp_presets_action("enable", {"name": ["playwright"]})
    managed_cwd = tmp_path / "state" / "mcp" / "playwright"
    (managed_cwd / "cache.txt").write_text("managed runtime data", encoding="utf-8")

    payload = mcp_presets_action("remove", {"name": ["playwright"]})

    assert payload["requires_restart"] is True
    assert payload["last_action"]["ok"] is True
    assert payload["last_action"]["removed"] is True
    assert payload["last_action"]["managed_paths_removed"] == ["runtime:mcp/playwright"]
    assert not managed_cwd.exists()
    config = load_config()
    assert "playwright" not in config.tools.mcp_servers


def test_remove_custom_mcp_server_preserves_user_cwd(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_config(tmp_path, monkeypatch)
    user_cwd = tmp_path / "user-cwd"
    user_cwd.mkdir()
    custom_mcp_action(
        "custom",
        {
            "name": ["internal-docs"],
            "transport": ["stdio"],
            "command": ["node"],
            "args": ['["server.js"]'],
            "cwd": [str(user_cwd)],
        },
    )

    payload = mcp_presets_action("remove", {"name": ["internal-docs"]})

    assert payload["last_action"]["ok"] is True
    assert user_cwd.exists()
    config = load_config()
    assert "internal-docs" not in config.tools.mcp_servers


@pytest.mark.parametrize("name", ["xmind", "custom-docs"])
def test_proxy_action_preserves_existing_server_and_materializes_presets(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    _use_config(tmp_path, monkeypatch)
    config = load_config()
    config.network.proxy = "http://shared.example:8080"
    save_config(config)
    if name == "custom-docs":
        custom_mcp_action(
            "custom",
            {
                "name": [name],
                "url": ["https://docs.example.com/mcp"],
                "headers": ['{"Authorization": "Bearer preserved-secret"}'],
                "enabled_tools": ['["search"]'],
                "tool_timeout": ["90"],
            },
        )

    payload = mcp_presets_action("proxy", {"name": [name], "use_proxy": ["true"]})
    before = load_config().tools.mcp_servers[name]
    assert before.use_proxy is True
    assert payload["requires_restart"] is True
    assert next(row for row in payload["presets"] if row["name"] == name)["use_proxy"] is True

    mcp_presets_action("proxy", {"name": [name], "use_proxy": ["false"]})
    after = load_config().tools.mcp_servers[name]
    assert after.use_proxy is False
    assert after.model_dump(exclude={"use_proxy"}) == before.model_dump(exclude={"use_proxy"})
    if name == "custom-docs":
        assert after.headers == {"Authorization": "Bearer preserved-secret"}
        assert after.enabled_tools == ["search"]
        assert after.tool_timeout == 90


def test_enable_preset_preserves_proxy_choice_on_later_enable(tmp_path, monkeypatch) -> None:
    _use_config(tmp_path, monkeypatch)
    config = load_config()
    config.network.proxy = "http://shared.example:8080"
    save_config(config)

    mcp_presets_action("enable", {"name": ["xmind"], "use_proxy": ["true"]})
    assert load_config().tools.mcp_servers["xmind"].use_proxy is True
    mcp_presets_action("enable", {"name": ["xmind"]})
    assert load_config().tools.mcp_servers["xmind"].use_proxy is True
    mcp_presets_action("enable", {"name": ["xmind"], "use_proxy": ["false"]})
    assert load_config().tools.mcp_servers["xmind"].use_proxy is False
