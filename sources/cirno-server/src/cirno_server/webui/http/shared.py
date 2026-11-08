"""HTTP request contracts and route values shared by the focused controllers."""

from __future__ import annotations

import json
import mimetypes
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast
from urllib.parse import unquote

from cirno_core.cron.types import CronJob, CronSchedule
from cirno_core.session.display_history import HistoryReader
from cirno_core.session.session_identity import is_webui_session_key
from cirno_core.session.transcript import (
    TranscriptReplayStats,
)
from cirno_server.webui.http_utils import JSONResponseMetrics
from cirno_server.webui.http_utils import (
    parse_query as _parse_query,
)
from loguru import logger
from websockets.http11 import Request as WsRequest
from websockets.http11 import Response

_SLOW_WEBUI_HTTP_LOG_MS = 1_000

_WEBUI_MUTATION_PAYLOAD_ATTR = "_cirno_webui_mutation_payload"

_WEBUI_MUTATION_REQUEST_ATTR = "_cirno_webui_mutation_request"

_NO_STORE_HEADERS = [("Cache-Control", "no-store")]


def _quoted_etag(revision: str) -> str:
    return f'"{revision}"'


def _etag_matches(value: str, etag: str) -> bool:
    return any(
        candidate.strip().removeprefix("W/") in {"*", etag} for candidate in value.split(",")
    )


@dataclass(slots=True)
class _WebUIThreadDiagnostics:
    transcript: TranscriptReplayStats = field(default_factory=TranscriptReplayStats)
    response: JSONResponseMetrics = field(default_factory=JSONResponseMetrics)
    session_hash: str = ""
    build_ms: float = 0.0
    total_ms: float = 0.0
    event_loop_lag_ms: float = 0.0


_WEBUI_MUTATION_PATHS = {
    "preferences.read": "/v0/preferences",
    "preferences.update": "/v0/preferences",
    "automation.enable": "/v0/webui/automations/enable",
    "automation.disable": "/v0/webui/automations/disable",
    "automation.delete": "/v0/webui/automations/delete",
    "automation.run": "/v0/webui/automations/run",
    "automation.update": "/v0/webui/automations/update",
    "automation.change_chat": "/v0/webui/automations/change-chat",
    "skill.install": "/v0/webui/skills/install",
    "skill.update": "/v0/webui/skills/update",
    "skill.delete": "/v0/webui/skills/delete",
    "sidebar.update": "/v0/webui/sidebar-state/update",
    "session.context_usage": "/v0/session-context",
    "instance.action": "/v0/instance",
    "workbench.action": "/v0/workbench",
    "workspace.files.list": "/v0/workspaces/files/list",
    "workspace.files.read": "/v0/workspaces/files/read",
    "workspace.files.save": "/v0/workspaces/files/save",
    "workspace.files.create": "/v0/workspaces/files/create",
    "workspace.favorite": "/v0/workspaces/favorite",
    "workspace.resolve_project": "/v0/workspaces/resolve-project",
    "recovery.continue": "/v0/webui/recovery/continue",
    "recovery.dismiss": "/v0/webui/recovery/dismiss",
    "subagent.cancel": "/v0/webui/subagents/cancel",
    "settings.profile.read": "/v0/settings/profile/read",
    "settings.profile.update": "/v0/settings/profile/update",
    "settings.agent.update": "/v0/settings/update",
    "settings.model_configuration.create": "/v0/settings/model-configurations/create",
    "settings.model_configuration.update": "/v0/settings/model-configurations/update",
    "settings.model_configuration.delete": "/v0/settings/model-configurations/delete",
    "settings.model_call_order.update": "/v0/settings/model-call-order/update",
    "settings.provider.update": "/v0/settings/provider/update",
    "settings.provider.create": "/v0/settings/provider/create",
    "settings.provider.oauth_login": "/v0/settings/provider/oauth-login",
    "settings.provider.oauth_complete": "/v0/settings/provider/oauth-login/complete",
    "settings.provider.oauth_logout": "/v0/settings/provider/oauth-logout",
    "settings.web_search.update": "/v0/settings/web-search/update",
    "settings.runtime_config.update": "/v0/settings/runtime-config/update",
    "settings.network_safety.update": "/v0/settings/network-safety/update",
    "settings.cli_app.install": "/v0/settings/cli-apps/install",
    "settings.cli_app.update": "/v0/settings/cli-apps/update",
    "settings.cli_app.uninstall": "/v0/settings/cli-apps/uninstall",
    "settings.cli_app.test": "/v0/settings/cli-apps/test",
    "settings.feature.enable": "/v0/settings/cirno-features/enable",
    "settings.feature.disable": "/v0/settings/cirno-features/disable",
    "settings.channel.validate": "/v0/settings/channels/validate",
    "settings.channel.configure": "/v0/settings/channels/configure",
    "settings.mcp.enable": "/v0/settings/mcp-presets/enable",
    "settings.mcp.disable": "/v0/settings/mcp-presets/disable",
    "settings.mcp.remove": "/v0/settings/mcp-presets/remove",
    "settings.mcp.test": "/v0/settings/mcp-presets/test",
    "settings.mcp.reconnect": "/v0/settings/mcp-presets/reconnect",
    "settings.mcp.proxy": "/v0/settings/mcp-presets/proxy",
    "settings.mcp.custom": "/v0/settings/mcp-presets/custom",
    "settings.mcp.import": "/v0/settings/mcp-presets/import",
    "settings.mcp.import_cursor": "/v0/settings/mcp-presets/import-cursor",
    "settings.mcp.tools": "/v0/settings/mcp-presets/tools",
    "settings.mcp.oauth_start": "/v0/settings/mcp-oauth/start",
    "settings.mcp.oauth_complete": "/v0/settings/mcp-oauth/complete",
    "settings.mcp.oauth_cancel": "/v0/settings/mcp-oauth/cancel",
}

_WEBUI_CHANNEL_CONNECT_ACTIONS = {
    "settings.channel.connect.start": "start",
    "settings.channel.connect.poll": "poll",
    "settings.channel.connect.cancel": "cancel",
}

_MIME_FIXES: dict[str, str] = {
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".css": "text/css",
    ".html": "text/html",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".wasm": "application/wasm",
}

for _ext, _ctype in _MIME_FIXES.items():
    mimetypes.add_type(_ctype, _ext, strict=True)

if TYPE_CHECKING:
    pass


def _decode_api_key(raw_key: str) -> str | None:
    key = unquote(raw_key)
    _api_key_re = re.compile(r"^[A-Za-z0-9_:.-]{1,128}$")
    if _api_key_re.match(key) is None:
        return None
    return key


def _mutation_payload(request: WsRequest) -> dict[str, Any] | None:
    payload = getattr(request, _WEBUI_MUTATION_PAYLOAD_ATTR, None)
    if not isinstance(payload, dict):
        return None
    return cast(dict[str, Any], payload)


def _request_query(request: WsRequest) -> dict[str, list[str]]:
    payload = _mutation_payload(request)
    if payload is None:
        return _parse_query(request.path)
    query: dict[str, list[str]] = {}
    for key, value in payload.items():
        if not key:
            continue
        if isinstance(value, bool):
            text = "true" if value else "false"
        elif value is None:
            text = ""
        elif isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        else:
            text = str(value)
        query[key] = [text]
    return query


def _default_model_name_from_config(config_path: Path | None = None) -> str | None:
    try:
        from cirno_core.config.loader import load_config

        model = load_config(config_path).resolve_preset().model.strip()
        return model or None
    except Exception as e:
        logger.debug("bootstrap model_name could not load from config: {}", e)
        return None


def _resolve_bootstrap_model_name(
    runtime_name: Callable[[], str | None] | None,
    config_path: Path | None = None,
) -> str:
    if runtime_name is not None:
        try:
            raw = runtime_name()
        except Exception as e:
            logger.debug("bootstrap runtime model resolver failed: {}", e)
        else:
            if isinstance(raw, str):
                stripped = raw.strip()
                if stripped:
                    return stripped
    return _default_model_name_from_config(config_path) or ""


class _HistoryProjection(Protocol):
    def __call__(self, request: WsRequest, key: str, *, history: HistoryReader) -> Response: ...


def _automation_values_from_request(request: WsRequest) -> dict[str, Any] | None:
    payload = _mutation_payload(request)
    if payload is None or "values" not in payload:
        return {}
    values = payload.get("values")
    return cast(dict[str, Any], values) if isinstance(values, dict) else None


def _parse_automation_update(
    values: dict[str, Any],
    *,
    current_job: CronJob | None = None,
) -> dict[str, Any] | str:
    update: dict[str, Any] = {}
    if "name" in values:
        raw_name = values.get("name")
        if not isinstance(raw_name, str):
            return "name must be a string"
        name = raw_name.strip()
        if not name:
            return "name cannot be empty"
        update["name"] = name
    if "message" in values:
        raw_message = values.get("message")
        if not isinstance(raw_message, str):
            return "message must be a string"
        message = raw_message.strip()
        if not message:
            return "message cannot be empty"
        update["message"] = message
    if "schedule" in values:
        raw_schedule = values.get("schedule")
        if not isinstance(raw_schedule, dict):
            return "schedule must be an object"
        parsed_schedule = _parse_automation_schedule(cast(dict[str, Any], raw_schedule))
        if isinstance(parsed_schedule, str):
            return parsed_schedule
        if current_job is not None and _schedule_matches_job(parsed_schedule, current_job):
            return update
        schedule_error = _validate_automation_schedule(parsed_schedule)
        if schedule_error:
            return schedule_error
        update["schedule"] = parsed_schedule
        update["delete_after_run"] = parsed_schedule.kind == "at"
    return update


def _parse_local_trigger_update(values: dict[str, Any]) -> dict[str, Any] | str:
    update: dict[str, Any] = {}
    if "name" in values:
        raw_name = values.get("name")
        if not isinstance(raw_name, str):
            return "name must be a string"
        name = raw_name.strip()
        if not name:
            return "name cannot be empty"
        update["name"] = name
    forbidden = [key for key in ("message", "schedule") if key in values]
    if forbidden:
        return "local trigger updates only support name"
    return update


def _parse_automation_schedule(values: dict[str, Any]) -> CronSchedule | str:
    raw_kind = values.get("kind")
    if not isinstance(raw_kind, str):
        return "schedule kind must be a string"
    kind = raw_kind.strip()
    if kind == "every":
        every_ms = _positive_int(values.get("every_ms"))
        if every_ms is None:
            return "every schedule requires positive every_ms"
        return CronSchedule(kind="every", every_ms=every_ms)
    if kind == "cron":
        raw_expr = values.get("expr")
        if not isinstance(raw_expr, str):
            return "cron schedule requires expr"
        expr = raw_expr.strip()
        if not expr:
            return "cron schedule requires expr"
        raw_tz = values.get("tz")
        if raw_tz is not None and not isinstance(raw_tz, str):
            return "cron schedule timezone must be a string"
        tz = raw_tz.strip() if isinstance(raw_tz, str) else ""
        return CronSchedule(kind="cron", expr=expr, tz=tz or None)
    if kind == "at":
        at_ms = _positive_int(values.get("at_ms"))
        if at_ms is None:
            return "one-time schedule requires positive at_ms"
        return CronSchedule(kind="at", at_ms=at_ms)
    return "unknown schedule kind"


def _schedule_matches_job(schedule: CronSchedule, job: CronJob) -> bool:
    current = job.schedule
    if schedule.kind != current.kind:
        return False
    if schedule.kind == "at":
        return schedule.at_ms == current.at_ms
    if schedule.kind == "every":
        return schedule.every_ms == current.every_ms
    if schedule.kind == "cron":
        return (schedule.expr or "") == (current.expr or "") and (schedule.tz or None) == (
            current.tz or None
        )
    return False


def _validate_automation_schedule(schedule: CronSchedule) -> str | None:
    if schedule.kind == "at":
        if not schedule.at_ms or schedule.at_ms <= int(time.time() * 1000):
            return "one-time schedule must be in the future"
        return None
    if schedule.kind != "cron":
        return None

    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from croniter import croniter

        tz = ZoneInfo(schedule.tz) if schedule.tz else datetime.now().astimezone().tzinfo
        base = datetime.now(tz=tz)
        croniter(cast(str, schedule.expr), base).get_next(datetime)
    except Exception:
        return "cron schedule is invalid"
    return None


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _is_websocket_channel_session_key(key: str) -> bool:
    return is_webui_session_key(key)
