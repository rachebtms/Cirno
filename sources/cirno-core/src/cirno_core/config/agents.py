"""Agents configuration models."""

from __future__ import annotations

from typing import Literal, cast

from cirno_memory.config import MemoryConfig
from cirno_core.config.base import Base
from cirno_core.config.home import get_default_workspace
from cirno_core.config.models import ConsolidationConfig, FallbackCandidate, ModelAPIConfig
from cirno_core.config.prompts import SystemPrompts
from cirno_core.config.timezone import detect_system_timezone
from cirno_core.cron.types import CronSchedule
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic.alias_generators import to_snake


class DreamConfig(Base):
    """Dream memory consolidation configuration."""

    _HOUR_MS = 3_600_000

    enabled: bool = True  # Register the periodic Dream consolidation job on startup
    mode: Literal["idle", "interval"] = "idle"
    idle_after_seconds: int = Field(default=180, ge=10, le=86400)
    max_tool_iterations: int = Field(default=24, ge=1, le=128)
    batch_entries: int = Field(default=8, ge=1, le=50)
    batch_chars: int = Field(default=16000, ge=2000, le=64000)
    interval_h: int = Field(default=2, ge=1)  # Every 2 hours by default
    model_override: str | None = Field(
        default=None,
        validation_alias=AliasChoices("modelOverride", "model_override"),
    )  # Model preset ID for Dream sessions

    def build_schedule(self, timezone: str) -> CronSchedule:
        """Build the interval schedule used outside idle mode."""
        return CronSchedule(kind="every", every_ms=self.interval_h * self._HOUR_MS)

    def describe_schedule(self) -> str:
        """Return a human-readable summary for logs and startup output."""
        if self.mode == "idle":
            return f"when idle for {self.idle_after_seconds}s with pending memory"
        hours = self.interval_h
        return f"every {hours}h"




class HeartbeatConfig(Base):
    """Heartbeat service configuration (now backed by cron)."""

    enabled: bool = True
    interval_s: int = 30 * 60  # 30 minutes


class ResumeConfig(Base):
    """Explicit continuation after Stop or an interrupted request."""

    message: str = Field(
        default="Continue the interrupted request from the saved conversation context. Check completed work before acting; do not repeat completed operations.",
        min_length=1,
        max_length=4000,
    )
    show_message: bool = False

    @field_validator("message")
    @classmethod
    def nonblank_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Continuation message must not be blank")
        return value


class ApprovalConfig(Base):
    """Independent operation review; uncertain or disabled reviews go to the owner."""

    enabled: bool = True
    model_override: str | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)


class AgentDefaults(Base):
    """Default agent configuration."""

    workspace: str = Field(default_factory=get_default_workspace)
    system_prompts: SystemPrompts = Field(default_factory=SystemPrompts)
    model_preset: str | None = None  # Active preset ID — takes precedence over fields below
    model: str = ""
    provider: str = (
        "auto"  # Provider ID (e.g. "anthropic", "openrouter") or "auto" for auto-detection
    )
    max_tokens: int = 8192
    context_window_tokens: int = 200_000
    temperature: float = 0.1
    fallback_models: list[FallbackCandidate] = Field(default_factory=list)
    goal_continuation_limit: int = Field(default=0, ge=0)
    resume: ResumeConfig = Field(default_factory=ResumeConfig)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)
    max_tool_iterations: int = 200
    max_concurrent_subagents: int = Field(default=4, ge=1)
    max_tool_result_chars: int = 16_000
    provider_retry_mode: Literal["standard", "persistent"] = "standard"
    tool_status_summary_max_chars: int = Field(
        default=40,
        ge=20,
        le=500,
        validation_alias=AliasChoices("toolStatusSummaryMaxChars"),
        serialization_alias="toolStatusSummaryMaxChars",
    )  # Max characters for channel tool status summaries (e.g. "$ cd …/project && npm test")
    reasoning_effort: str | None = (
        None  # low / medium / high / xhigh / max / adaptive / none — LLM thinking effort; None preserves the provider default
    )
    reasoning_history: Literal["auto", "preserve", "omit"] = "auto"
    api: ModelAPIConfig | None = None
    timezone: str = "UTC"  # Effective IANA timezone, e.g. "Asia/Shanghai"
    timezone_mode: Literal["auto", "manual"] = "auto"
    disabled_skills: list[str] = Field(
        default_factory=list
    )  # Skill names to exclude from loading (e.g. ["summarize", "skill-creator"])
    idle_compact_after_minutes: int = Field(
        default=15,
        ge=0,
        validation_alias="idleCompactAfterMinutes",
        serialization_alias="idleCompactAfterMinutes",
    )  # Auto-compact idle threshold in minutes (0 = disabled)
    idle_compact_check_interval_seconds: int = Field(
        default=60,
        ge=0,
    )  # Minimum interval in seconds between scans for idle sessions
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    consolidation: ConsolidationConfig = Field(
        default_factory=ConsolidationConfig,
        validation_alias=AliasChoices("consolidation", "compaction"),
    )
    # Legacy batch/history compatibility; never scheduled or serialized.
    dream: DreamConfig = Field(default_factory=DreamConfig, exclude=True)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    idle_compact_percent: float = Field(default=20, ge=0, le=100)
    active_compact_percent: int = Field(default=100, ge=1, le=100)
    idle_compact_keep_percent: float = Field(default=5, ge=0, le=100)
    idle_compact_min_tokens: int = Field(default=32_000, ge=0)
    idle_compact_keep_recent_tokens: int = Field(default=8_000, ge=0)

    @property
    def compaction(self) -> ConsolidationConfig:
        """Compatibility for internal checkpoint-budget consumers."""
        return self.consolidation

    @model_validator(mode="before")
    @classmethod
    def migrate_consolidation(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        merged = {to_snake(key): item for key, item in dict(data.pop("compaction", {})).items()}
        merged.update({to_snake(key): item for key, item in dict(data.get("consolidation", {})).items()})
        legacy = data.get("dream", {})
        if isinstance(legacy, dict) and "enabled" in legacy:
            merged.setdefault("learn", legacy["enabled"])
        data["consolidation"] = merged
        return data

    @model_validator(mode="before")
    @classmethod
    def resolve_timezone(cls, value: object) -> object:
        """Detect new defaults server-side while preserving configured timezones."""
        if not isinstance(value, dict):
            return value

        data = dict(cast(dict[str, object], value))
        timezone_mode = data.get("timezoneMode", data.get("timezone_mode"))
        if timezone_mode is None:
            timezone_mode = "manual" if "timezone" in data else "auto"
            data["timezoneMode"] = timezone_mode
        if timezone_mode == "auto":
            data["timezone"] = detect_system_timezone()
        return data

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError(f"unknown timezone {value!r}") from None
        return value


class AgentsConfig(Base):
    """Agent configuration."""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)
