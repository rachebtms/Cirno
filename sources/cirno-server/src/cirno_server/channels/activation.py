"""Construct configured runtimes and serialize live channel reconfiguration."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from cirno_server.channels._setup import channel_setup_spec
from cirno_server.channels.configuration import channel_section
from cirno_server.channels.contracts import (
    channel_instance_specs,
    channel_runtime_name,
    resolve_channel_action_target,
)
from cirno_server.channels.factory import ChannelFactory
from cirno_server.channels.plugin import ChannelPlugin
from cirno_server.channels.runtimes import ChannelRuntimes


class ChannelActivation:
    def __init__(
        self, runtimes: ChannelRuntimes, factory: ChannelFactory, config_path: Path
    ) -> None:
        self.runtimes = runtimes
        self.factory = factory
        self.config_path = config_path
        self.locks: dict[str, asyncio.Lock] = {}

    def initialize(self) -> None:
        """Initialize enabled runtimes from dependency-free channel descriptors."""
        from cirno_server.channels.registry import discover_plugins
        from cirno_server.features.service import ensure_enabled_channel_dependencies

        plugins = discover_plugins()
        default_sections: dict[str, Any] = {}
        activations: dict[str, tuple[Any, list[tuple[str, Any]]]] = {}
        enabled_names: set[str] = set()
        for name, plugin in plugins.items():
            section = channel_section(
                self.runtimes.config,
                name,
                default_sections=default_sections,
                default_enabled=plugin.default_enabled,
            )
            if section is None:
                continue
            try:
                channel_setup_spec(name, plugin=plugin)
                specs = channel_instance_specs(plugin, section)
                runtime_specs = [
                    (channel_runtime_name(plugin, spec.instance_id), spec) for spec in specs
                ]
            except Exception as exc:
                logger.warning("Could not inspect {} channel activation: {}", name, exc)
                continue
            if not runtime_specs:
                continue
            collisions = sorted(
                set(self.runtimes.specs) & {runtime_name for runtime_name, _spec in runtime_specs}
            )
            if collisions:
                logger.warning(
                    "{} channel runtime name(s) are already claimed: {}",
                    name,
                    ", ".join(collisions),
                )
                continue
            for runtime_name, spec in runtime_specs:
                self.runtimes.specs[runtime_name] = (name, spec.instance_id)
            activations[name] = (plugin, runtime_specs)
            enabled_names.add(name)

        dependency_errors = ensure_enabled_channel_dependencies(enabled_names, plugins)
        for name, error in dependency_errors.items():
            self.runtimes.mark_owner_error(name, error)

        for name, (plugin, runtime_specs) in activations.items():
            if name in dependency_errors:
                continue
            try:
                cls = plugin.load_channel_class()
                built = [
                    (
                        runtime_name,
                        self.factory.build(
                            self.runtimes.config,
                            cls,
                            spec.config,
                            runtime_name=runtime_name,
                        ),
                    )
                    for runtime_name, spec in runtime_specs
                ]
                for runtime_name, channel in built:
                    self.runtimes.channels[runtime_name] = channel
                    self.runtimes.owners[runtime_name] = name
                    logger.info("{} channel enabled as {}", cls.display_name, runtime_name)
            except Exception as exc:
                self.runtimes.mark_owner_error(
                    name,
                    "Channel runtime could not be loaded. Check Cirno logs.",
                )
                logger.warning("{} channel not available: {}", name, exc)

    async def apply(
        self,
        action: str,
        name: str,
        instance_id: str | None = None,
    ) -> dict[str, Any]:
        """Apply a WebUI channel enable/disable action without restarting the Cirno.

        Returns a small transport-neutral result. ``handled=False`` means the
        optional feature is not a channel and should keep the default feature
        response semantics.
        """
        name = name.strip()
        instance_id = (instance_id or "").strip() or None
        if not name:
            return {"handled": False}

        from cirno_server.channels.registry import discover_plugins

        plugin = discover_plugins({name}).get(name)
        if plugin is None:
            return {"handled": False}
        if "always_enabled" in plugin.capabilities:
            return {
                "handled": True,
                "ok": False,
                "requires_restart": True,
                "message": f"{plugin.display_name} is always enabled and is applied on restart.",
            }

        lock = self.locks.setdefault(name, asyncio.Lock())
        async with lock:
            return await self._apply(action, name, instance_id, plugin)

    async def _apply(
        self,
        action: str,
        name: str,
        instance_id: str | None,
        plugin: ChannelPlugin,
    ) -> dict[str, Any]:
        from cirno_core.config.loader import load_config

        self.runtimes.config = load_config(self.config_path)
        section = channel_section(
            self.runtimes.config, name, default_enabled=plugin.default_enabled
        )
        channel_setup_spec(name, plugin=plugin)
        instance_id = resolve_channel_action_target(instance_id)

        if action == "disable":
            runtime_name = channel_runtime_name(plugin, instance_id)
            runtime_names = [runtime_name] if self.runtimes.owners.get(runtime_name) == name else []
            stopped = False
            for runtime_name in runtime_names:
                stopped = await self.runtimes.stop(runtime_name) or stopped
                self.runtimes.channels.pop(runtime_name, None)
                self.runtimes.owners.pop(runtime_name, None)
            self.runtimes.specs.pop(runtime_name, None)
            self.runtimes.errors.pop(runtime_name, None)
            return {
                "handled": True,
                "ok": True,
                "requires_restart": False,
                "message": f"{name} channel stopped." if stopped else f"{name} channel disabled.",
            }

        if action != "enable":
            return {"handled": True, "ok": False, "requires_restart": True}

        specs = channel_instance_specs(plugin, section) if section is not None else []
        specs = [spec for spec in specs if spec.instance_id == instance_id]
        if not specs:
            return {
                "handled": True,
                "ok": False,
                "requires_restart": True,
                "message": f"{name} channel config was not enabled.",
            }

        runtime_specs = [(channel_runtime_name(plugin, spec.instance_id), spec) for spec in specs]
        collisions = [
            runtime_name
            for runtime_name, _spec in runtime_specs
            if (
                runtime_name in self.runtimes.channels
                and self.runtimes.owners.get(runtime_name) != name
            )
        ]
        if collisions:
            return {
                "handled": True,
                "ok": False,
                "requires_restart": True,
                "message": (
                    "Channel runtime name(s) already owned by another channel: "
                    + ", ".join(sorted(collisions))
                ),
            }
        for runtime_name, spec in runtime_specs:
            self.runtimes.specs[runtime_name] = (name, spec.instance_id)

        try:
            cls = plugin.load_channel_class()
        except Exception:
            logger.exception("Failed to load {} channel after settings change", name)
            self.runtimes.mark_errors(
                (runtime_name for runtime_name, _spec in runtime_specs),
                "Channel runtime could not be loaded. Check Cirno logs.",
            )
            return {
                "handled": True,
                "ok": False,
                "requires_restart": False,
                "message": f"{name} channel could not be loaded. Check Cirno logs.",
            }

        try:
            built = [
                (
                    runtime_name,
                    self.factory.build(
                        self.runtimes.config,
                        cls,
                        spec.config,
                        runtime_name=runtime_name,
                    ),
                )
                for runtime_name, spec in runtime_specs
            ]
        except Exception:
            self.runtimes.mark_errors(
                (runtime_name for runtime_name, _spec in runtime_specs),
                "Channel runtime could not be built. Check Cirno logs.",
            )
            logger.exception("Failed to build {} channel after settings change", name)
            return {
                "handled": True,
                "ok": False,
                "requires_restart": False,
                "message": f"{name} channel could not be started. Check Cirno logs.",
            }

        runtime_names_to_replace = {runtime_name for runtime_name, _channel in built}
        for runtime_name in sorted(runtime_names_to_replace):
            if runtime_name not in self.runtimes.channels:
                continue
            await self.runtimes.stop(runtime_name)
            self.runtimes.channels.pop(runtime_name, None)
            self.runtimes.owners.pop(runtime_name, None)

        for runtime_name, channel in built:
            self.runtimes.channels[runtime_name] = channel
            self.runtimes.owners[runtime_name] = name
            self.runtimes.errors.pop(runtime_name, None)
            if self.runtimes.started:
                self.runtimes.start_task(runtime_name, channel)
            logger.info("{} channel applied without restart", runtime_name)
        if self.runtimes.started:
            await asyncio.sleep(0)
        failed = [
            runtime_name for runtime_name, _channel in built if runtime_name in self.runtimes.errors
        ]
        return {
            "handled": True,
            "ok": not failed,
            "requires_restart": False,
            "message": (
                f"{cls.display_name} channel failed to start. Check Cirno logs."
                if failed
                else f"{cls.display_name} channel applied without restart."
            ),
        }
