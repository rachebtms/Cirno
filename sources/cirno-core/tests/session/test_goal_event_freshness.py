"""Delayed Goal events cannot restore old status into a newer conversation."""

import pytest
from cirno_core.bus.queue import MessageBus
from cirno_core.bus.runtime_events import GoalStateChanged, RuntimeEventContext
from cirno_core.session.goal_state import goal_state_ws_blob
from cirno_core.session.manager import SessionManager
from cirno_core.session.webui_turns.coordinator import WebuiTurnCoordinator


@pytest.mark.parametrize("change", ["deleted", "replaced", "same_generation", "legacy_context"])
async def test_goal_event_publishes_only_current_saved_state(tmp_path, change):
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    key = "websocket:worker"
    header = await sessions.state.get_header(key)
    stale = {"goal_state": {"goal_id": "old", "status": "active", "objective": "Old work"}}
    await sessions.state.update_metadata(key, stale)
    bus = MessageBus()
    coordinator = WebuiTurnCoordinator(bus, sessions, lambda _work: None)
    unsubscribe = coordinator.subscribe()
    event = GoalStateChanged(
        context=RuntimeEventContext(
            channel="websocket",
            chat_id="worker",
            session_key=key,
            session_generation=None if change == "legacy_context" else header.generation,
        ),
        session_metadata=stale,
    )
    try:
        if change == "deleted":
            await sessions.state.delete(key)
        else:
            if change == "replaced":
                await sessions.state.reset(key)
            await sessions.state.update_metadata(
                key,
                {
                    "goal_state": {
                        "goal_id": "new" if change == "replaced" else "old",
                        "status": "stopped",
                        "objective": "Saved current work",
                    }
                },
            )
        await bus.publish(event)
        if change in {"deleted", "replaced"}:
            assert bus.outbound.empty(), "A retired generation published stale Goal state"
        else:
            current = (await sessions.state.read_metadata(key))["metadata"]
            outbound = bus.outbound.get_nowait()
            assert outbound.event.goal_state == goal_state_ws_blob(current)
            assert bus.outbound.empty()
    finally:
        unsubscribe()
        await sessions.state.aclose()
