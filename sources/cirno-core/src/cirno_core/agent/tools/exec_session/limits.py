"""Normalize bounded observation arguments supplied by tools."""


def clamp_session_int(value: int | None, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    return min(max(value, minimum), maximum)
