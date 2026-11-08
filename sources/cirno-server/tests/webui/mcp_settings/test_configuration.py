"""MCP configuration behavior through the settings operations."""

from __future__ import annotations

import json

import pytest
from cirno_core.config.loader import load_config, save_config
from cirno_server.webui.mcp.actions import mcp_presets_action
from cirno_server.webui.mcp.catalog import mcp_presets_payload
from cirno_server.webui.mcp.configuration import custom_mcp_action, ensure_mcp_oauth_server
from cirno_server.webui.mcp.contracts import McpPresetError

from .fixtures import _use_config


def test_custom_mcp_server_writes_config_and_catalog_row(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)

    payload = custom_mcp_action(
        "custom",
        {
            "name": ["internal-docs"],
            "transport": ["stdio"],
            "command": ["node"],
            "args": ['["server.js"]'],
            "env": ['{"DOCS_TOKEN":"docs-secret-value"}'],
            "tool_timeout": ["45"],
        },
    )

    assert payload["requires_restart"] is True
    row = next(item for item in payload["presets"] if item["name"] == "internal-docs")
    assert row["source"] == "custom"
    assert row["transport"] == "stdio"
    assert row["connection_summary"] == "node server.js"
    assert row["manifest"]["schema"] == "agent-app.v1"
    assert row["manifest"]["source"] == "mcp-custom"
    assert row["manifest"]["capabilities"][0]["command"] == "node"
    assert "server.js" not in str(row["manifest"])
    assert "docs-secret-value" not in str(payload)
    config = load_config()
    assert config.tools.mcp_servers["internal-docs"].args == ["server.js"]
    assert config.tools.mcp_servers["internal-docs"].env["DOCS_TOKEN"] == "docs-secret-value"


def test_import_mcp_config_and_tool_allowlist(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)

    payload = custom_mcp_action(
        "import",
        {
            "config": [
                (
                    '{"mcpServers":{'
                    '"docs":{"command":"npx","args":["-y","docs-mcp"],"env":{"API_KEY":"config-secret-value"}},'
                    '"remote-docs":{"transport":"sse","url":"https://example.com/sse"}'
                    "}}"
                )
            ],
        },
    )

    assert payload["last_action"]["message"] == "Imported 2 MCP server(s)."
    config = load_config()
    assert config.tools.mcp_servers["docs"].command == "npx"
    assert config.tools.mcp_servers["docs"].args == ["-y", "docs-mcp"]
    assert config.tools.mcp_servers["remote-docs"].type == "sse"
    assert config.tools.mcp_servers["remote-docs"].url == "https://example.com/sse"
    assert config.tools.mcp_servers["docs"].env["API_KEY"] == "config-secret-value"
    assert "config-secret-value" not in str(payload)

    payload = custom_mcp_action(
        "tools",
        {
            "name": ["docs"],
            "enabled_tools": ['["mcp_docs_search"]'],
        },
    )

    row = next(item for item in payload["presets"] if item["name"] == "docs")
    assert row["enabled_tools"] == ["mcp_docs_search"]
    assert load_config().tools.mcp_servers["docs"].enabled_tools == ["mcp_docs_search"]

    payload = custom_mcp_action(
        "tools",
        {
            "name": ["docs"],
            "enabled_tools": ["[]"],
        },
    )

    row = next(item for item in payload["presets"] if item["name"] == "docs")
    assert row["enabled_tools"] == []
    assert load_config().tools.mcp_servers["docs"].enabled_tools == []


def test_import_recognizes_known_and_explicit_oauth_servers(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)

    payload = custom_mcp_action(
        "import",
        {
            "config": [
                (
                    '{"mcpServers":{'
                    '"notion-work":{"url":"https://mcp.notion.com/mcp"},'
                    '"company-mcp":{"url":"https://mcp.example.com/mcp","auth":"oauth"},'
                    '"notion-pat":{"url":"https://mcp.notion.com/mcp",'
                    '"headers":{"Authorization":"Bearer secret"}}'
                    "}}"
                )
            ],
        },
    )

    config = load_config()
    assert config.tools.mcp_servers["notion-work"].auth == "oauth"
    assert config.tools.mcp_servers["company-mcp"].auth == "oauth"
    assert config.tools.mcp_servers["notion-pat"].auth is None
    rows = {row["name"]: row for row in payload["presets"]}
    assert rows["notion-work"]["status"] == "authorization_required"
    assert rows["company-mcp"]["status"] == "authorization_required"
    assert rows["notion-pat"]["status"] == "configured"
    assert "Bearer secret" not in str(payload)


@pytest.mark.parametrize("transport", ["sse", "streamableHttp"])
def test_custom_server_saves_explicit_proxy_flag(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    transport: str,
) -> None:
    _use_config(tmp_path, monkeypatch)
    config = load_config()
    config.network.proxy = "http://shared.example:8080"
    save_config(config)
    payload = custom_mcp_action(
        "custom",
        {
            "name": ["company-docs"],
            "transport": [transport],
            "url": ["https://docs.example.com/mcp"],
            "use_proxy": ["true"],
        },
    )
    assert load_config().tools.mcp_servers["company-docs"].use_proxy is True
    assert (
        next(row for row in payload["presets"] if row["name"] == "company-docs")["use_proxy"]
        is True
    )


@pytest.mark.parametrize("use_proxy", [False, True])
def test_import_preserves_boolean_proxy_flag(tmp_path, monkeypatch, use_proxy: bool) -> None:
    _use_config(tmp_path, monkeypatch)
    config = load_config()
    config.network.proxy = "http://shared.example:8080"
    save_config(config)
    custom_mcp_action(
        "import",
        {
            "config": [
                json.dumps(
                    {
                        "mcpServers": {
                            "company-docs": {
                                "url": "https://docs.example.com/mcp",
                                "useProxy": use_proxy,
                            },
                        }
                    }
                )
            ]
        },
    )
    assert load_config().tools.mcp_servers["company-docs"].use_proxy is use_proxy


@pytest.mark.parametrize("invalid", ["true", "false", 1, None])
def test_import_rejects_nonboolean_proxy_flag_without_saving(
    tmp_path, monkeypatch, invalid
) -> None:
    _use_config(tmp_path, monkeypatch)
    with pytest.raises(McpPresetError, match="useProxy must be a boolean"):
        custom_mcp_action(
            "import",
            {
                "config": [
                    json.dumps(
                        {
                            "mcpServers": {
                                "valid-first": {"url": "https://docs.example.com/mcp"},
                                "bad-flag": {
                                    "url": "https://docs.example.com/mcp",
                                    "useProxy": invalid,
                                },
                            }
                        }
                    )
                ]
            },
        )
    assert load_config().tools.mcp_servers == {}


@pytest.mark.parametrize("action", ["enable", "proxy", "oauth", "custom", "import"])
def test_explicit_proxy_requires_shared_address_before_saving(
    tmp_path, monkeypatch, action
) -> None:
    _use_config(tmp_path, monkeypatch)
    with pytest.raises(McpPresetError, match="Configure the shared proxy"):
        if action == "oauth":
            ensure_mcp_oauth_server({"name": ["xmind"], "use_proxy": ["true"]})
        elif action == "custom":
            custom_mcp_action(
                "custom",
                {
                    "name": ["company-docs"],
                    "url": ["https://docs.example.com/mcp"],
                    "use_proxy": ["true"],
                },
            )
        elif action == "import":
            custom_mcp_action(
                "import",
                {
                    "config": [
                        json.dumps(
                            {
                                "company-docs": {
                                    "url": "https://docs.example.com/mcp",
                                    "useProxy": True,
                                },
                            }
                        )
                    ]
                },
            )
        else:
            mcp_presets_action(action, {"name": ["xmind"], "use_proxy": ["true"]})
    assert load_config().tools.mcp_servers == {}
    assert mcp_presets_payload()["proxy_configured"] is False


@pytest.mark.parametrize(
    "server",
    [
        {
            "type": "stdio",
            "command": "node",
            "args": ["server.js", "two words"],
            "env": {"KEY": "${TOKEN}"},
            "cwd": "/tmp/mcp",
            "toolTimeout": 90,
            "enabledTools": ["search"],
        },
        {
            "type": "streamableHttp",
            "url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer test-secret"},
            "toolTimeout": 45,
            "enabledTools": [],
        },
        {"type": "sse", "url": "https://example.com/sse", "auth": "oauth", "enabledTools": ["*"]},
    ],
)
def test_custom_mcp_edit_roundtrip_preserves_connection_fields(tmp_path, server):
    from cirno_server.webui.mcp.catalog import custom_mcp_config_payload

    path = tmp_path / "instance" / "config.json"
    custom_mcp_action(
        "import",
        {"config": [json.dumps({"mcpServers": {"custom-docs": server}})]},
        config_path=path,
    )
    before = load_config(path).tools.mcp_servers["custom-docs"]
    editable = custom_mcp_config_payload("custom-docs", config_path=path)["config"]
    editable["toolTimeout"] = 120
    custom_mcp_action(
        "import",
        {"config": [json.dumps({"mcpServers": {"custom-docs": editable}})]},
        config_path=path,
    )
    after = load_config(path).tools.mcp_servers["custom-docs"]
    assert after == before.model_copy(update={"tool_timeout": 120})
    with pytest.raises(McpPresetError, match="unknown custom MCP server"):
        custom_mcp_config_payload("missing", config_path=path)
