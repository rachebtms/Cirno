"""Mapping and attribute access at the SDK wire boundary."""

from typing import Any, cast


def field(obj: object, key: str) -> Any:
    """Get a value from dict or object attribute, returning None if absent."""
    if isinstance(obj, dict):
        return cast(dict[str, Any], obj).get(key)
    return getattr(obj, key, None)


def mapping(value: object) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped: object = model_dump()
        if isinstance(dumped, dict):
            return cast(dict[str, Any], dumped)
    return None
