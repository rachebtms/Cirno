"""First-awakening files and follow-ups retain their admitted Home and source."""

import pytest
from cirno_core.bus.queue import MessageBus
from cirno_core.config.home import set_instance_path
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.manager import SessionManager
from cirno_core.session.sqlite_store import SessionConflictError
from cirno_server.webui.auth.router_identity import RouterIdentity


@pytest.mark.parametrize("stage", ["initialize", "wake"])
async def test_router_awakening_uses_its_captured_agent_home(tmp_path, stage):
    first, second = tmp_path / "first", tmp_path / "second"
    set_instance_path(first)
    sessions = SessionManager(first / "workspace", sessions_root=first / "state" / "sessions")
    bus = MessageBus()
    identity = RouterIdentity(sessions, bus)
    try:
        if stage == "wake":
            await identity.initialize("fixture", registration=True)
        set_instance_path(second)
        if stage == "initialize":
            await identity.initialize("fixture", registration=True)
            assert (first / "home" / "BOOTSTRAP.md").is_file()
            assert not (second / "home").exists()
        else:
            assert await identity.wake("en")
            assert bus.inbound_size == 1
    finally:
        await sessions.state.aclose()


async def test_reset_after_wake_journal_cannot_mark_the_new_router_generation_as_awakened(tmp_path, monkeypatch):
    set_instance_path(tmp_path)
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "state" / "sessions")
    bus = MessageBus()
    identity = RouterIdentity(sessions, bus)
    await identity.initialize("fixture", registration=True)
    queue = sessions.state.queue_followup

    async def reset_after_queue(key, message):
        result = await queue(key, message)
        await sessions.state.reset(key)
        await sessions.state.import_messages(key, [{"role": "user", "content": "Replacement"}])
        return result

    monkeypatch.setattr(sessions.state, "queue_followup", reset_after_queue)
    try:
        try:
            await identity.wake("en")
        except SessionConflictError:
            pass
        header = await sessions.state.read_header(ROUTER_SESSION_KEY)
        assert not header.metadata.get("awakening_started")
        assert bus.inbound_size == 0
    finally:
        await sessions.state.aclose()
