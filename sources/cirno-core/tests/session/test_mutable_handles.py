"""Renaming changes display metadata, not identity, history or queued execution."""
import asyncio

import pytest

from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.manager import SessionManager
from cirno_core.session.router_session import ensure_router_session
from cirno_core.session.session_handles import SessionHandleResolver
from cirno_core.session.state.handles import SessionHandleConflictError
from cirno_core.agent.tools.session_messages import SendSessionMessageTool
from cirno_core.bus.queue import MessageBus


@pytest.mark.asyncio
async def test_rename_keeps_id_and_long_runtime_records_without_reading_them(tmp_path, monkeypatch):
    sessions = SessionManager(tmp_path)
    router = sessions.get_or_create(ROUTER_SESSION_KEY)
    router.metadata.update(role="router", session_handle="cirno", title="@cirno", goal={"objective": "seven days", "state": "active"})
    router.add_message("user", "Original instructions mention @cirno")
    # The runtime tables may hold very large checkpoints and input payloads.
    sessions.save(router)
    with sessions._store.transaction() as db:
        db.execute("INSERT INTO checkpoints VALUES (?, ?)", (router.key, '{"evidence":"' + 'x' * 2_000_000 + '"}'))
        db.execute("INSERT INTO pending_inputs VALUES (?,?,?,?)", (router.key, "pending_inputs", 0, '{"source_session_key":"'+router.key+'"}'))
    resolver = SessionHandleResolver(sessions)
    before = await resolver.ahandle_for_session(router.key)
    original_read = sessions._store.read_metadata
    def header_only(key, *, include_runtime=True):
        assert include_runtime is False, "Rename must not deserialize a long checkpoint"
        return original_read(key, include_runtime=include_runtime)
    monkeypatch.setattr(sessions._store, "read_metadata", header_only)
    try:
        result = await sessions.state.rename_session_handle(router.key, "@Snow_9")
        assert result == {"id": before.id, "name": "snow_9"}
        assert (await resolver.aresolve(before.id)).session_key == router.key
        assert await resolver.aresolve("@cirno") is None
        assert (await resolver.aresolve("@snow_9")).id == before.id
        with sessions._store.transaction(write=False) as db:
            assert db.execute("SELECT length(record) FROM checkpoints WHERE session_key=?", (router.key,)).fetchone()[0] > 2_000_000
            assert db.execute("SELECT count(*) FROM pending_inputs WHERE session_key=?", (router.key,)).fetchone()[0] == 1
            assert db.execute("SELECT count(*) FROM messages WHERE session_key=?", (router.key,)).fetchone()[0] == 1
        assert (await sessions.state.read_metadata(router.key, include_runtime=False))["metadata"]["goal"] == router.metadata["goal"]
    finally:
        await sessions.state.aclose()


@pytest.mark.asyncio
async def test_concurrent_rename_rejects_collision_without_renaming_the_other_conversation(tmp_path):
    sessions = SessionManager(tmp_path)
    for key in (ROUTER_SESSION_KEY, "websocket:worker"):
        sessions.save(sessions.get_or_create(key))
    resolver = SessionHandleResolver(sessions)
    before = await resolver.alist_all_by_key()
    try:
        results = await asyncio.gather(*(sessions.state.rename_session_handle(key, "snow_9") for key in before), return_exceptions=True)
        assert sum(isinstance(result, SessionHandleConflictError) for result in results) == 1
        after = await resolver.alist_all_by_key()
        assert len({handle.name for handle in after.values()}) == 2
        assert {key: handle.id for key, handle in after.items()} == {key: handle.id for key, handle in before.items()}
        for key, result in zip(before, results):
            if isinstance(result, SessionHandleConflictError):
                assert after[key].name == before[key].name
    finally:
        await sessions.state.aclose()


@pytest.mark.asyncio
async def test_saved_tool_target_id_routes_after_rename_and_restart_bootstrap_does_not_restore_old_name(tmp_path):
    sessions = SessionManager(tmp_path)
    for key in (ROUTER_SESSION_KEY, "websocket:worker"):
        sessions.save(sessions.get_or_create(key))
    resolver = SessionHandleResolver(sessions)
    before = await resolver.ahandle_for_session(ROUTER_SESSION_KEY)
    try:
        await sessions.state.rename_session_handle(ROUTER_SESSION_KEY, "snow_9")
        await sessions.state.rename_session_handle("websocket:worker", "cirno")
        from cirno_core.session.roles import conversation_role
        assert conversation_role((await resolver.aresolve("@cirno")).session_key).name == "worker"
        assert conversation_role((await resolver.aresolve(before.id)).session_key).name == "router"
        await ensure_router_session(sessions, handle="cirno")  # initial registration seed
        bus = MessageBus()
        tool = SendSessionMessageTool(sessions=sessions, bus=bus)
        assert await tool.enqueue(source_session_key="websocket:worker", target_handle=before.id, content="Research completed", expect_reply=False) == "@snow_9"
        inbound = await bus.consume_inbound()
        assert inbound.session_key == ROUTER_SESSION_KEY
        assert (await resolver.aresolve(before.id)).name == "snow_9"
    finally:
        await sessions.state.aclose()
