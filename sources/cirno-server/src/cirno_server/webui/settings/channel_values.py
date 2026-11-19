"""Pure channel form conversion and validated configuration updates."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any, cast

from cirno_core.config.schema import Config
from cirno_server.channels._setup import channel_setup_spec
from cirno_server.channels.contracts import (
    RouteFieldType, channel_instance_config, channel_update_instance_config,
)
from cirno_server.channels.field_values import assign_channel_field as assign_channel_config_value
from cirno_server.webui.settings.contracts import WebUISettingsError
from cirno_server.webui.settings.system_contracts import LoadChannelPlugin

if TYPE_CHECKING:
    from cirno_server.webui.settings.services import WebUISettingsConfig

_SKIP_FIELD = object()


def update_channel_config_values(
    store: WebUISettingsConfig, name: str, raw_values: dict[str, Any], instance_id: str = "default",
    *, load_channel_plugin: LoadChannelPlugin,
) -> list[str]:
    """Run form validation and persistence in the owning config transaction."""
    return store.update(lambda config: save_channel_config_values(
        config, name, raw_values, instance_id, load_channel_plugin=load_channel_plugin,
    ))


def save_channel_config_values(
    config: Config,
    name: str,
    raw_values: dict[str, Any],
    instance_id: str = "default",
    *,
    load_channel_plugin: LoadChannelPlugin,
) -> list[str]:
    if not name:
        raise WebUISettingsError("missing channel name")
    try:
        plugin = load_channel_plugin(name)
    except ImportError:
        raise WebUISettingsError(f"unknown channel '{name}'", status=404) from None
    setup_spec = channel_setup_spec(name, plugin=plugin)
    if setup_spec is None:
        raise WebUISettingsError(
            f"channel '{name}' cannot be configured from WebUI",
            status=404,
        )
    field_types = setup_spec.route_field_types
    if not raw_values:
        return []

    section = getattr(config.channels, name, None)
    channel_config = channel_instance_config(
        plugin,
        section,
        instance_id=instance_id,
    )
    saved: list[str] = []
    prefix = f"channels.{name}."
    for raw_key, raw_value in raw_values.items():
        if not raw_key:
            raise WebUISettingsError(
                "channel settings payload contains an invalid key"
            )
        field = raw_key[len(prefix) :] if raw_key.startswith(prefix) else raw_key
        value_type = field_types.get(field)
        if value_type is None:
            raise WebUISettingsError(f"'{raw_key}' cannot be configured from WebUI")
        if setup_spec.fields[field].inheritable and raw_value in (None, ""):
            value = None
        else:
            value = coerce_channel_value(raw_key, raw_value, value_type)
        if value is _SKIP_FIELD:
            continue
        assign_channel_config_value(
            channel_config, field, value, inheritable=setup_spec.fields[field].inheritable,
        )
        saved.append(raw_key)

    try:
        if setup_spec.validate_config is not None:
            setup_spec.validate_config(channel_config)
        updated_section = channel_update_instance_config(
            plugin,
            section,
            channel_config,
            instance_id=instance_id,
        )
    except ValueError as exc:
        raise WebUISettingsError(
            f"Invalid {name} configuration: {exc}",
            status=400,
        ) from exc
    setattr(config.channels, name, updated_section)
    return saved


def coerce_channel_value(
    raw_key: str,
    raw_value: Any,
    value_type: RouteFieldType,
) -> Any:
    if isinstance(value_type, tuple):
        kind = value_type[0]
        allowed = value_type[1]
    else:
        kind = value_type
        allowed = None

    if kind in {"string", "secret"}:
        if kind == "secret" and raw_value is None:
            return ""
        value = raw_value.strip() if isinstance(raw_value, str) else str(raw_value)
        if kind == "secret" and not value:
            return _SKIP_FIELD
        return value

    if kind == "list":
        if raw_value is None:
            return []
        if isinstance(raw_value, str):
            return [item.strip() for item in raw_value.split(",") if item.strip()]
        if isinstance(raw_value, list):
            return [
                str(item).strip()
                for item in cast(list[Any], raw_value)
                if str(item).strip()
            ]
        raise WebUISettingsError(f"'{raw_key}' must be a comma-separated list")

    if kind == "int":
        if raw_value in (None, ""):
            return _SKIP_FIELD
        try:
            if isinstance(raw_value, bool) or (
                isinstance(raw_value, float) and not raw_value.is_integer()
            ):
                raise ValueError("not an integer")
            return int(raw_value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise WebUISettingsError(f"'{raw_key}' must be an integer") from exc

    if kind == "float":
        if raw_value in (None, ""):
            return _SKIP_FIELD
        try:
            if isinstance(raw_value, bool):
                raise ValueError("not a number")
            value = float(raw_value)
            if not math.isfinite(value):
                raise ValueError("not finite")
            return value
        except (TypeError, ValueError, OverflowError) as exc:
            raise WebUISettingsError(f"'{raw_key}' must be a finite number") from exc

    if kind == "json":
        if raw_value in (None, ""):
            return _SKIP_FIELD
        try:
            value = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
        except (TypeError, ValueError) as exc:
            raise WebUISettingsError(f"'{raw_key}' must be valid JSON") from exc
        if not isinstance(value, dict):
            raise WebUISettingsError(f"'{raw_key}' must be a JSON object")
        return cast(dict[str, Any], value)

    if kind == "bool":
        if isinstance(raw_value, bool):
            return raw_value
        value = str(raw_value).strip().lower()
        if value in {"true", "1", "yes", "on"}:
            return True
        if value in {"false", "0", "no", "off"}:
            return False
        raise WebUISettingsError(f"'{raw_key}' must be true or false")

    if kind == "enum":
        value = raw_value.strip() if isinstance(raw_value, str) else str(raw_value)
        if not value:
            return _SKIP_FIELD
        if allowed is None or value not in allowed:
            options = ", ".join(sorted(allowed or ()))
            raise WebUISettingsError(f"'{raw_key}' must be one of: {options}")
        return value

    raise WebUISettingsError(f"'{raw_key}' has an unsupported field type")
