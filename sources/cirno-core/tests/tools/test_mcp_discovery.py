"""Discovery failures must remain visible without dropping working capabilities."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.tools.mcp.discovery import (
    list_catalog,
    optional_catalog,
    register_capabilities,
)
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.config.tools import MCPServerConfig
from loguru import logger
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, ServerCapabilities, ToolsCapability


@pytest.mark.asyncio
async def test_unadvertised_catalogs_are_never_requested():
    session = SimpleNamespace(
        list_tools=AsyncMock(return_value=SimpleNamespace(tools=[], nextCursor=None)),
        list_resources=AsyncMock(side_effect=AssertionError("unadvertised resources")),
        list_prompts=AsyncMock(side_effect=AssertionError("unadvertised prompts")),
    )
    registry = ToolRegistry()
    assert await register_capabilities(
        session, ServerCapabilities(tools=ToolsCapability()), "test",
        MCPServerConfig(command="fake"), registry,
    ) == 0
    session.list_tools.assert_awaited_once()
    session.list_resources.assert_not_awaited()
    session.list_prompts.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["resources", "prompts"])
async def test_repeated_cursor_discards_incomplete_catalog_and_reports_failure(kind):
    request = AsyncMock(return_value=SimpleNamespace(**{kind: ["first"]}, nextCursor="loop"))
    records = []
    sink = logger.add(lambda message: records.append(message.record), level="WARNING")
    try:
        assert await optional_catalog(request, kind, "research") == []
    finally:
        logger.remove(sink)
    assert request.await_count == 2
    assert any(f"{kind}/list failed (ValueError)" in record["message"] for record in records)


@pytest.mark.asyncio
@pytest.mark.parametrize("code, level", [(-32601, "DEBUG"), (-32603, "WARNING")])
async def test_unsupported_method_and_server_failure_have_distinct_severity(code, level):
    request = AsyncMock(side_effect=McpError(ErrorData(code=code, message="not available")))
    records = []
    sink = logger.add(lambda message: records.append(message.record), level="DEBUG")
    try:
        assert await optional_catalog(request, "resources", "test") == []
    finally:
        logger.remove(sink)
    assert len(records) == 1
    assert records[0]["level"].name == level


@pytest.mark.asyncio
async def test_catalog_failure_never_returns_a_partial_page():
    request = AsyncMock(side_effect=[
        SimpleNamespace(tools=["first"], nextCursor="second"),
        OSError("connection lost"),
    ])
    with pytest.raises(OSError, match="connection lost"):
        await list_catalog(request, "tools")


@pytest.mark.asyncio
async def test_distinct_upstream_names_survive_provider_name_normalization():
    from mcp.types import CallToolResult, TextContent, Tool

    session = SimpleNamespace(
        list_tools=AsyncMock(return_value=SimpleNamespace(tools=[
            Tool(name="read.notes", inputSchema={"type": "object"}),
            Tool(name="read_notes", inputSchema={"type": "object"}),
        ], nextCursor=None)),
        call_tool=AsyncMock(side_effect=lambda name, **kwargs: CallToolResult(
            content=[TextContent(type="text", text=name)],
        )),
    )
    registry = ToolRegistry()
    await register_capabilities(session, ServerCapabilities(tools=ToolsCapability()), "test",
                                MCPServerConfig(command="fake"), registry)
    assert len(registry.tool_names) == 2
    results = {await registry.execute(name, {}) for name in registry.tool_names}
    assert results == {"read.notes", "read_notes"}


@pytest.mark.asyncio
async def test_duplicate_catalog_does_not_leave_partially_registered_tools():
    from mcp.types import Tool

    session = SimpleNamespace(list_tools=AsyncMock(return_value=SimpleNamespace(tools=[
        Tool(name="first", inputSchema={"type": "object"}),
        Tool(name="duplicate", inputSchema={"type": "object"}),
        Tool(name="duplicate", inputSchema={"type": "object"}),
    ], nextCursor=None)))
    registry = ToolRegistry()
    with pytest.raises(ValueError, match="duplicate model-facing name"):
        await register_capabilities(session, ServerCapabilities(tools=ToolsCapability()), "test",
                                    MCPServerConfig(command="fake"), registry)
    assert registry.tool_names == []
