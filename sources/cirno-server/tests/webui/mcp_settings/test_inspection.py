"""MCP inspection behavior through the settings operations."""

from __future__ import annotations

import asyncio

import pytest
from cirno_core.config.loader import load_config, save_config
from cirno_server.webui.mcp.actions import mcp_presets_action
from cirno_server.webui.mcp.inspection import mcp_presets_test_action

from .fixtures import _use_config


def test_test_mcp_preset_reports_missing_dependency(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)
    mcp_presets_action("enable", {"name": ["playwright"]})
    monkeypatch.setattr("cirno_server.webui.mcp.fields.shutil.which", lambda _command: None)

    payload = asyncio.run(mcp_presets_test_action({"name": ["playwright"]}))

    assert payload["last_action"]["ok"] is False
    assert "npx" in payload["last_action"]["message"]


def test_test_mcp_preset_connects_and_reports_tools(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)
    mcp_presets_action("enable", {"name": ["playwright"]})

    class FakeStack:
        async def aclose(self) -> None:
            return None

    async def fake_connect(servers, registry, *, network):
        assert list(servers) == ["playwright"]

        class FakeTool:
            name = "mcp_playwright_browser_navigate"

            def to_schema(self):
                return {"name": self.name, "description": "", "parameters": {}}

        registry.register(FakeTool())
        return {"playwright": FakeStack()}

    monkeypatch.setattr(
        "cirno_server.webui.mcp.inspection.command_available", lambda _command: True
    )
    monkeypatch.setattr("cirno_core.agent.tools.mcp.connector.connect_mcp_servers", fake_connect)

    payload = asyncio.run(mcp_presets_test_action({"name": ["playwright"]}))

    assert payload["last_action"]["ok"] is True
    assert payload["last_action"]["tool_count"] == 1
    assert payload["last_action"]["tool_names"] == ["mcp_playwright_browser_navigate"]


def test_test_mcp_preset_inspects_tools_outside_the_enabled_allowlist(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)
    mcp_presets_action("enable", {"name": ["playwright"]})
    config = load_config()
    config.tools.mcp_servers["playwright"].enabled_tools = [
        "mcp_playwright_browser_navigate",
    ]
    save_config(config)

    class FakeStack:
        async def aclose(self) -> None:
            return None

    async def fake_connect(servers, registry, *, network):
        assert servers["playwright"].enabled_tools == ["*"]

        class FakeTool:
            def __init__(self, name: str) -> None:
                self.name = name

            def to_schema(self):
                return {"name": self.name, "description": "", "parameters": {}}

        for index in range(20):
            registry.register(FakeTool(f"mcp_playwright_tool_{index:02d}"))
        return {"playwright": FakeStack()}

    monkeypatch.setattr(
        "cirno_server.webui.mcp.inspection.command_available", lambda _command: True
    )
    monkeypatch.setattr("cirno_core.agent.tools.mcp.connector.connect_mcp_servers", fake_connect)

    payload = asyncio.run(mcp_presets_test_action({"name": ["playwright"]}))

    assert payload["last_action"]["tool_count"] == 20
    assert len(payload["last_action"]["tool_names"]) == 20
    row = next(item for item in payload["presets"] if item["name"] == "playwright")
    assert row["enabled_tools"] == ["mcp_playwright_browser_navigate"]


def test_test_mcp_preset_scrubs_connection_errors(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_config(tmp_path, monkeypatch)
    mcp_presets_action(
        "enable",
        {
            "name": ["browserbase"],
            "browserbase_api_key": ["bb_live_secret"],
        },
    )

    async def fake_connect(_servers, _registry, *, network):
        raise RuntimeError(
            "failed https://mcp.browserbase.com/mcp?browserbaseApiKey=bb_live_secret"
        )

    monkeypatch.setattr(
        "cirno_server.webui.mcp.inspection.command_available", lambda _command: True
    )
    monkeypatch.setattr("cirno_core.agent.tools.mcp.connector.connect_mcp_servers", fake_connect)

    payload = asyncio.run(mcp_presets_test_action({"name": ["browserbase"]}))

    assert payload["last_action"]["ok"] is False
    assert "bb_live_secret" not in str(payload)
    assert "<redacted>" in payload["last_action"]["error"]
