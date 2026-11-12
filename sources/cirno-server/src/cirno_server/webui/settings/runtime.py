"""Explicit non-channel runtime configuration exposed by the settings UI."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
from pathlib import Path
from typing import Any, cast

from cirno_core.config.schema import Config
from cirno_server.webui.settings.contracts import WebUISettingsError
from cirno_server.webui.settings.requests import redact_request_secrets
from pydantic import BaseModel, TypeAdapter, ValidationError

# Only these leaves may be read or patched through this surface. Model/provider,
# and channel configuration keep dedicated mutation contracts. The embedding API
# key is masked on this surface and restored only through the shared secret helpers.
SYSTEM_PROMPT_PATHS = (
    "agents.defaults.system_prompts.shared",
    "agents.defaults.system_prompts.router",
    "agents.defaults.system_prompts.worker",
)

RUNTIME_CONFIG_PATHS = (
    *SYSTEM_PROMPT_PATHS,
    "agents.defaults.workspace",
    "agents.defaults.approval.enabled",
    "agents.defaults.approval.model_override",
    "agents.defaults.approval.timeout_seconds",
    "channels.send_progress",
    "channels.send_tool_hints",
    "channels.show_reasoning",
    "channels.show_compaction_notices",
    "channels.send_max_retries",
    "tools.exec.idle_timeout",
    "tools.exec.idle_action",
    "tools.exec.max_runtime_limit",
    "agents.defaults.consolidation.learn",
    "agents.defaults.consolidation.max_updates",
    "agents.defaults.consolidation.context_chars",
    "agents.defaults.memory.release_archived_runtime",
    "agents.defaults.memory.context_tokens",
    "agents.defaults.memory.checkpoint_tokens",
    "agents.defaults.memory.index_scan_batch",
    "agents.defaults.memory.embedding_enabled",
    "agents.defaults.memory.embedding_provider",
    "agents.defaults.memory.embedding_api_base",
    "agents.defaults.memory.embedding_api_key",
    "agents.defaults.memory.embedding_api_model",
    "agents.defaults.memory.embedding_api_chunk_chars",
    "agents.defaults.memory.embedding_model_path",
    "agents.defaults.memory.embedding_tokenizer_path",
    "agents.defaults.memory.embedding_max_rss_mb",
    "agents.defaults.memory.embedding_timeout_seconds",

    'agents.defaults.idle_compact_check_interval_seconds',
    'agents.defaults.idle_compact_percent',
    'agents.defaults.active_compact_percent',
    'agents.defaults.consolidation.output_reserve_percent',
    'agents.defaults.consolidation.max_tokens',
    'agents.defaults.consolidation.max_retries',
    'agents.defaults.consolidation.reasoning_effort',
    'agents.defaults.consolidation.checkpoint_reminder_percent',
    'agents.defaults.idle_compact_keep_percent',
    'agents.defaults.heartbeat.enabled',
    'agents.defaults.heartbeat.interval_s',
    'network.request_timeout_s',
    'network.stream_idle_timeout_s',
    'network.provider_max_retries',
    "agents.defaults.timezone",
    "agents.defaults.timezone_mode",
    "agents.defaults.idle_compact_after_minutes",
    "agents.defaults.max_tool_iterations",
    "agents.defaults.goal_continuation_limit",
    "agents.defaults.resume.message",
    "agents.defaults.resume.show_message",
    "agents.defaults.max_concurrent_subagents",
    "agents.defaults.max_tool_result_chars",
    "agents.defaults.provider_retry_mode",
    "agents.defaults.tool_status_summary_max_chars",
    "server.uploads.max_file_mb",
    "server.uploads.max_video_mb",
    "server.uploads.max_total_mb",
    "server.health_host",
    "server.health_port",
    "server.restart_mode",
    "tools.exec.enable",
    "tools.exec.max_runtime",
    "tools.exec.path_prepend",
    "tools.exec.path_append",
    "tools.exec.sandbox",
    "tools.exec.sandbox_ro_binds",
    "tools.exec.sandbox_rw_binds",
    "tools.exec.allowed_env_keys",
    "tools.exec.allow_patterns",
    "tools.exec.deny_patterns",
    "tools.file.enable",
    "tools.my.enable",
    "tools.my.allow_set",
    "tools.cli_apps.enable",
    "tools.cli_apps.install_timeout",
    "tools.cli_apps.run_timeout",
    "tools.cli_apps.catalog_ttl_seconds",
    "tools.restrict_to_workspace",
    "tools.ssrf_whitelist",
    "tools.max_outgoing_session_messages_per_minute",
    "tools.web.enable",
    "network.proxy",
    "tools.web.use_proxy",
    "tools.web.user_agent",
)


def _parent(config: Config, path: str) -> tuple[BaseModel, str]:
    parent: BaseModel = config
    *parts, leaf = path.split(".")
    for part in parts:
        value: object = getattr(parent, part)
        assert isinstance(value, BaseModel)
        parent = value
    return parent, leaf


def runtime_config_payload(config: Config) -> dict[str, Any]:
    return {
        path: (redact_request_secrets(getattr(parent, leaf), secret=True) if path.endswith(".embedding_api_key") else getattr(parent, leaf))
        for path in RUNTIME_CONFIG_PATHS
        for parent, leaf in [_parent(config, path)]
    }


def runtime_restart_values(config: Config) -> dict[str, str]:
    """Compare restart-sensitive values without retaining plaintext secrets."""
    return {
        path: hashlib.sha256(json.dumps(getattr(parent, leaf), sort_keys=True).encode()).hexdigest()
        for path in RUNTIME_CONFIG_PATHS if path not in SYSTEM_PROMPT_PATHS
        for parent, leaf in [_parent(config, path)]
    }


def update_runtime_config(
    config: Config, values: dict[str, Any],
) -> bool:
    """Validate the complete patch before changing any persisted configuration."""
    unknown = values.keys() - set(RUNTIME_CONFIG_PATHS)
    if unknown:
        raise WebUISettingsError("Unknown runtime setting: " + sorted(unknown)[0])
    candidate = config.model_copy(deep=True)
    for path, value in values.items():
        parent, leaf = _parent(candidate, path)
        if path.endswith(".embedding_api_key"):
            from cirno_server.webui.settings.requests import restore_request_secrets
            value = restore_request_secrets(value, getattr(parent, leaf), secret=True)
        if isinstance(value, float) and not math.isfinite(value):
            raise WebUISettingsError(f"{path}: enter a finite number")
        try:
            field = type(parent).model_fields[leaf]
            parsed = TypeAdapter(field.rebuild_annotation()).validate_python(value, strict=True)
        except ValidationError as exc:
            message = exc.errors(include_input=False, include_url=False)[0]["msg"]
            raise WebUISettingsError(f"{path}: {message}") from None
        setattr(parent, leaf, parsed)
    try:
        # Dump public field names so timezone/model validators are
        # handled by the same schema as a normal configuration-file load.
        validated = Config.model_validate(candidate.model_dump(by_alias=True), strict=True)
    except ValidationError as exc:
        errors = exc.errors(include_input=False, include_url=False)
        error = errors[0]
        location = ".".join(str(part) for part in error["loc"])
        raise WebUISettingsError(f"{location}: {error['msg']}") from None

    if "agents.defaults.workspace" in values:
        workspace = validated.agents.defaults.workspace.strip()
        if not workspace or not Path(workspace).expanduser().is_absolute():
            raise WebUISettingsError("agents.defaults.workspace: enter an absolute directory path")
        validated.agents.defaults.workspace = workspace
    for purpose in ("approval",):
        path = f"agents.defaults.{purpose}.model_override"
        model = getattr(validated.agents.defaults, purpose).model_override
        if path in values and model and model != "default" and model not in validated.model_presets:
            raise WebUISettingsError(f"{path}: choose an existing model preset")
    numeric_minima = {
        "agents.defaults.max_tool_iterations": 1,
        "agents.defaults.max_tool_result_chars": 1,
        "server.health_port": 1,
        "agents.defaults.heartbeat.interval_s": 60,
    }
    for path, minimum in numeric_minima.items():
        if path in values:
            parent, leaf = _parent(validated, path)
            if getattr(parent, leaf) < minimum:
                raise WebUISettingsError(f"{path}: must be at least {minimum}")
    if "server.health_port" in values and validated.server.health_port > 65535:
        raise WebUISettingsError("server.health_port: must be at most 65535")
    if {"tools.exec.max_runtime", "tools.exec.max_runtime_limit"} & values.keys():
        limit = validated.tools.exec.max_runtime_limit
        if limit > 0 and validated.tools.exec.max_runtime > limit:
            raise WebUISettingsError(
                f"tools.exec.max_runtime: enter 1–{limit} seconds, or 0 for no time limit"
            )
    if "server.health_host" in values and not validated.server.health_host.strip():
        raise WebUISettingsError("server.health_host: must not be empty")
    if "tools.exec.sandbox" in values and validated.tools.exec.sandbox not in {"", "bwrap", "seatbelt"}:
        raise WebUISettingsError("tools.exec.sandbox: choose no sandbox, bwrap, or seatbelt")
    if "tools.ssrf_whitelist" in values:
        for cidr in validated.tools.ssrf_whitelist:
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                raise WebUISettingsError("tools.ssrf_whitelist: enter valid IP addresses or CIDR ranges") from None
    for path in ("tools.exec.allow_patterns", "tools.exec.deny_patterns"):
        if path in values:
            patterns = cast(list[str], values[path])  # Schema validation above guarantees list[str].
            for pattern in patterns:
                try:
                    re.compile(pattern)
                except re.error:
                    raise WebUISettingsError(f"{path}: invalid regular expression") from None
    if values.get("tools.web.use_proxy") is True:
        try:
            validated.network.resolve_proxy(True)
        except ValueError as exc:
            raise WebUISettingsError(str(exc)) from None
    before = config.model_dump()
    after = validated.model_dump()
    if before == after:
        return False
    config.agents = validated.agents
    config.tools = validated.tools
    config.network = validated.network
    config.server = validated.server
    config.channels = validated.channels
    return True
