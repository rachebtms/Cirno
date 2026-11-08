"""Construct channel adapters with shared presentation policy."""

from __future__ import annotations

from typing import Any

from cirno_core.bus.queue import MessageBus
from cirno_core.config.schema import Config

from .base import BaseChannel
from .configuration import resolve_bool_override
from .webui_binding import WebUIChannelBindings


class ChannelFactory:
    def __init__(self, bus: MessageBus, webui: WebUIChannelBindings) -> None:
        self.bus = bus
        self.webui = webui

    def build(
        self,
        config: Config,
        cls: type[BaseChannel],
        section: Any,
        *,
        runtime_name: str | None = None,
    ) -> BaseChannel:
        kwargs: dict[str, Any] = {}
        if cls.uses_shared_proxy:
            kwargs["network"] = config.network
        if cls.name == "websocket":
            kwargs["gateway"] = self.webui.services(config, section, self.bus)
        channel = cls(section, self.bus, **kwargs)
        channel.tool_status_summary_max_chars = config.agents.defaults.tool_status_summary_max_chars
        if runtime_name and runtime_name != channel.name:
            channel.name = runtime_name
        progress_default, tool_hints_default = channel.progress_transport_defaults() or (
            config.channels.send_progress,
            config.channels.send_tool_hints,
        )
        channel.send_progress = resolve_bool_override(
            section,
            "send_progress",
            progress_default,
        )
        channel.send_tool_hints = resolve_bool_override(
            section,
            "send_tool_hints",
            tool_hints_default,
        )
        channel.show_reasoning = resolve_bool_override(
            section,
            "show_reasoning",
            config.channels.show_reasoning,
        )
        # Respect the channel adapter’s default for compaction notices.
        notice_default = resolve_bool_override(
            channel.config,
            "show_compaction_notices",
            config.channels.show_compaction_notices,
        )
        channel.show_compaction_notices = resolve_bool_override(
            section,
            "show_compaction_notices",
            notice_default,
        )
        return channel
