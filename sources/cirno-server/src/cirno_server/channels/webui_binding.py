"""Application dependencies used when constructing the Web UI channel."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cirno_core.bus.queue import MessageBus
from cirno_core.config.schema import Config
from loguru import logger

if TYPE_CHECKING:
    from cirno_core.agent.subagents.manager import SubagentManager
    from cirno_core.cron.service import CronService
    from cirno_core.session.manager import SessionManager
    from cirno_core.triggers.local_store import LocalTriggerStore

    from cirno_server.webui.services import ServerServices


def _default_webui_dist() -> Path | None:
    """Return the absolute path to the bundled webui dist directory if it exists."""
    from cirno_server.webui.build import default_webui_dist_dir

    candidate = default_webui_dist_dir()
    return candidate if (candidate / "index.html").is_file() else None


@dataclass(frozen=True)
class WebUIChannelBindings:
    config_path: Path
    session_manager: SessionManager | None
    cron_service: CronService | None
    local_trigger_store: LocalTriggerStore | None
    runtime_model_name: Callable[[], str | None] | None
    context_usage: Callable[[str], Awaitable[dict[str, Any]]] | None
    maintenance: Callable[[], Any] | None
    refresh_runtime_config: Callable[[], None] | None
    cron_pending_job_ids: Callable[[str], set[str]] | None
    local_trigger_pending_ids: Callable[[str], set[str]] | None
    static_dist: bool
    mcp_runtime_status: Callable[[], Mapping[str, str]] | None
    mcp_reload: Callable[[], Awaitable[dict[str, Any]]] | None
    skill_state_action: Callable[[set[str]], None] | None
    recovery_action: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None
    subagent_manager: SubagentManager | None
    discard_session: Callable[[str], Awaitable[None]] | None
    feature_action: Callable[[str, str, str | None], Awaitable[dict[str, Any]]]
    runtime_status: Callable[[], dict[str, Any]]

    def services(self, config: Config, section: Any, bus: MessageBus) -> ServerServices:
        from cirno_server.channels.websocket.config import WebSocketConfig
        from cirno_server.webui.services import build_server_services

        parsed = WebSocketConfig.model_validate(section)
        static_path = _default_webui_dist() if self.static_dist else None
        workspace = Path(config.workspace_path)
        gateway = build_server_services(
            config=parsed,
            bus=bus,
            session_manager=self.session_manager,
            static_dist_path=static_path,
            workspace_path=workspace,
            default_restrict_to_workspace=config.tools.restrict_to_workspace,
            config_path=self.config_path,
            disabled_skills=set(config.agents.defaults.disabled_skills),
            runtime_model_name=self.runtime_model_name,
            context_usage=self.context_usage,
            maintenance=self.maintenance,
            refresh_runtime_config=self.refresh_runtime_config,
            cron_service=self.cron_service,
            local_trigger_store=self.local_trigger_store,
            cron_pending_job_ids=self.cron_pending_job_ids,
            local_trigger_pending_ids=self.local_trigger_pending_ids,
            channel_feature_action=self.feature_action,
            channel_runtime_status=self.runtime_status,
            mcp_runtime_status=self.mcp_runtime_status,
            mcp_reload=self.mcp_reload,
            skill_state_action=self.skill_state_action,
            recovery_action=self.recovery_action,
            subagent_manager=self.subagent_manager,
            discard_session=self.discard_session,
            logger=logger,
        )
        return gateway
