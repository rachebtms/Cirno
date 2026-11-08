"""Inspection failures must reach the owner without exposing credentials."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cirno_core.config.errors import ConfigLoadError
from cirno_core.config.loader import save_config
from cirno_core.config.schema import Config
from cirno_core.config.tools import MCPServerConfig
from cirno_server.webui.mcp.inspection import mcp_presets_test_action
from cirno_server.webui.mcp.mentions import normalize_mcp_preset_mentions


def test_config_errors_do_not_silently_remove_custom_mcp_mentions(tmp_path):
    config = tmp_path / "config.json"
    config.write_text("{")
    with pytest.raises(ConfigLoadError):
        normalize_mcp_preset_mentions([{"name": "custom-docs"}], config_path=config)
    assert config.read_text() == "{"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["error", "transport_cancelled"])
async def test_inspection_reports_cleanup_failure_and_closes_remaining_connections(
    tmp_path, monkeypatch, failure
):
    path = tmp_path / "config.json"
    config = Config()
    config.tools.mcp_servers["custom-docs"] = MCPServerConfig(command="fixture-mcp")
    save_config(config, path)
    exception = (
        OSError("close failed: token=private-token")
        if failure == "error"
        else asyncio.CancelledError()
    )
    broken = SimpleNamespace(aclose=AsyncMock(side_effect=exception))
    healthy = SimpleNamespace(aclose=AsyncMock())

    async def connect(_servers, _registry, **_kwargs):
        return {"custom-docs": broken, "another": healthy}

    monkeypatch.setattr(
        "cirno_server.webui.mcp.inspection.command_available", lambda _command: True
    )
    monkeypatch.setattr("cirno_core.agent.tools.mcp.connector.connect_mcp_servers", connect)
    payload = await mcp_presets_test_action({"name": ["custom-docs"]}, config_path=path)
    broken.aclose.assert_awaited_once()
    healthy.aclose.assert_awaited_once()
    assert payload["last_action"]["ok"] is False
    assert "cleanup failed" in payload["last_action"]["message"]
    assert "custom-docs" in payload["last_action"]["error"]
    assert "private-token" not in str(payload)
