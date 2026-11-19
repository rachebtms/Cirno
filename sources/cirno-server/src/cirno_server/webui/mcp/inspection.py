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
from cirno_core.config.loader import get_config_path, load_config, resolve_config_env_vars
from cirno_core.config.schema import Config
from cirno_core.config.tools import MCPServerConfig
from cirno_core.utils.cancellation import shield_and_drain

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
from cirno_server.webui.mcp.presets import McpPreset

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


def _render_inspection_payload(
    name: str, *, last_action: dict[str, Any], config_path: Path | None,
    expected_config: Config | None = None,
) -> dict[str, Any]:
    """Keep an observed empty inventory distinct from an uninspected catalog row."""
    snapshot = load_config(config_path)
    stale = False
    if expected_config is not None:
        before = expected_config.tools.mcp_servers.get(name)
        try:
            current = resolve_config_env_vars(snapshot, config_path=config_path)
            after = current.tools.mcp_servers.get(name)
            stale = (
                before is None or after is None
                or before.model_dump(exclude={"enabled_tools"}) != after.model_dump(exclude={"enabled_tools"})
                or (before.use_proxy and expected_config.network.proxy != current.network.proxy)
            )
        except ValueError:
            stale = True
        if stale:
            last_action = {
                "ok": False,
                "message": "MCP connection changed during inspection. Test the current connection again.",
                "error": "Connection changed; test again.",
                "inventory_stale": True,
                "tool_names": [], "tool_count": 0,
                "checked_at": last_action["checked_at"],
            }
    payload = mcp_presets_payload(
        last_action=last_action,
        tool_preview={name: last_action.get("tool_names", [])},
        config_path=config_path,
        config_snapshot=snapshot,
    )
    for row in payload["presets"]:
        if row.get("name") == name:
            row.update({key: last_action[key] for key in ("tool_names", "tool_count", "checked_at")})
            if last_action.get("error"):
                row["error"] = last_action["error"]
            if stale:
                row["inventory_stale"] = True
    return payload


async def _inspection_payload(
    name: str, *, last_action: dict[str, Any], config_path: Path,
    expected_config: Config | None = None,
) -> dict[str, Any]:
    # Catalog discovery can materialize plugin data directories. Do not leave
    # that accepted filesystem work outside the cancelled request's lifetime.
    return await shield_and_drain(asyncio.to_thread(
        _render_inspection_payload, name, last_action=last_action, config_path=config_path,
        expected_config=expected_config,
    ))


def _prepare_inspection(name: str, preset: McpPreset | None, config_path: Path) -> tuple[Config, MCPServerConfig, str, bool]:
    config = resolve_config_env_vars(load_config(config_path), config_path=config_path)
    cfg = config.tools.mcp_servers.get(name)
    if cfg is None:
        raise McpPresetError(f"{display_name_for(name, preset)} is not enabled", status=404)
    command_found = cfg.transport_type != "stdio" or command_available(cfg.command, cwd=cfg.cwd, env=cfg.env)
    status = (
        status_for(preset, cfg, config_path=config.source_path)
        if preset is not None
        else ("configured" if command_found else "missing_dependency")
    )
    return config, cfg, status, command_found


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
    config_path = config_path if config_path is not None else get_config_path()

    try:
        config, cfg, status, command_found = await shield_and_drain(asyncio.to_thread(
            _prepare_inspection, name, preset, config_path,
        ))
    except ValueError as exc:
        return await _inspection_payload(
            name,
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

    config_path = config.source_path or config_path
    if status == "missing_credentials":
        last_action: dict[str, Any] = {
            "ok": False,
            "message": f"{display_name} is missing required credentials.",
            "error": "missing credentials",
            "tool_count": 0,
            "tool_names": [],
            "checked_at": _checked_at(),
        }
        return await _inspection_payload(
            name, last_action=last_action, config_path=config_path, expected_config=config,
        )

    if not command_found:
        last_action = {
            "ok": False,
            "message": f"{display_name} requires '{cfg.command}' on PATH.",
            "error": "missing dependency",
            "tool_count": 0,
            "tool_names": [],
            "checked_at": _checked_at(),
        }
        return await _inspection_payload(
            name, last_action=last_action, config_path=config_path, expected_config=config,
        )

    registry = ToolRegistry()
    stacks: dict[str, MCPConnection] = {}
    inspection_cfg = cfg.model_copy(update={"enabled_tools": ["*"]})
    try:
        stacks = await asyncio.wait_for(
            connect_mcp_servers({name: inspection_cfg}, registry, network=config.network, config_path=config.source_path),
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

    return await _inspection_payload(
        name,
        last_action=last_action,
        config_path=config_path,
        expected_config=config,
    )
