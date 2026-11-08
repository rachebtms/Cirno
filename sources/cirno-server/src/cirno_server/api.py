"""Public transport endpoints for Cirno's current major API version."""

API_MAJOR = 0
API_PREFIX = f"/v{API_MAJOR}"
WEBSOCKET_PATH = f"{API_PREFIX}/ws"
HEALTH_PATH = f"{API_PREFIX}/health"


def require_api_path(value: str) -> str:
    """Keep configurable endpoints inside the supported API namespace."""
    if not value.startswith(f"{API_PREFIX}/") or value == f"{API_PREFIX}/":
        raise ValueError(f"API endpoint must be under {API_PREFIX}/")
    if any(character in value for character in ("?", "#", "\\", "\x00")):
        raise ValueError("API endpoint must be a path without a query or fragment")
    if any(part in {".", "..", ""} for part in value.removeprefix("/").split("/")):
        raise ValueError("API endpoint must not contain empty or relative path segments")
    return value
