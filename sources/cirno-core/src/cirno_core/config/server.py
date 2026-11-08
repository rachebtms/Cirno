"""Server configuration models."""

from __future__ import annotations

from typing import Literal

from cirno_core.config.base import Base
from pydantic import Field


class UploadConfig(Base):
    """Browser attachment upload limits, measured in MiB; local references are excluded."""

    max_file_mb: int = Field(default=6, ge=1)
    max_video_mb: int = Field(default=20, ge=1)
    max_total_mb: int = Field(default=24, ge=1)


class ServerConfig(Base):
    """Service listeners, lifecycle and browser upload policy."""

    uploads: UploadConfig = Field(default_factory=UploadConfig)
    health_host: str = "127.0.0.1"  # Safer default: local-only bind.
    health_port: int = 18790
    restart_mode: Literal["auto", "exec", "spawn", "exit"] = "auto"
