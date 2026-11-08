"""Channel manager for coordinating chat channels."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.config.schema import Config
from cirno_core.utils.restart import (
    RestartNotice,
    consume_restart_notice_from_env,
    format_restart_completed_message,
)
from loguru import logger

from cirno_server.channels.activation import ChannelActivation
from cirno_server.channels.base import BaseChannel
from cirno_server.channels.delivery.dispatcher import OutboundDispatcher
from cirno_server.channels.delivery.inbox import InboxDelivery
from cirno_server.channels.delivery.queue import OutboundQueue
from cirno_server.channels.factory import ChannelFactory
from cirno_server.channels.runtimes import ChannelRuntimes
from cirno_server.channels.webui_binding import WebUIChannelBindings

if TYPE_CHECKING:
    from cirno_core.agent.subagents.manager import SubagentManager
    from cirno_core.cron.service import CronService
    from cirno_core.session.manager import SessionManager
    from cirno_core.triggers.local_store import LocalTriggerStore


_RESTART_NOTICE_START_TIMEOUT_S = 30.0
_RESTART_NOTICE_START_POLL_S = 0.25


class ChannelManager:
    """
    Manages chat channels and coordinates message routing.

    Responsibilities:
    - Initialize the Web UI and enabled personal channels
    - Start/stop channels
    - Route outbound messages
    """

    def __init__(
        self,
        config: Config,
        bus: MessageBus,
        *,
        session_manager: "SessionManager | None" = None,
        cron_service: CronService | None = None,
        local_trigger_store: LocalTriggerStore | None = None,
        webui_runtime_model_name: Callable[[], str | None] | None = None,
        webui_context_usage: Callable[[str], Awaitable[dict[str, Any]]] | None = None,
        webui_maintenance: Callable[[], Any] | None = None,
        webui_refresh_runtime_config: Callable[[], None] | None = None,
        webui_cron_pending_job_ids: Callable[[str], set[str]] | None = None,
        webui_local_trigger_pending_ids: Callable[[str], set[str]] | None = None,
        webui_static_dist: bool = True,
        webui_mcp_runtime_status: Callable[[], Mapping[str, str]] | None = None,
        webui_mcp_reload: Callable[[], Awaitable[dict[str, Any]]] | None = None,
        webui_skill_state_action: Callable[[set[str]], None] | None = None,
        webui_recovery_action: (
            Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None
        ) = None,
        webui_subagent_manager: SubagentManager | None = None,
        webui_discard_session: Callable[[str], Awaitable[None]] | None = None,
        config_path: Path | None = None,
    ):
        if config_path is None:
            from cirno_core.config.loader import get_config_path

            config_path = get_config_path()
        self._config_path = config_path.expanduser().resolve(strict=False)
        self.bus = bus
        self.runtimes = ChannelRuntimes(config, bus, lambda name: self.delivery.cancel(name))
        self._dispatch_task: asyncio.Task[None] | None = None
        self._restart_notice_task: asyncio.Task[None] | None = None
        self.delivery = OutboundQueue(
            bus,
            self._config_path,
            session_manager,
            lambda: self.runtimes.config,
            self.get_channel,
            lambda name: name in self.runtimes.stopping,
        )
        self.notifications = InboxDelivery(
            bus,
            self._config_path,
            session_manager,
            self.get_channel,
        )

        self.dispatcher = OutboundDispatcher(
            bus, self.delivery, self.notifications, self.get_channel
        )

        factory = ChannelFactory(
            bus,
            WebUIChannelBindings(
                session_manager=session_manager,
                config_path=self._config_path,
                cron_service=cron_service,
                local_trigger_store=local_trigger_store,
                runtime_model_name=webui_runtime_model_name,
                context_usage=webui_context_usage,
                maintenance=webui_maintenance,
                refresh_runtime_config=webui_refresh_runtime_config,
                cron_pending_job_ids=webui_cron_pending_job_ids,
                local_trigger_pending_ids=webui_local_trigger_pending_ids,
                static_dist=webui_static_dist,
                mcp_runtime_status=webui_mcp_runtime_status,
                mcp_reload=webui_mcp_reload,
                skill_state_action=webui_skill_state_action,
                recovery_action=webui_recovery_action,
                subagent_manager=webui_subagent_manager,
                discard_session=webui_discard_session,
                feature_action=lambda action, name, instance_id=None: self.activation.apply(
                    action, name, instance_id
                ),
                runtime_status=self.runtimes.status,
            ),
        )
        self.activation = ChannelActivation(self.runtimes, factory, self._config_path)
        self.activation.initialize()
        self._remove_delivery_check: Callable[[], None] | None = (
            self.bus.admission.register_pending_work(lambda: self.has_pending_delivery)
        )

    async def start_all(self) -> None:
        """Start all channels and the outbound dispatcher."""
        if self._remove_delivery_check is None:
            self._remove_delivery_check = self.bus.admission.register_pending_work(
                lambda: self.has_pending_delivery,
            )
        if not self.runtimes.channels:
            logger.warning("No channels enabled")
            return

        self.runtimes.started = True
        # Start outbound dispatcher
        self._dispatch_task = asyncio.create_task(self.dispatcher.run())

        # Start channels
        tasks: list[asyncio.Task[None]] = []
        for name, channel in self.runtimes.channels.items():
            tasks.append(self.runtimes.start_task(name, channel))

        self._notify_restart_done_if_needed()

        # Wait for all to complete (they should run forever)
        await asyncio.gather(*tasks, return_exceptions=True)

    def _notify_restart_done_if_needed(self) -> asyncio.Task[None] | None:
        """Schedule restart completion after the target channel starts."""
        notice = consume_restart_notice_from_env()
        if not notice:
            return None
        self._restart_notice_task = asyncio.create_task(
            self._send_restart_notice_when_started(notice)
        )
        return self._restart_notice_task

    async def _send_restart_notice_when_started(
        self,
        notice: RestartNotice,
        *,
        timeout_s: float = _RESTART_NOTICE_START_TIMEOUT_S,
        poll_s: float = _RESTART_NOTICE_START_POLL_S,
    ) -> None:
        """Deliver a restart notice after the target channel starts."""
        await self.bus.admission.wait_until_open()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        target = self.runtimes.channels.get(notice.channel)
        if target is None:
            logger.warning("Restart notice target channel is not enabled: {}", notice.channel)
            return
        if notice.channel == "websocket":
            # Reconnect and recovery are already represented by WebSocket
            # protocol state. A generic restart-complete notice must not
            # masquerade as a recovery transition and overwrite a real
            # awaiting-user checkpoint in connected clients.
            return

        while not target.is_running:
            remaining = deadline - loop.time()
            if remaining <= 0:
                logger.warning(
                    "Restart notice target did not start: {}:{}",
                    notice.channel,
                    notice.chat_id,
                )
                return
            await asyncio.sleep(min(poll_s, remaining))

        await self.delivery.retry.send(
            target,
            OutboundMessage(
                channel=notice.channel,
                chat_id=notice.chat_id,
                content=format_restart_completed_message(notice.started_at_raw),
                metadata=dict(notice.metadata or {}),
            ),
            deadline=deadline,
        )

    async def stop_all(self) -> None:
        """Stop all channels and the dispatcher."""
        logger.info("Stopping all channels...")
        self.runtimes.started = False
        self.notifications.close()

        failures: list[BaseException] = []
        for task in (self._dispatch_task, self._restart_notice_task):
            if task is None:
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                failures.append(exc)
        self._dispatch_task = None
        self._restart_notice_task = None

        names = list(self.runtimes.channels)
        results = await asyncio.gather(
            *(self.runtimes.stop(name) for name in names),
            return_exceptions=True,
        )
        for name, result in zip(names, results, strict=True):
            if isinstance(result, BaseException):
                result.add_note(f"Stopping channel {name}")
                failures.append(result)
        if self._remove_delivery_check is not None:
            self._remove_delivery_check()
            self._remove_delivery_check = None
        if failures:
            raise BaseExceptionGroup("Channel shutdown failed", failures)

    @property
    def has_pending_delivery(self) -> bool:
        """A synchronous idle check, including channel-owned transport queues.

        Read on the Cirno event loop immediately before closing admission.
        This is delivery liveness, not proof that every channel writer stopped.
        """
        return bool(
            self.bus.outbound_size
            or self.dispatcher.pending
            or self.dispatcher.dispatching
            or self.delivery.tasks
            or (self._restart_notice_task is not None and not self._restart_notice_task.done())
            or any(channel.has_pending_delivery for channel in self.runtimes.channels.values())
        )

    def get_channel(self, name: str) -> BaseChannel | None:
        """Get a channel by name."""
        return self.runtimes.channels.get(name)

    def get_status(self) -> dict[str, Any]:
        return self.runtimes.status()

    @property
    def enabled_channels(self) -> list[str]:
        """Get list of enabled channel names."""
        return list(self.runtimes.channels.keys())
