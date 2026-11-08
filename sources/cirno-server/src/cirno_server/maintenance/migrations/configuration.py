"""One-time conversion of released endpoint paths and model display names."""

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from cirno_core.config.errors import ConfigIssue, ConfigLoadError, validation_issues
from cirno_server.api import API_PREFIX, WEBSOCKET_PATH
from cirno_server.channels.websocket.config import WebSocketConfig
from pydantic import ValidationError


def versioned_path(path: str) -> str:
    if path == API_PREFIX or path.startswith(API_PREFIX + "/"):
        return path
    if path == "/":
        return WEBSOCKET_PATH
    return API_PREFIX + (path.removeprefix("/api") if path.startswith("/api/") else path)


def import_configuration(data: dict, version: str, config_path: Path) -> None:
    websocket = data.get("channels", {}).get("websocket", {})
    if "path" in websocket:
        websocket["path"] = versioned_path(websocket["path"])
    for name in ("tokenIssuePath", "token_issue_path"):
        if websocket.get(name):
            websocket[name] = versioned_path(websocket[name])
    for name in ("publicWsUrl", "public_ws_url"):
        if websocket.get(name):
            url = urlsplit(websocket[name])
            websocket[name] = urlunsplit(url._replace(path=versioned_path(url.path or "/")))
    try:
        WebSocketConfig.model_validate(websocket)
    except ValidationError as error:
        raise ConfigLoadError(
            config_path, kind="invalid_schema", summary="Web UI connection settings are invalid.",
            issues=tuple(ConfigIssue(path=("channels", "websocket", *issue.path), message=issue.message)
                         for issue in validation_issues(error)),
        ) from error
    presets = data.get("modelPresets", data.get("model_presets", {}))
    for identifier, preset in presets.items():
        if not preset.get("displayName") and not preset.get("display_name"):
            preset["displayName"] = identifier
    data.pop("last_run_version", None)
    data["lastRunVersion"] = version
