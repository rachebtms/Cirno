"""Execution configuration shared by shell/session tools and the root schema."""

from typing import Literal

from pydantic import AliasChoices, Field

from cirno.config.base import Base


class ExecToolConfig(Base):
    """Shell exec tool configuration."""
    enable: bool = True
    max_runtime: int = Field(
        default=3600, ge=0,
        validation_alias=AliasChoices("maxRuntime", "max_runtime"),
    )
    max_runtime_limit: int = Field(default=86400, gt=0)
    idle_timeout: int = Field(default=300, ge=0)
    idle_action: Literal["report", "terminate"] = "report"
    path_prepend: str = ""
    path_append: str = ""
    sandbox: str = ""
    sandbox_ro_binds: list[str] = Field(default_factory=list)
    sandbox_rw_binds: list[str] = Field(default_factory=list)
    allowed_env_keys: list[str] = Field(default_factory=list)
    allow_patterns: list[str] = Field(default_factory=list)
    deny_patterns: list[str] = Field(default_factory=list)
