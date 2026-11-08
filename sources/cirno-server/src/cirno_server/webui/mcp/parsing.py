"""Validate custom MCP configuration and imports without mutating settings."""

from __future__ import annotations

import json
import shlex
from typing import Any, Literal, Mapping, cast

from cirno_core.config.tools import MCPServerConfig
from cirno_server.webui.mcp.contracts import (
    McpPresetError,
    QueryParams,
    query_first,
    validated_server_name,
)
from cirno_server.webui.mcp.fields import proxy_enabled
from cirno_server.webui.mcp.presets import MCP_PRESETS

_DEFAULT_CUSTOM_TIMEOUT = 30


def _parse_json_value(raw: str | None, *, fallback: Any) -> Any:
    if raw is None or not raw.strip():
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise McpPresetError(f"invalid JSON: {exc.msg}") from exc


def _parse_string_list(raw: str | None) -> list[str]:
    if raw is None or not raw.strip():
        return []
    parsed = _parse_json_value(raw, fallback=None)
    if isinstance(parsed, list):
        items = cast(list[object], parsed)
        if all(isinstance(item, str) for item in items):
            return [item for item in cast(list[str], items) if item.strip()]
    if isinstance(parsed, str):
        return shlex.split(parsed)
    raise McpPresetError("expected a JSON string array")


def _parse_string_map(raw: str | None) -> dict[str, str]:
    parsed = _parse_json_value(raw, fallback={})
    if not isinstance(parsed, dict):
        raise McpPresetError("expected a JSON object")
    out: dict[str, str] = {}
    for key, value in cast(dict[object, object], parsed).items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise McpPresetError("JSON object values must be strings")
        if key.strip():
            out[key.strip()] = value
    return out


def parse_enabled_tools(raw: str | None) -> list[str]:
    if raw is None or not raw.strip():
        return ["*"]
    values = _parse_string_list(raw)
    if "*" in values:
        return ["*"]
    return values


def _normalize_transport(
    value: str | None, *, command: str = "", url: str = ""
) -> Literal["stdio", "sse", "streamableHttp"]:
    raw = (value or "").strip()
    if not raw:
        if command:
            return "stdio"
        if url.rstrip("/").endswith("/sse"):
            return "sse"
        return "streamableHttp"
    aliases: dict[str, Literal["stdio", "sse", "streamableHttp"]] = {
        "stdio": "stdio",
        "sse": "sse",
        "streamableHttp": "streamableHttp",
        "streamable-http": "streamableHttp",
        "streamable_http": "streamableHttp",
        "http": "streamableHttp",
    }
    normalized = aliases.get(raw)
    if normalized is None:
        raise McpPresetError("unsupported MCP transport")
    return normalized


def _normalize_auth(
    value: object,
    *,
    transport: Literal["stdio", "sse", "streamableHttp"],
    url: str,
    headers: Mapping[str, str],
) -> Literal["oauth"] | None:
    raw = str(value or "").strip().lower()
    if not raw and url and not headers:
        normalized_url = url.rstrip("/")
        if any(
            preset.server is not None
            and preset.server.auth == "oauth"
            and preset.server.url.rstrip("/") == normalized_url
            for preset in MCP_PRESETS
        ):
            raw = "oauth"
    if not raw:
        return None
    if raw != "oauth":
        raise McpPresetError("unsupported MCP auth type")
    if transport == "stdio":
        raise McpPresetError("MCP OAuth requires a remote HTTP transport")
    return "oauth"


def custom_server_from_query(query: QueryParams) -> tuple[str, MCPServerConfig]:
    name = validated_server_name((query_first(query, "name") or "").strip())
    command = (query_first(query, "command") or "").strip()
    url = (query_first(query, "url") or "").strip()
    transport = _normalize_transport(query_first(query, "transport"), command=command, url=url)
    if transport == "stdio" and not command:
        raise McpPresetError("stdio MCP servers require a command")
    if transport in {"sse", "streamableHttp"} and not url:
        raise McpPresetError("remote MCP servers require a URL")
    headers = _parse_string_map(query_first(query, "headers"))
    auth = _normalize_auth(
        query_first(query, "auth"),
        transport=transport,
        url=url,
        headers=headers,
    )
    raw_timeout = (query_first(query, "tool_timeout") or "").strip()
    tool_timeout = _DEFAULT_CUSTOM_TIMEOUT
    if raw_timeout:
        try:
            tool_timeout = max(5, min(int(raw_timeout), 600))
        except ValueError as exc:
            raise McpPresetError("tool_timeout must be an integer") from exc
    cfg = MCPServerConfig(
        type=transport,
        auth=auth,
        command=command if transport == "stdio" else "",
        args=_parse_string_list(query_first(query, "args")),
        env=_parse_string_map(query_first(query, "env")),
        cwd=(query_first(query, "cwd") or "").strip() if transport == "stdio" else "",
        url=url if transport in {"sse", "streamableHttp"} else "",
        headers=headers,
        use_proxy=proxy_enabled(query),
        tool_timeout=tool_timeout,
        enabled_tools=parse_enabled_tools(query_first(query, "enabled_tools")),
    )
    return name, cfg


def _mcp_server_config(name: str, raw: Any) -> tuple[str, MCPServerConfig]:
    server_name = validated_server_name(name)
    if not isinstance(raw, Mapping):
        raise McpPresetError(f"MCP server '{server_name}' must be an object")
    server = cast(Mapping[str, Any], raw)
    command = str(server.get("command") or "").strip()
    url = str(server.get("url") or "").strip()
    transport_value = str(server.get("type", server.get("transport", "")) or "")
    transport = _normalize_transport(transport_value, command=command, url=url)
    if transport == "stdio" and not command:
        raise McpPresetError(f"MCP server '{server_name}' stdio transport requires a command")
    if transport in {"sse", "streamableHttp"} and not url:
        raise McpPresetError(f"MCP server '{server_name}' remote transport requires a URL")
    args_value: object = server.get("args") or []
    env_value: object = server.get("env") or {}
    headers_value: object = server.get("headers") or {}
    cwd = str(server.get("cwd") or "").strip()
    enabled_tools_value: object = server.get("enabledTools", server.get("enabled_tools", ["*"]))
    tool_timeout: object = server.get(
        "toolTimeout", server.get("tool_timeout", _DEFAULT_CUSTOM_TIMEOUT)
    )
    try:
        timeout_int = max(5, min(int(cast(Any, tool_timeout)), 600))
    except (TypeError, ValueError):
        timeout_int = _DEFAULT_CUSTOM_TIMEOUT
    if not isinstance(args_value, list):
        raise McpPresetError(f"MCP server '{server_name}' args must be a string array")
    args = cast(list[object], args_value)
    if not all(isinstance(item, str) for item in args):
        raise McpPresetError(f"MCP server '{server_name}' args must be a string array")
    if not isinstance(env_value, dict):
        raise McpPresetError(f"MCP server '{server_name}' env must be a string object")
    env = cast(dict[object, object], env_value)
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        raise McpPresetError(f"MCP server '{server_name}' env must be a string object")
    if not isinstance(headers_value, dict):
        raise McpPresetError(f"MCP server '{server_name}' headers must be a string object")
    headers = cast(dict[object, object], headers_value)
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
        raise McpPresetError(f"MCP server '{server_name}' headers must be a string object")
    typed_headers = cast(dict[str, str], headers)
    use_proxy = server.get("useProxy", server.get("use_proxy", False))
    if not isinstance(use_proxy, bool):
        raise McpPresetError(f"MCP server '{server_name}' useProxy must be a boolean")
    auth = _normalize_auth(
        server.get("auth"),
        transport=transport,
        url=url,
        headers=typed_headers,
    )
    if not isinstance(enabled_tools_value, list):
        enabled_tools_value = ["*"]
    else:
        enabled_tools = cast(list[object], enabled_tools_value)
        if not all(isinstance(item, str) for item in enabled_tools):
            enabled_tools_value = ["*"]
    return server_name, MCPServerConfig(
        type=transport,
        auth=auth,
        command=command if transport == "stdio" else "",
        args=cast(list[str], args),
        env=cast(dict[str, str], env),
        cwd=cwd if transport == "stdio" else "",
        url=url if transport in {"sse", "streamableHttp"} else "",
        headers=typed_headers,
        use_proxy=use_proxy,
        tool_timeout=timeout_int,
        enabled_tools=cast(list[str], enabled_tools_value),
    )


def import_mcp_servers(raw_json: str | None) -> dict[str, MCPServerConfig]:
    parsed = _parse_json_value(raw_json, fallback=None)
    if not isinstance(parsed, Mapping):
        raise McpPresetError("MCP config must be a JSON object")
    parsed_mapping = cast(Mapping[str, Any], parsed)
    servers: object = parsed_mapping.get("mcpServers", parsed_mapping)
    if not isinstance(servers, Mapping):
        raise McpPresetError("MCP config must contain mcpServers")
    out: dict[str, MCPServerConfig] = {}
    for name, raw_server in cast(Mapping[object, object], servers).items():
        if not isinstance(name, str):
            raise McpPresetError("MCP server names must be strings")
        server_name, cfg = _mcp_server_config(name, raw_server)
        out[server_name] = cfg
    if not out:
        raise McpPresetError("MCP config contains no servers")
    return out
