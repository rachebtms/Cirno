"""Materialize preset fields, command availability and managed stdio directories."""

from __future__ import annotations

import os
import shutil
import urllib.parse
from pathlib import Path
from typing import Any

from cirno_core.agent.tools.mcp_oauth import (
    mcp_oauth_has_credentials,
)
from cirno_core.config.network import NetworkConfig
from cirno_core.config.paths import get_runtime_subdir
from cirno_core.config.tools import MCPServerConfig
from cirno_core.utils.file_io import ensure_dir
from cirno_server.webui.mcp.contracts import McpPresetError, QueryParams, query_first, query_value
from cirno_server.webui.mcp.presets import McpPreset, McpPresetField


def clone_server(server: MCPServerConfig) -> MCPServerConfig:
    return MCPServerConfig.model_validate(server.model_dump(mode="json"))


def _with_managed_stdio_cwd(name: str, cfg: MCPServerConfig) -> MCPServerConfig:
    if cfg.command and (cfg.type in (None, "stdio")) and not cfg.cwd:
        cfg.cwd = str(ensure_dir(get_runtime_subdir("mcp") / name))
    return cfg


def remove_managed_stdio_cwd(name: str, cfg: MCPServerConfig | None) -> bool:
    if cfg is None or not cfg.cwd:
        return False
    cwd = Path(cfg.cwd).expanduser().resolve(strict=False)
    managed = (get_runtime_subdir("mcp") / name).resolve(strict=False)
    if cwd != managed or not cwd.exists():
        return False
    if cwd.is_symlink() or cwd.is_file():
        cwd.unlink()
    else:
        shutil.rmtree(cwd)
    return True


def _url_with_param(url: str, key: str, value: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if k != key]
    query.append((key, value))
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(query),
            parsed.fragment,
        )
    )


def _arg_value(args: list[str], flag: str) -> str | None:
    prefix = f"{flag}="
    for index, item in enumerate(args):
        if item == flag and index + 1 < len(args):
            return args[index + 1]
        if item.startswith(prefix):
            return item[len(prefix) :]
    return None


def _with_arg_value(args: list[str], flag: str, value: str) -> list[str]:
    out: list[str] = []
    skip_next = False
    prefix = f"{flag}="
    for item in args:
        if skip_next:
            skip_next = False
            continue
        if item == flag:
            skip_next = True
            continue
        if item.startswith(prefix):
            continue
        out.append(item)
    out.extend([flag, value])
    return out


def _field_value_from_config(field: McpPresetField, cfg: MCPServerConfig | None) -> str | None:
    if cfg is None:
        return None
    target_kind, target_name = field.target
    if target_kind == "env":
        value = cfg.env.get(target_name)
        return value if value else None
    if target_kind == "header":
        value = cfg.headers.get(target_name)
        return value.removeprefix(field.value_prefix) if value else None
    if target_kind == "url":
        return cfg.url or None
    if target_kind == "arg":
        return _arg_value(list(cfg.args), target_name)
    if target_kind == "url_param" and cfg.url:
        parsed = urllib.parse.urlsplit(cfg.url)
        values = urllib.parse.parse_qs(parsed.query).get(target_name)
        if values:
            return values[0]
    return None


def _field_configured(field: McpPresetField, cfg: MCPServerConfig | None) -> bool:
    value = _field_value_from_config(field, cfg)
    if value:
        return True
    return bool(field.env_var and os.environ.get(field.env_var))


def field_payload(field: McpPresetField, cfg: MCPServerConfig | None) -> dict[str, Any]:
    return {
        "name": field.name,
        "label": field.label,
        "secret": field.secret,
        "required": field.required,
        "configured": _field_configured(field, cfg),
        "placeholder": field.placeholder,
        "env_var": field.env_var,
    }


def _resolve_field_value(
    field: McpPresetField,
    query: QueryParams,
    existing: MCPServerConfig | None,
) -> str | None:
    provided = query_value(query, field.name)
    if provided:
        return provided
    current = _field_value_from_config(field, existing)
    if current:
        return current
    if field.env_var and os.environ.get(field.env_var):
        return f"${{{field.env_var}}}"
    return None


def proxy_enabled(query: QueryParams, current: bool = False) -> bool:
    raw = query_first(query, "use_proxy")
    if raw is None:
        return current
    if raw.lower() not in {"true", "false"}:
        raise McpPresetError("use_proxy must be true or false")
    return raw.lower() == "true"


def validate_proxy(cfg: MCPServerConfig, network: NetworkConfig) -> None:
    if cfg.use_proxy and (cfg.command or not cfg.url):
        raise McpPresetError("The shared proxy is available for HTTP and SSE MCP connections")
    try:
        network.resolve_proxy(cfg.use_proxy)
    except ValueError as exc:
        raise McpPresetError(str(exc)) from None


def materialize_server(
    preset: McpPreset,
    query: QueryParams,
    existing: MCPServerConfig | None,
) -> MCPServerConfig:
    if preset.server is None or not preset.install_supported:
        raise McpPresetError(f"{preset.display_name} is not supported yet", status=409)

    cfg = clone_server(existing or preset.server)
    cfg.use_proxy = proxy_enabled(query, cfg.use_proxy)
    for field_spec in preset.fields:
        value = _resolve_field_value(field_spec, query, existing)
        if field_spec.required and not value:
            raise McpPresetError(f"missing {field_spec.label}")
        if not value:
            continue
        target_kind, target_name = field_spec.target
        if target_kind == "env":
            cfg.env[target_name] = value
        elif target_kind == "header":
            cfg.headers[target_name] = field_spec.value_prefix + value
        elif target_kind == "arg":
            cfg.args = _with_arg_value(list(cfg.args), target_name, value)
        elif target_kind == "url_param":
            cfg.url = _url_with_param(cfg.url, target_name, value)
        elif target_kind == "url":
            cfg.url = value
    return _with_managed_stdio_cwd(preset.name, cfg)


def command_available(command: str) -> bool:
    if not command:
        return False
    if shutil.which(command):
        return True
    path = Path(command).expanduser()
    return path.exists() and path.is_file()


def config_available(cfg: MCPServerConfig | None) -> bool:
    if cfg is None:
        return False
    if cfg.command:
        return command_available(cfg.command)
    if cfg.url:
        return True
    return False


def status_for(preset: McpPreset, cfg: MCPServerConfig | None) -> str:
    if cfg is None:
        return "not_installed" if preset.install_supported else "coming_soon"
    if any(field.required and not _field_configured(field, cfg) for field in preset.fields):
        return "missing_credentials"
    if cfg.auth == "oauth" and not mcp_oauth_has_credentials(preset.name, cfg.url):
        return "authorization_required"
    if cfg.command and not command_available(cfg.command):
        return "missing_dependency"
    return "configured"
