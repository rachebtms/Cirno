"""MCP connections."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from cirno_core.agent.tools.mcp.contracts import MCPConnection
from cirno_core.utils.cancellation import shield_and_drain, task_is_cancelling
from loguru import logger


async def close_mcp_connection(name: str, connection: MCPConnection) -> Exception | None:
    try:
        await connection.aclose()
    except asyncio.CancelledError:
        if task_is_cancelling():
            raise
        logger.warning("MCP server '{}': connection cleanup was cancelled by the transport", name)
        return RuntimeError("Connection cleanup was cancelled by the transport")
    except Exception as exc:
        logger.warning("MCP server '{}': connection cleanup failed ({})", name, type(exc).__name__)
        return exc
    return None


async def close_mcp_connections(connections: Mapping[str, MCPConnection]) -> dict[str, Exception]:
    """Close every connection, report failures, and settle before propagating Stop."""
    cancellation: asyncio.CancelledError | None = None
    errors: dict[str, Exception] = {}
    for name, connection in connections.items():
        try:
            error = await close_mcp_connection(name, connection)
            if error is not None:
                errors[name] = error
        except asyncio.CancelledError as exc:
            cancellation = cancellation or exc
    if cancellation is not None:
        raise cancellation
    return errors


class OwnedMCPConnection:
    """Close an MCP transport from the task that originally opened it."""

    def __init__(self, owner: asyncio.Task[None], close_requested: asyncio.Event) -> None:
        self._owner = owner
        self._close_requested = close_requested

    async def aclose(self) -> None:
        self._close_requested.set()
        try:
            await shield_and_drain(self._owner)
        except asyncio.CancelledError:
            if task_is_cancelling() or not self._owner.cancelled():
                raise
