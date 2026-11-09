"""Owner controls for the Router's periodic heartbeat."""
import asyncio
from pathlib import Path
from typing import Any

from cirno_core.bus.outbound_events import SessionUpdatedEvent
from cirno_core.bus.queue import MessageBus
from cirno_core.config.loader import load_config
from cirno_core.runtime.heartbeat import heartbeat_paused
from cirno_core.session.keys import ROUTER_CHAT_ID, ROUTER_SESSION_KEY
from cirno_core.session.manager import SessionManager
from cirno_core.session.router_session import ensure_router_session


async def router_heartbeat_action(action: str, values: dict[str, Any], *, sessions: SessionManager, bus: MessageBus, config_path: Path | None = None) -> dict[str, bool]:
    await ensure_router_session(sessions)
    if action == "router.heartbeat.update":
        paused = values.get("paused")
        if not isinstance(paused, bool):
            raise ValueError("paused must be a boolean")
        await sessions.state.update_metadata(ROUTER_SESSION_KEY, {"heartbeat_paused": paused})
        await bus.publish_event(SessionUpdatedEvent(scope="metadata"), channel="websocket", chat_id=ROUTER_CHAT_ID)
    config = await asyncio.to_thread(load_config, config_path)
    return {"paused": await heartbeat_paused(sessions),
            "enabled": config.agents.defaults.heartbeat.enabled}
