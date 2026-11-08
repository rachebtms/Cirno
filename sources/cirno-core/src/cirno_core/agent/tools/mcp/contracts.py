"""MCP contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Literal, Protocol, TypeVar

from cirno_core.agent.tools.base import Tool
from cirno_core.config.network import NetworkConfig

if TYPE_CHECKING:
    from cirno_core.config.tools import MCPServerConfig


class MCPConnection(Protocol):
    async def aclose(self) -> None: ...


_ReconnectCallback = Callable[[str, str, Tool], Awaitable[Tool | None]]


_MCPResultT = TypeVar("_MCPResultT")


MCPServerLoader = Callable[[], tuple[Mapping[str, "MCPServerConfig"], NetworkConfig]]


MCPRuntimeStatus = Literal["connecting", "connected", "failed"]
