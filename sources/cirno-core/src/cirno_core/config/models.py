"""Models configuration models."""

from __future__ import annotations

from typing import Any, Literal

from cirno_core.config.base import Base
from cirno_core.providers.generation import GenerationSettings
from cirno_core.providers.model_api import ModelAPICapabilities, RequestAPI
from pydantic import Field, model_validator


class ProviderAPIConfig(Base):
    """Connection API defaults and custom endpoints' accepted request APIs."""

    supported_apis: tuple[RequestAPI, ...] = Field(min_length=1)
    preferred_api: RequestAPI | None = None

    @model_validator(mode="after")
    def _validate_preference(self) -> "ProviderAPIConfig":
        if self.preferred_api is not None and self.preferred_api not in self.supported_apis:
            raise ValueError("preferred_api must be one of supported_apis")
        return self

    def to_capabilities(self) -> ModelAPICapabilities:
        return ModelAPICapabilities(
            supported_apis=self.supported_apis,
            preferred_api=self.preferred_api or self.supported_apis[0],
        )


class ModelAPIConfig(ProviderAPIConfig):
    """Allowed request APIs and preference for a model preset's endpoint."""

    @model_validator(mode="after")
    def _validate_api_family(self) -> "ModelAPIConfig":
        if "anthropic_messages" in self.supported_apis and set(self.supported_apis) != {
            "anthropic_messages",
        }:
            raise ValueError("anthropic_messages cannot be combined with OpenAI request APIs")
        return self


class CompactionConfig(Base):
    """Small, independent checkpoint-generation budget."""

    max_tokens: int = Field(default=8192, ge=512, le=32768)
    max_retries: int = Field(default=1, ge=0, le=10, strict=True)
    reasoning_effort: Literal["inherit", "low", "none"] = "low"
    checkpoint_reminder_percent: int = Field(default=85, ge=1, le=100)
    output_reserve_percent: int = Field(default=5, ge=1, le=50)


class ConsolidationConfig(CompactionConfig):
    """One request produces a task checkpoint and source-backed learning."""

    learn: bool = True
    max_updates: int = Field(default=8, ge=1, le=32)
    context_chars: int = Field(default=16000, ge=2000, le=64000)


class RequestOverrides(Base):
    """Optional request differences; omitted fields inherit connection defaults."""

    extra_headers: dict[str, str] | None = Field(default=None, repr=False)
    extra_query: dict[str, str] | None = Field(default=None, repr=False)
    extra_body: dict[str, Any] | None = Field(default=None, repr=False)


class InlineFallbackConfig(RequestOverrides):
    """One inline fallback model configuration."""

    model: str
    provider: str
    max_tokens: int | None = None
    context_window_tokens: int | None = None
    temperature: float | None = None
    reasoning_effort: str | None = None
    reasoning_history: Literal["auto", "preserve", "omit"] = "auto"
    api: ModelAPIConfig | None = None


FallbackCandidate = str | InlineFallbackConfig


class ModelPresetConfig(RequestOverrides):
    """A model configuration referenced by its immutable dictionary key."""

    display_name: str | None = None
    image_input: bool | None = None
    video_input: bool | None = None

    model: str
    provider: str = "auto"
    max_tokens: int = 8192
    context_window_tokens: int = 200_000
    temperature: float = 0.1
    reasoning_effort: str | None = None
    reasoning_history: Literal["auto", "preserve", "omit"] = "auto"
    api: ModelAPIConfig | None = None

    idle_compact_percent: float | None = Field(default=None, ge=0, le=100)
    idle_compact_keep_percent: float | None = Field(default=None, ge=0, le=100)

    def to_generation_settings(self) -> GenerationSettings:
        return GenerationSettings(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort=self.reasoning_effort,
        )
