"""Isolated configuration and plugin fixtures for MCP settings acceptance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cirno_core.agent.plugins import AGENT_PLUGIN_MCP_SCHEMA, AGENT_PLUGIN_SCHEMA


def _use_config(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"agents": {"defaults": {"workspace": str(tmp_path / "workspace")}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("cirno_core.config.loader._current_config_path", config_path)


def _write_agent_plugin(workspace: Path) -> None:
    root = workspace / "plugins" / "desktop"
    root.mkdir(parents=True)
    for filename, payload in (
        (
            "plugin.json",
            {
                "$schema": AGENT_PLUGIN_SCHEMA,
                "name": "desktop",
                "description": "Control the local desktop.",
                "extensions": {
                    "dev.cirno": {
                        "displayName": "Desktop Control",
                        "permissions": ["screen-recording"],
                    }
                },
            },
        ),
        (
            "mcp.json",
            {
                "$schema": AGENT_PLUGIN_MCP_SCHEMA,
                "mcpServers": {"desktop": {"type": "stdio", "command": "echo"}},
            },
        ),
    ):
        (root / filename).write_text(json.dumps(payload), encoding="utf-8")
