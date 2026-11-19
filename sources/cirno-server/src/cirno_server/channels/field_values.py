"""Nested channel-field assignment shared by defaults, draft checks and saves."""

from typing import Any, cast

from pydantic.alias_generators import to_snake


def assign_channel_field(
    channel_config: dict[str, Any],
    field: str,
    value: Any,
    *,
    inheritable: bool = False,
) -> None:
    target = channel_config
    parts = field.split(".")
    for part in parts[:-1]:
        current: object = target.get(part)
        if not isinstance(current, dict):
            current = {}
            target[part] = current
        target = cast(dict[str, Any], current)
    key = parts[-1]
    if inheritable:
        # Do not leave an older snake_case override shadowing this UI edit.
        target.pop(to_snake(key), None)
        if value is None:
            # Absence restores inheritance and remains readable by older configs.
            target.pop(key, None)
            return
    target[key] = value
