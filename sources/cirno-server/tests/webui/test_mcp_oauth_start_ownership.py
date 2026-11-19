"""Browser authorization replacement is serialized through old-flow cleanup."""

import asyncio

from cirno_core.config.tools import MCPServerConfig
from cirno_core.runtime.admission import RuntimeAdmission
from cirno_server.webui.mcp.oauth_api import McpOAuthManager


async def test_concurrent_same_server_starts_leave_one_live_authorization_owner(monkeypatch):
    manager = McpOAuthManager(RuntimeAdmission())
    closing = asyncio.Event()
    release = asyncio.Event()
    active = set()
    original = None

    async def connect(flow, _handlers):
        active.add(flow.flow_id)
        flow.authorization_ready.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            if flow.flow_id == original:
                closing.set()
                await release.wait()
            raise
        finally:
            active.discard(flow.flow_id)

    monkeypatch.setattr(manager, "_connect", connect)
    options = {"reload_mcp": lambda: None}
    config = MCPServerConfig(type="streamableHttp", auth="oauth", url="https://fixture.test/mcp")
    async def start():
        return await manager.start("fixture", config, "https://fixture.test/v0/mcp/oauth/callback", **options)

    first = await start()
    original = first["flow_id"]
    replacements = []
    try:
        replacements.append(asyncio.create_task(start()))
        await asyncio.wait_for(closing.wait(), timeout=1)
        replacements.append(asyncio.create_task(start()))
        await asyncio.sleep(0)
        release.set()
        outcomes = await asyncio.wait_for(asyncio.gather(*replacements), timeout=1)
        assert len(active) == 1, "Two starts replaced the same old flow without replacing each other"
        assert outcomes[-1]["flow_id"] in active
    finally:
        release.set()
        for task in replacements:
            if not task.done():
                task.cancel()
        await asyncio.gather(*replacements, return_exceptions=True)
        await manager.close()
    assert not active


async def test_cancelled_replacement_finishes_old_cleanup_without_starting_a_new_flow(monkeypatch):
    manager = McpOAuthManager(RuntimeAdmission())
    closing = asyncio.Event()
    release = asyncio.Event()
    cleaned = asyncio.Event()

    async def connect(flow, _handlers):
        flow.authorization_ready.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            closing.set()
            await release.wait()
            cleaned.set()
            raise

    monkeypatch.setattr(manager, "_connect", connect)
    config = MCPServerConfig(type="streamableHttp", auth="oauth", url="https://fixture.test/mcp")
    async def start():
        return await manager.start("fixture", config, "https://fixture.test/v0/mcp/oauth/callback", reload_mcp=lambda: None)

    await start()
    replacement = asyncio.create_task(start())
    try:
        await asyncio.wait_for(closing.wait(), timeout=1)
        replacement.cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        release.set()
        outcome = await asyncio.wait_for(asyncio.gather(replacement, return_exceptions=True), timeout=1)
        assert isinstance(outcome[0], asyncio.CancelledError)
        assert cleaned.is_set(), "Cancelling the requester interrupted its old connection cleanup"
        assert len(manager._flows) == 1, "A cancelled start still created a replacement authorization flow"
    finally:
        release.set()
        if not replacement.done():
            replacement.cancel()
        await asyncio.gather(replacement, return_exceptions=True)
        await manager.close()
