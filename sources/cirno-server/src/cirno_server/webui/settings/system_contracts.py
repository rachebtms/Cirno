"""Injected operations for system settings domains."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cirno_server.channels.plugin import ChannelPlugin

LoadChannelPlugin = Callable[[str], "ChannelPlugin"]
SettingsOperation = Callable[..., Any]


@dataclass(frozen=True)
class SystemSettingsOperations:
    update_runtime_config: SettingsOperation
    cli_apps_payload: SettingsOperation
    cli_apps_action: SettingsOperation
    cirno_features_payload: SettingsOperation
    cirno_features_action: SettingsOperation
    cirno_feature_instance_target: SettingsOperation
    validate_channel_config: SettingsOperation
    load_channel_plugin: LoadChannelPlugin
    mcp_presets_action: SettingsOperation
    reload_mcp: SettingsOperation
    mcp_runtime_status: Callable[[], Mapping[str, str]] | None
    channel_feature_action: SettingsOperation | None = None
    channel_runtime_status: Callable[[], dict[str, Any]] | None = None
