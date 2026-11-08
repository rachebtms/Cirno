"""Tools configuration models."""

from __future__ import annotations

from typing import Literal

from cirno_core.agent.tools.cli_apps_config import CliAppsToolConfig
from cirno_core.agent.tools.filesystem_config import FileToolsConfig
from cirno_core.agent.tools.self_config import MyToolConfig
from cirno_core.agent.tools.shell_config import ExecToolConfig
from cirno_core.agent.tools.web_config import WebToolsConfig
from cirno_core.config.base import Base
from pydantic import AliasChoices, Field


class MCPServerConfig(Base):
    """MCP server connection configuration (stdio or HTTP)."""

    type: Literal["stdio", "sse", "streamableHttp"] | None = None  # auto-detected if omitted
    auth: Literal["oauth"] | None = None  # Remote MCP OAuth; tokens are stored outside config
    command: str = ""  # Stdio: command to run (e.g. "npx")
    args: list[str] = Field(default_factory=list)  # Stdio: command arguments
    env: dict[str, str] = Field(default_factory=dict)  # Stdio: extra env vars
    cwd: str = ""  # Stdio: working directory for MCP server runtime artifacts
    url: str = ""  # HTTP/SSE: endpoint URL
    headers: dict[str, str] = Field(default_factory=dict)  # HTTP/SSE: custom headers
    use_proxy: bool = False
    tool_timeout: int = 30  # seconds before a tool call is cancelled
    enabled_tools: list[str] = Field(
        default_factory=lambda: ["*"]
    )  # Only register these tools; accepts raw MCP names or wrapped mcp_<server>_<tool> names; ["*"] = all capabilities (tools, resources, prompts); any restriction = only listed tools, no resources/prompts


class ToolsConfig(Base):
    """Root settings assembled from tool-owned configuration models."""

    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    file: FileToolsConfig = Field(default_factory=FileToolsConfig)
    cli_apps: CliAppsToolConfig = Field(default_factory=CliAppsToolConfig)
    my: MyToolConfig = Field(default_factory=MyToolConfig)
    max_outgoing_session_messages_per_minute: int = Field(default=6, ge=1)
    restrict_to_workspace: bool = (
        False  # policy intent: keep tool access inside workspace when possible
    )
    webui_allow_local_service_access: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "webuiAllowLocalServiceAccess",
            "webui_allow_local_service_access",
        ),
    )  # allow WebUI Full Access shell checks against localhost services
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)
    ssrf_whitelist: list[str] = Field(
        default_factory=list
    )  # CIDR ranges to exempt from SSRF blocking
