"""MCP wrappers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Any, Literal, cast

from cirno_core.agent.tools.base import Tool, ToolResult
from cirno_core.agent.tools.context import tool_log_content_allowed
from cirno_core.utils.cancellation import task_is_cancelling
from loguru import logger

if TYPE_CHECKING:
    from mcp import ClientSession
    from mcp.types import Prompt, Resource
    from mcp.types import Tool as MCPToolDefinition

from cirno_core.agent.tools.mcp.contracts import _MCPResultT, _ReconnectCallback
from cirno_core.agent.tools.mcp.errors import _is_session_terminated, _is_transient
from cirno_core.agent.tools.mcp.names import _sanitize_mcp_tool_name
from cirno_core.agent.tools.mcp.results import _image_block_data_url, _mcp_image_tool_result
from cirno_core.agent.tools.mcp.schema import _normalize_schema_for_openai


class _MCPWrapperBase(Tool):
    """Common reconnect handling for wrappers bound to one MCP server session."""

    _plugin_discoverable = False
    _session: ClientSession
    _server_name: str
    _name: str

    def _set_mcp_connection(self, session: ClientSession, server_name: str) -> None:
        self._session = session
        self._server_name = server_name
        self._reconnect: _ReconnectCallback | None = None

    def set_reconnect_handler(self, reconnect: _ReconnectCallback) -> None:
        self._reconnect = reconnect

    async def _refresh_session_after_termination(
        self,
        exc: BaseException,
        already_refreshed: bool,
        capability_kind: str,
    ) -> bool:
        if already_refreshed or not _is_session_terminated(exc) or self._reconnect is None:
            return False
        logger.warning(
            "MCP {} '{}' session terminated; reconnecting server '{}' before retry",
            capability_kind,
            self._name,
            self._server_name,
        )
        refreshed_tool = await self._reconnect(self._server_name, self._name, self)
        refreshed_session = getattr(refreshed_tool, "_session", None)
        if refreshed_session is None:
            logger.warning(
                "MCP {} '{}' could not refresh session for server '{}'",
                capability_kind,
                self._name,
                self._server_name,
            )
            return False
        self._session = refreshed_session
        return True

    async def _request_with_recovery(
        self,
        request: Callable[[], Awaitable[_MCPResultT]],
        timeout: float,
        capability_kind: Literal["tool", "resource", "prompt"],
    ) -> _MCPResultT | ToolResult:
        """Recover requests only; rendering and reconnect/backoff failures stay outside replay."""
        from mcp.shared.exceptions import McpError

        operation = f"{capability_kind} {'read' if capability_kind == 'resource' else 'call'}"
        refreshed_session = False
        retried = False
        while True:
            try:
                return await asyncio.wait_for(request(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(
                    "MCP {} '{}' timed out after {}s", capability_kind, self._name, timeout
                )
                return ToolResult.error(f"(MCP {operation} timed out after {timeout}s)")
            except asyncio.CancelledError:
                # MCP SDK cancel scopes can leak cancellation without cancelling our task.
                if task_is_cancelling():
                    raise
                logger.warning(
                    "MCP {} '{}' was cancelled by server/SDK", capability_kind, self._name
                )
                return ToolResult.error(f"(MCP {operation} was cancelled)")
            except Exception as exc:
                if await self._refresh_session_after_termination(
                    exc, refreshed_session, capability_kind
                ):
                    refreshed_session = True
                    continue
                if capability_kind == "prompt" and isinstance(exc, McpError):
                    logger.opt(exception=exc if tool_log_content_allowed() else False).error(
                        "MCP prompt '{}' failed: code={} message={}",
                        self._name,
                        exc.error.code,
                        exc.error.message if tool_log_content_allowed() else "[content hidden]",
                    )
                    return ToolResult.error(
                        f"(MCP prompt call failed: {exc.error.message} [code {exc.error.code}])"
                    )
                if _is_transient(exc):
                    if not retried:
                        logger.warning(
                            "MCP {} '{}' hit transient error ({}), retrying once...",
                            capability_kind,
                            self._name,
                            type(exc).__name__,
                        )
                        retried = True
                        await asyncio.sleep(1)
                        continue
                    logger.opt(exception=exc if tool_log_content_allowed() else False).error(
                        "MCP {} '{}' failed after retry: {}",
                        capability_kind,
                        self._name,
                        type(exc).__name__,
                    )
                    return ToolResult.error(
                        f"(MCP {operation} failed after retry: {type(exc).__name__})"
                    )
                logger.opt(exception=exc if tool_log_content_allowed() else False).error(
                    "MCP {} '{}' failed: {}: {}",
                    capability_kind,
                    self._name,
                    type(exc).__name__,
                    exc if tool_log_content_allowed() else "[content hidden]",
                )
                return ToolResult.error(f"(MCP {operation} failed: {type(exc).__name__})")


class MCPToolWrapper(_MCPWrapperBase):
    """Wraps a single MCP server tool as a cirno Tool."""

    _plugin_discoverable = False

    def __init__(
        self,
        session: ClientSession,
        server_name: str,
        tool_def: MCPToolDefinition,
        tool_timeout: int = 30,
    ):
        self._set_mcp_connection(session, server_name)
        self._original_name = tool_def.name
        self._name = _sanitize_mcp_tool_name(f"mcp_{server_name}_{tool_def.name}")
        self._description = tool_def.description or tool_def.name
        raw_schema = tool_def.inputSchema or {"type": "object", "properties": {}}
        self._parameters = _normalize_schema_for_openai(raw_schema)
        self._tool_timeout = tool_timeout

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        result = await self._request_with_recovery(
            lambda: self._session.call_tool(self._original_name, arguments=kwargs),
            self._tool_timeout,
            "tool",
        )
        if isinstance(result, ToolResult):
            return result
        # Success — extract text and persist any image content as artifacts.
        try:
            rendered = self._render_call_result(result.content, kwargs)
            if getattr(result, "isError", False):
                return ToolResult.error(rendered)
            return rendered
        except Exception as exc:
            logger.opt(exception=tool_log_content_allowed()).error(
                "MCP tool '{}' failed while rendering result: {}: {}",
                self._name,
                type(exc).__name__,
                exc if tool_log_content_allowed() else "[content hidden]",
            )
            return ToolResult.error(f"(MCP tool returned malformed content: {type(exc).__name__})")

    def _render_call_result(self, content: Any, arguments: Mapping[str, Any]) -> str:
        """Turn MCP content blocks into a tool result string.

        Text is concatenated as before. Image blocks are decoded and saved as
        local artifacts so the
        model can deliver them via the message tool instead of trying to forward
        base64 — which would be truncated and bloat the context window.
        """
        from mcp import types

        text_parts: list[str] = []
        artifacts: list[dict[str, Any]] = []
        for block in content:
            if isinstance(block, types.TextContent):
                text_parts.append(block.text)
                continue
            data_url = _image_block_data_url(block, types)
            if data_url is not None:
                stored = self._store_image_block(data_url, arguments)
                if stored is not None:
                    artifacts.append(stored)
                else:
                    text_parts.append("(MCP tool returned an image that could not be stored)")
                continue
            text_parts.append(str(block))

        if artifacts:
            return _mcp_image_tool_result(text_parts, artifacts)
        return "\n".join(text_parts) or "(no output)"

    def _store_image_block(
        self, data_url: str, arguments: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        """Persist one image data URL as an artifact; return its metadata or None."""
        from cirno_core.utils.artifacts import ArtifactError, store_generated_image_artifact

        try:
            return store_generated_image_artifact(
                data_url,
                prompt=str(arguments.get("prompt") or ""),
                model=str(arguments.get("model") or ""),
                save_dir="generated",
                provider=f"mcp:{self._server_name}",
            )
        except (ArtifactError, OSError) as exc:
            logger.warning(
                "MCP tool '{}' returned an image that could not be stored: {}",
                self._name,
                exc if tool_log_content_allowed() else type(exc).__name__,
            )
            return None


class MCPResourceWrapper(_MCPWrapperBase):
    """Wraps an MCP resource URI as a read-only cirno Tool."""

    _plugin_discoverable = False

    def __init__(
        self,
        session: ClientSession,
        server_name: str,
        resource_def: Resource,
        resource_timeout: int = 30,
    ):
        self._set_mcp_connection(session, server_name)
        self._uri = resource_def.uri
        self._name = _sanitize_mcp_tool_name(f"mcp_{server_name}_resource_{resource_def.name}")
        desc = resource_def.description or resource_def.name
        self._description = f"[MCP Resource] {desc}\nURI: {self._uri}"
        self._parameters: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }
        self._resource_timeout = resource_timeout

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        from mcp import types

        result = await self._request_with_recovery(
            lambda: self._session.read_resource(self._uri),
            self._resource_timeout,
            "resource",
        )
        if isinstance(result, ToolResult):
            return str(result)
        parts: list[str] = []
        for block in result.contents:
            if isinstance(block, types.TextResourceContents):
                parts.append(block.text)
            elif isinstance(cast(object, block), types.BlobResourceContents):
                parts.append(f"[Binary resource: {len(block.blob)} bytes]")
            else:
                parts.append(str(block))
        return "\n".join(parts) or "(no output)"


class MCPPromptWrapper(_MCPWrapperBase):
    """Wraps an MCP prompt as a read-only cirno Tool."""

    _plugin_discoverable = False

    def __init__(
        self,
        session: ClientSession,
        server_name: str,
        prompt_def: Prompt,
        prompt_timeout: int = 30,
    ):
        self._set_mcp_connection(session, server_name)
        self._prompt_name = prompt_def.name
        self._name = _sanitize_mcp_tool_name(f"mcp_{server_name}_prompt_{prompt_def.name}")
        desc = prompt_def.description or prompt_def.name
        self._description = (
            f"[MCP Prompt] {desc}\n"
            "Returns a filled prompt template that can be used as a workflow guide."
        )
        self._prompt_timeout = prompt_timeout

        # Build parameters from prompt arguments
        properties: dict[str, Any] = {}
        required: list[str] = []
        for arg in prompt_def.arguments or []:
            prop: dict[str, Any] = {"type": "string"}
            if getattr(arg, "description", None):
                prop["description"] = arg.description
            properties[arg.name] = prop
            if arg.required:
                required.append(arg.name)
        self._parameters: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        from mcp import types

        result = await self._request_with_recovery(
            lambda: self._session.get_prompt(self._prompt_name, arguments=kwargs),
            self._prompt_timeout,
            "prompt",
        )
        if isinstance(result, ToolResult):
            return str(result)
        parts: list[str] = []
        for message in result.messages:
            content = message.content
            if isinstance(content, types.TextContent):
                parts.append(content.text)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, types.TextContent):
                        parts.append(block.text)
                    else:
                        parts.append(str(block))
            else:
                parts.append(str(content))
        return "\n".join(parts) or "(no output)"
