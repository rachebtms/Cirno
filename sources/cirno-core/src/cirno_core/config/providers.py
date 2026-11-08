"""Providers configuration models."""

from __future__ import annotations

from typing import Any, ClassVar

from cirno_core.config.balance import ProviderBalanceConfig
from cirno_core.config.base import Base
from cirno_core.config.models import ProviderAPIConfig
from pydantic import ConfigDict, Field, field_validator, model_validator


class ProviderConfig(Base):
    """LLM provider configuration."""

    balance: ProviderBalanceConfig | None = None

    # User-facing name for dynamic custom providers.
    display_name: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    api_key: str | None = Field(default=None, repr=False)
    api_base: str | None = None
    api: ProviderAPIConfig | None = Field(default=None, exclude_if=lambda value: value is None)
    extra_headers: dict[str, str] | None = None  # Custom headers (e.g. APP-Code for AiHubMix)
    extra_body: dict[str, Any] | None = (
        None  # Extra provider request fields; shape depends on provider/API surface
    )
    extra_query: dict[str, str] | None = (
        None  # Extra query params (e.g. api-version for Azure-style gateways)
    )
    use_proxy: bool = False
    thinking_style: str | None = None  # Thinking/reasoning style for custom providers

    # Valid values mirror the keys of _THINKING_STYLE_MAP in
    # cirno/providers/openai_compat_provider.py. Kept duplicated here to
    # avoid an import cycle (schema.py must not import from providers/).
    _VALID_THINKING_STYLES: ClassVar[tuple[str, ...]] = (
        "thinking_type",
        "enable_thinking",
        "reasoning_split",
    )

    @field_validator("thinking_style")
    @classmethod
    def _validate_thinking_style(cls, v: str | None) -> str | None:
        if not v:  # None or "" means no provider-specific injection
            return v
        if v not in cls._VALID_THINKING_STYLES:
            raise ValueError(
                f"Invalid thinking_style {v!r}. "
                f"Must be one of: {', '.join(repr(s) for s in cls._VALID_THINKING_STYLES)} "
                f"(or empty/omitted)."
            )
        return v


class BedrockProviderConfig(ProviderConfig):
    """AWS Bedrock Runtime provider configuration."""

    region: str | None = None  # AWS region, falls back to AWS_REGION/AWS_DEFAULT_REGION/profile
    profile: str | None = None  # Optional AWS shared config profile


class ProvidersConfig(Base):
    """Configuration for LLM providers.

    Supports custom providers via extra fields — any additional field
    becomes an OpenAI-compatible custom provider.
    """

    model_config = ConfigDict(extra="allow")

    custom: ProviderConfig = Field(default_factory=ProviderConfig)  # Any OpenAI-compatible endpoint
    azure_openai: ProviderConfig = Field(
        default_factory=ProviderConfig
    )  # Azure OpenAI (model = deployment name)
    bedrock: BedrockProviderConfig = Field(
        default_factory=BedrockProviderConfig
    )  # AWS Bedrock Converse
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)
    orcarouter: ProviderConfig = Field(default_factory=ProviderConfig)  # OrcaRouter API gateway
    huggingface: ProviderConfig = Field(default_factory=ProviderConfig)
    skywork: ProviderConfig = Field(default_factory=ProviderConfig)  # Skywork / APIFree API gateway
    deepseek: ProviderConfig = Field(default_factory=ProviderConfig)
    groq: ProviderConfig = Field(default_factory=ProviderConfig)
    zhipu: ProviderConfig = Field(default_factory=ProviderConfig)
    dashscope: ProviderConfig = Field(default_factory=ProviderConfig)
    modelscope: ProviderConfig = Field(default_factory=ProviderConfig)
    vllm: ProviderConfig = Field(default_factory=ProviderConfig)
    ollama: ProviderConfig = Field(default_factory=ProviderConfig)  # Ollama local models
    lm_studio: ProviderConfig = Field(default_factory=ProviderConfig)  # LM Studio local models
    atomic_chat: ProviderConfig = Field(default_factory=ProviderConfig)  # Atomic Chat local models
    ovms: ProviderConfig = Field(default_factory=ProviderConfig)  # OpenVINO Model Server (OVMS)
    gemini: ProviderConfig = Field(default_factory=ProviderConfig)
    moonshot: ProviderConfig = Field(default_factory=ProviderConfig)
    kimi_coding: ProviderConfig = Field(
        default_factory=ProviderConfig
    )  # Kimi Coding Plan (Anthropic Messages API)
    minimax: ProviderConfig = Field(default_factory=ProviderConfig)
    minimax_anthropic: ProviderConfig = Field(
        default_factory=ProviderConfig
    )  # MiniMax Anthropic endpoint (thinking)
    mistral: ProviderConfig = Field(default_factory=ProviderConfig)
    stepfun: ProviderConfig = Field(
        default_factory=ProviderConfig
    )  # Step Fun (阶跃星辰) — LLM + ASR (set apiBase to Plan URL for ASR)
    xiaomi_mimo: ProviderConfig = Field(default_factory=ProviderConfig)  # Xiaomi MIMO (小米)
    longcat: ProviderConfig = Field(default_factory=ProviderConfig)  # LongCat
    ant_ling: ProviderConfig = Field(default_factory=ProviderConfig)  # Ant Ling
    aihubmix: ProviderConfig = Field(default_factory=ProviderConfig)  # AiHubMix API gateway
    siliconflow: ProviderConfig = Field(default_factory=ProviderConfig)  # SiliconFlow (硅基流动)
    edenai: ProviderConfig = Field(default_factory=ProviderConfig)  # Eden AI API gateway
    novita: ProviderConfig = Field(default_factory=ProviderConfig)  # Novita AI
    volcengine: ProviderConfig = Field(default_factory=ProviderConfig)  # VolcEngine (火山引擎)
    volcengine_coding_plan: ProviderConfig = Field(
        default_factory=ProviderConfig
    )  # VolcEngine Coding Plan
    byteplus: ProviderConfig = Field(
        default_factory=ProviderConfig
    )  # BytePlus (VolcEngine international)
    byteplus_coding_plan: ProviderConfig = Field(
        default_factory=ProviderConfig
    )  # BytePlus Coding Plan
    openai_codex: ProviderConfig = Field(
        default_factory=ProviderConfig, exclude=True
    )  # OpenAI Codex (OAuth)
    xai_grok: ProviderConfig = Field(
        default_factory=ProviderConfig, exclude=True
    )  # xAI Grok (OAuth)
    github_copilot: ProviderConfig = Field(
        default_factory=ProviderConfig, exclude=True
    )  # Github Copilot (OAuth)
    qianfan: ProviderConfig = Field(default_factory=ProviderConfig)  # Qianfan (百度千帆)
    nvidia: ProviderConfig = Field(default_factory=ProviderConfig)  # NVIDIA NIM (nvapi- keys)
    opencode: ProviderConfig = Field(
        default_factory=ProviderConfig
    )  # OpenCode Zen (canonical provider id)
    opencode_go: ProviderConfig = Field(
        default_factory=ProviderConfig
    )  # OpenCode Go (low-cost coding models)

    @model_validator(mode="after")
    def convert_extra_providers(self):
        """Convert extra fields (custom providers) to ProviderConfig objects."""
        if self.model_extra:
            from cirno_core.providers.registry import find_by_name

            for key, value in self.model_extra.items():
                if spec := find_by_name(key):
                    raise ValueError(
                        f"providers.{key} conflicts with built-in provider {spec.name!r}; "
                        "use the built-in provider key or choose a different custom provider name"
                    )
                if isinstance(value, dict):
                    self.model_extra[key] = ProviderConfig.model_validate(value)
        return self
