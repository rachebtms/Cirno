"""Inspect one MCP server with the runtime's shared connection lifecycle."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cirno_core.agent.tools.mcp.connections import close_mcp_connections
from cirno_core.agent.tools.mcp.contracts import MCPConnection
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.config.loader import load_config, resolve_config_env_vars
from cirno_core.config.tools import MCPServerConfig
from cirno_server.webui.mcp.catalog import mcp_presets_payload
from cirno_server.webui.mcp.contracts import (
    MCP_SERVER_NAME_RE,
    McpPresetError,
    QueryParams,
    display_name_for,
    preset_by_name_optional,
    query_first,
)
from cirno_server.webui.mcp.fields import command_available, status_for

_DEFAULT_TEST_TIMEOUT = 20
_SECRET_QUERY_RE = re.compile(
    r"([?&](?:[^=&]*(?:api[_-]?key|token|secret|password|bearer)[^=&]*)=)[^&#\s]+",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"((?:api[_-]?key|token|secret|password|bearer)(?:[=:]|\s+))[^,\s'\"&]+",
    re.IGNORECASE,
)


def _scrub_test_error(text: str) -> str:
    scrubbed = _SECRET_QUERY_RE.sub(r"\1<redacted>", text.strip())
    scrubbed = _SECRET_ASSIGNMENT_RE.sub(r"\1<redacted>", scrubbed)
    return scrubbed[:400] if scrubbed else "Connection failed."


def _checked_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _test_timeout(cfg: MCPServerConfig) -> int:
    raw = cfg.tool_timeout or _DEFAULT_TEST_TIMEOUT
    return max(5, min(int(raw), _DEFAULT_TEST_TIMEOUT))


async def mcp_presets_test_action(
    query: QueryParams,
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Connect to an enabled MCP preset and report its complete tool surface."""
    from cirno_core.agent.tools.mcp.connector import connect_mcp_servers

    name = (query_first(query, "name") or "").strip()
    if not name:
        raise McpPresetError("missing MCP preset name")
    if MCP_SERVER_NAME_RE.match(name) is None:
        raise McpPresetError("invalid MCP server name")
    preset = preset_by_name_optional(name)
    display_name = display_name_for(name, preset)

    try:
        config = resolve_config_env_vars(
            load_config(config_path) if config_path is not None else load_config(),
            config_path=config_path,
        )
    except ValueError as exc:
        return mcp_presets_payload(
            last_action={
                "ok": False,
                "message": _scrub_test_error(str(exc)),
                "error": _scrub_test_error(str(exc)),
                "tool_count": 0,
                "tool_names": [],
                "checked_at": _checked_at(),
            },
            config_path=config_path,
        )

    cfg = config.tools.mcp_servers.get(name)
    if cfg is None:
        raise McpPresetError(f"{display_name} is not enabled", status=404)

    status = (
        status_for(preset, cfg)
        if preset is not None
        else (
            "missing_dependency"
            if cfg.command and not command_available(cfg.command)
            else "configured"
        )
    )
    if status == "missing_credentials":
        last_action: dict[str, Any] = {
            "ok": False,
            "message": f"{display_name} is missing required credentials.",
            "error": "missing credentials",
            "tool_count": 0,
            "tool_names": [],
            "checked_at": _checked_at(),
        }
        return mcp_presets_payload(last_action=last_action, config_path=config_path)

    if cfg.command and not command_available(cfg.command):
        last_action = {
            "ok": False,
            "message": f"{display_name} requires '{cfg.command}' on PATH.",
            "error": "missing dependency",
            "tool_count": 0,
            "tool_names": [],
            "checked_at": _checked_at(),
        }
        return mcp_presets_payload(last_action=last_action, config_path=config_path)

    registry = ToolRegistry()
    stacks: dict[str, MCPConnection] = {}
    inspection_cfg = cfg.model_copy(update={"enabled_tools": ["*"]})
    try:
        stacks = await asyncio.wait_for(
            connect_mcp_servers({name: inspection_cfg}, registry, network=config.network),
            timeout=_test_timeout(cfg),
        )
        tool_names = sorted(registry.tool_names)
        ok = name in stacks
        if ok:
            last_action = {
                "ok": True,
                "message": (
                    f"{display_name} connected with {len(tool_names)} tools."
                    if tool_names
                    else f"{display_name} connected, but reported no tools."
                ),
                "tool_count": len(tool_names),
                "tool_names": tool_names,
                "checked_at": _checked_at(),
            }
        else:
            last_action = {
                "ok": False,
                "message": f"{display_name} did not complete an MCP handshake.",
                "error": "MCP handshake failed",
                "tool_count": 0,
                "tool_names": [],
                "checked_at": _checked_at(),
            }
    except asyncio.TimeoutError:
        last_action = {
            "ok": False,
            "message": f"{display_name} test timed out.",
            "error": "timeout",
            "tool_count": 0,
            "tool_names": [],
            "checked_at": _checked_at(),
        }
    except Exception as exc:
        error = _scrub_test_error(str(exc))
        last_action = {
            "ok": False,
            "message": f"{display_name} could not connect.",
            "error": error,
            "tool_count": 0,
            "tool_names": [],
            "checked_at": _checked_at(),
        }
    finally:
        cleanup_errors = await close_mcp_connections(stacks)

    if cleanup_errors:
        error = _scrub_test_error(
            "; ".join(f"{name}: {failure}" for name, failure in cleanup_errors.items())
        )
        last_action.update(
            ok=False, error=error, message=f"{display_name} connection cleanup failed: {error}"
        )

    tool_names = last_action.get("tool_names", [])
    preview = {name: tool_names} if tool_names else None
    return mcp_presets_payload(
        last_action=last_action,
        tool_preview=preview,
        config_path=config_path,
    )
