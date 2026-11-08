"""CLI App failures and execution settings."""

from __future__ import annotations

from dataclasses import dataclass


class CliAppError(ValueError):
    """User-facing CLI Apps failure."""

    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass(slots=True)
class CliAppsRuntimeConfig:
    """Runtime knobs for CLI Apps."""

    install_timeout: int = 300
    run_timeout: int = 60
    catalog_ttl_seconds: int = 3600
