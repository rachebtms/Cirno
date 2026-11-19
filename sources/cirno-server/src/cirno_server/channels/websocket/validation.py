"""WebSocket setup validation owned by the channel package."""

from typing import Any

from pydantic import ValidationError

from cirno_server.channels.contracts import ChannelValidationContext
from cirno_server.channels.validation import check, enabled, official_action, payload
from cirno_server.channels.websocket.config import WebSocketConfig


def validate_config(values: dict[str, Any]) -> None:
    """Reject unusable listener configuration without echoing secret inputs."""
    try:
        WebSocketConfig.model_validate(values)
    except ValidationError as exc:
        details = [
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        ]
        raise ValueError("; ".join(details)) from None


def validate(values: dict[str, Any], _context: ChannelValidationContext) -> dict[str, Any]:
    checks = [
        check(
            "managed",
            "Managed by WebUI",
            "pass",
            "The browser workbench prepares the local WebSocket channel.",
            action_url=official_action("websocket"),
        )
    ]
    status = "connected" if enabled(values) else "configured"
    return payload("websocket", status, checks, can_enable=True)


__all__ = ["validate", "validate_config"]
