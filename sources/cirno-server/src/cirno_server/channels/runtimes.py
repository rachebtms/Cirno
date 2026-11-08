"""Own adapter instances, their runners and lifecycle status."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from contextlib import suppress
from typing import Any

from cirno_core.bus.queue import MessageBus
from cirno_core.config.schema import Config
from loguru import logger

from cirno_server.channels.base import BaseChannel


class ChannelRuntimes:
    def __init__(
        self,
        config: Config,
        bus: MessageBus,
        cancel_delivery: Callable[[str], Awaitable[None]],
    ) -> None:
        self.config = config
        self.bus = bus
        self.cancel_delivery = cancel_delivery
        self.channels: dict[str, BaseChannel] = {}
        self.owners: dict[str, str] = {}
        self.specs: dict[str, tuple[str, str]] = {}
        self.errors: dict[str, str] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.stopping: set[str] = set()
        self.started = False

    def mark_owner_error(self, owner: str, message: str) -> None:
        self.mark_errors(
            (
                runtime_name
                for runtime_name, (
                    runtime_owner,
                    _instance_id,
                ) in self.specs.items()
                if runtime_owner == owner
            ),
            message,
        )

    def mark_errors(self, runtime_names: Iterable[str], message: str) -> None:
        for runtime_name in runtime_names:
            self.errors[runtime_name] = message

    async def start(self, name: str, channel: BaseChannel) -> None:
        """Start a channel and log any exceptions."""
        errors = self.errors
        errors.pop(name, None)
        try:
            if name != "websocket":
                await self.bus.admission.wait_until_open()
            await channel.start()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            public_error = channel.start_error_message(exc)
            errors[name] = public_error or "Channel failed to start. Check Cirno logs."
            if public_error:
                logger.error("Failed to start channel {}: {}", name, public_error)
            else:
                logger.exception("Failed to start channel {}", name)

    def start_task(self, name: str, channel: BaseChannel) -> asyncio.Task[None]:
        logger.info("Starting {} channel...", name)
        task = asyncio.create_task(self.start(name, channel))
        self.tasks[name] = task
        return task

    async def stop(self, name: str) -> bool:
        self.stopping.add(name)
        try:
            await self.cancel_delivery(name)
            return await self._stop_runtime(name)
        finally:
            self.stopping.discard(name)

    async def _stop_runtime(self, name: str) -> bool:
        channel = self.channels.get(name)
        if channel is None:
            self.tasks.pop(name, None)
            return False

        task = self.tasks.pop(name, None)
        try:
            await channel.stop()
            logger.info("Stopped {} channel", name)
        except asyncio.CancelledError:
            current_task = asyncio.current_task()
            if current_task is not None and current_task.cancelling():
                raise
            logger.debug("Channel {} stop task was already cancelled", name)
        finally:
            if task is not None and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        return True

    def status(self) -> dict[str, Any]:
        """Return actual runtime state, including enabled runtimes that failed."""
        owners = self.owners
        runtime_specs = dict(self.specs)
        for runtime_name in self.channels:
            runtime_specs.setdefault(
                runtime_name,
                (owners.get(runtime_name, runtime_name), "default"),
            )
        tasks = self.tasks
        errors = self.errors
        status: dict[str, Any] = {}
        for runtime_name, (owner, instance_id) in runtime_specs.items():
            channel = self.channels.get(runtime_name)
            task = tasks.get(runtime_name)
            error = errors.get(runtime_name)
            running = bool(channel and channel.is_running)
            if error:
                state = "failed"
            elif running:
                state = "running"
            elif task is not None and not task.done():
                state = "starting"
            else:
                state = "stopped"
            status[runtime_name] = {
                "enabled": True,
                "running": running,
                "state": state,
                "owner": owner,
                "instance_id": instance_id,
            }
            if error:
                status[runtime_name]["error"] = error
        return status
