"""Channel defaults and instance-specific presentation settings."""

from __future__ import annotations

from typing import Any, cast

from cirno_core.config.schema import Config

from .contracts import channel_default_config
from .registry import channel_default_enabled

_BOOL_CAMEL_ALIASES: dict[str, str] = {
    "send_progress": "sendProgress",
    "send_tool_hints": "sendToolHints",
    "show_reasoning": "showReasoning",
    "show_compaction_notices": "showCompactionNotices",
}


def _default_channel_config(name: str) -> dict[str, Any] | None:
    from cirno_server.channels.registry import load_channel_plugin

    plugin = load_channel_plugin(name)
    if not plugin.default_enabled:
        return None
    return channel_default_config(plugin)


def channel_section(
    config: Config,
    name: str,
    *,
    default_sections: dict[str, Any] | None = None,
    default_enabled: bool | None = None,
) -> Any:
    section = getattr(config.channels, name, None)
    if default_enabled is None:
        default_enabled = channel_default_enabled(name)
    if section is not None or not default_enabled:
        return section
    if default_sections is None:
        return _default_channel_config(name)
    if name not in default_sections:
        default = _default_channel_config(name)
        if default is not None:
            default_sections[name] = default
    return default_sections.get(name)


def resolve_bool_override(section: Any, key: str, default: bool) -> bool:
    """Return *key* from *section* if it is a bool, otherwise *default*.

    For dict configs also checks the camelCase alias (e.g. ``sendProgress``
    for ``send_progress``) so raw JSON/TOML configs work alongside
    Pydantic models.
    """
    if isinstance(section, dict):
        section_data = cast(dict[str, Any], section)
        value = section_data.get(key)
        if value is None:
            camel = _BOOL_CAMEL_ALIASES.get(key)
            if camel:
                value = section_data.get(camel)
        return value if isinstance(value, bool) else default
    value = getattr(section, key, None)
    return value if isinstance(value, bool) else default
