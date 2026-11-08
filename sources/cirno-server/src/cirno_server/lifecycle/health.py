"""Local service readiness probes without inherited proxy routing."""

import hashlib
import http.client
import json
from dataclasses import asdict
from typing import Any, Protocol, cast
from uuid import uuid4

from cirno_core import __version__
from loguru import logger

from cirno_server.api import HEALTH_PATH
from cirno_server.lifecycle.contracts import ServerHealthIdentity
from cirno_server.lifecycle.instance import ServerInstance


class ChannelHealthSource(Protocol):
    @property
    def enabled_channels(self) -> list[str]: ...

    def get_status(self) -> dict[str, Any]: ...


def _channel_health(ready: bool, state: str) -> tuple[bool, dict[str, object]]:
    return ready, {
        "status": "ok" if ready else "degraded",
        "process": "alive",
        "ready": ready,
        "websocket": state,
    }


def channel_readiness(channels: ChannelHealthSource) -> tuple[bool, dict[str, object]]:
    """Describe process liveness separately from required WebSocket readiness."""
    try:
        statuses = channels.get_status()
    except Exception:
        logger.exception("Server readiness could not read channel status")
        return _channel_health(False, "unavailable")

    websocket = statuses.get("websocket")
    if websocket is None and "websocket" not in channels.enabled_channels:
        return _channel_health(True, "disabled")
    if not isinstance(websocket, dict):
        return _channel_health(False, "unavailable")
    status = cast(dict[str, Any], websocket)
    state = status.get("state")
    return _channel_health(status.get("running") is True, state if isinstance(state, str) else "unavailable")


def health_ready(
    host: str,
    port: int,
    *,
    timeout_s: float = 0.4,
    expected: ServerHealthIdentity | None = None,
    maintenance: bool | None = None,
) -> bool:
    """Read readiness from the management listener without using proxy settings."""
    connect_host = "127.0.0.1" if host in {"", "0.0.0.0"} else "::1" if host == "::" else host
    connection = http.client.HTTPConnection(connect_host, port, timeout=timeout_s)
    try:
        connection.request("GET", HEALTH_PATH)
        response = connection.getresponse()
        body = response.read(4097)
    except (OSError, http.client.HTTPException, TimeoutError):
        return False
    finally:
        connection.close()
    if response.status != 200 or len(body) > 4096:
        return False
    try:
        raw_payload = cast(object, json.loads(body.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(raw_payload, dict):
        return False
    payload = cast(dict[str, object], raw_payload)
    if maintenance is not None and payload.get("maintenance") is not maintenance:
        return False
    if expected is not None:
        raw_identity = payload.get("runtime")
        if payload.get("ready") is not True or not isinstance(raw_identity, dict):
            return False
        identity = cast(dict[str, object], raw_identity)
        if any(identity.get(key) != value for key, value in asdict(expected).items()):
            return False
    return payload.get("status") == "ok" and payload.get("ready") is not False


def create_health_identity(instance: ServerInstance) -> ServerHealthIdentity:
    return ServerHealthIdentity(
        hashlib.sha256(str(instance.paths.state_path.resolve()).encode()).hexdigest(),
        uuid4().hex,
        __version__,
    )
