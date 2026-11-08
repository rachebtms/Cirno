"""Provider and model metadata, independent of transport clients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cirno_core.providers.model_api import (
    ModelAPICapabilities,
    ProviderAPI,
    ResponsesCapabilities,
)
from pydantic.alias_generators import to_snake


@dataclass(frozen=True)
class ProviderModelSpec:
    """Curated model metadata used for fixed catalogs or online fallback."""

    id: str
    label: str = ""
    description: str = ""
    owned_by: str = ""
    context_window: int | None = None
    reasoning_efforts: tuple[str, ...] = ()
    supports_backend_search: bool = False
    api: ModelAPICapabilities | None = None
    aliases: tuple[str, ...] = ()
    max_output_tokens: int | None = None
    input_modalities: tuple[str, ...] = ()
    output_modalities: tuple[str, ...] = ()
    default_reasoning_effort: str | None = None


@dataclass(frozen=True)
class ProviderSpec:
    """One provider's routing and request-policy metadata.

    Placeholders in env_extras values:
      {api_key}  — the user's API key
      {api_base} — api_base from config, or this spec's default_api_base
    """

    # identity
    name: str  # config field name, e.g. "dashscope"
    keywords: tuple[str, ...]  # model-name keywords for matching (lowercase)
    env_key: str  # env var for API key, e.g. "DASHSCOPE_API_KEY"
    # Request formats available through this provider's adapters. Remote model
    # support is separate: an adapter does not guarantee endpoint support.
    request_apis: tuple[ProviderAPI, ...]
    display_name: str = ""  # shown in settings
    model_catalog: str = "auto"  # WebUI model-list source, including builtin/hybrid
    builtin_models: tuple[ProviderModelSpec, ...] = ()

    # which provider implementation to use
    # "openai_compat" | "anthropic" | "azure_openai" | "openai_codex" | "xai_grok"
    # | "github_copilot" | "bedrock"
    backend: str = "openai_compat"

    # extra env vars / request headers supplied by the provider integration.
    env_extras: tuple[tuple[str, str], ...] = ()
    default_extra_headers: tuple[tuple[str, str], ...] = ()

    # gateway / local detection
    is_gateway: bool = False  # routes any model (OpenRouter, AiHubMix)
    is_local: bool = False  # local deployment (vLLM, Ollama)
    detect_by_key_prefix: str = ""  # match api_key prefix, e.g. "sk-or-"
    detect_by_base_keyword: str = ""  # match substring in api_base URL
    default_api_base: str = ""  # OpenAI-compatible base URL for this provider

    # gateway behavior
    strip_model_prefix: bool = False  # strip "provider/" before sending to gateway
    strip_model_prefixes: tuple[str, ...] = ()  # strip only when the first model segment matches
    supports_max_completion_tokens: bool = False

    # per-model param overrides, e.g. (("kimi-k2.5", {"temperature": 1.0}),)
    model_overrides: tuple[tuple[str, dict[str, Any]], ...] = ()

    # OAuth-based providers (e.g., OpenAI Codex) don't use API keys
    is_oauth: bool = False

    # Direct providers skip API-key validation (user supplies everything)
    is_direct: bool = False

    # Provider supports cache_control on content blocks (e.g. Anthropic prompt caching)
    supports_prompt_caching: bool = False

    # How to inject the thinking on/off toggle into extra_body.
    # ""              — no extra_body needed (default)
    # "thinking_type" — {"thinking": {"type": "enabled"/"disabled"}}
    #                   (DeepSeek, VolcEngine, BytePlus)
    # "enable_thinking" — {"enable_thinking": true/false}  (DashScope)
    # "reasoning_split" — {"reasoning_split": true/false}  (MiniMax)
    thinking_style: str = ""

    # Server-native reasoning control to pair with model-level thinking styles.
    # "reasoning_effort" — {"reasoning": {"effort": <none|minimal|...>}}
    #                      (OpenRouter)
    gateway_reasoning_style: str = ""

    # When True, treat the "reasoning" response field as formal content
    # when "content" is empty.  Only set this for providers (e.g. StepFun)
    # whose API returns the actual answer in "reasoning" instead of "content".
    reasoning_as_content: bool = False

    # Map user-supplied reasoning_effort (OpenAI vocab: minimal/low/medium/high)
    # to the value this provider accepts on the wire. Set when the provider's
    # accepted set differs from OpenAI's. An empty mapped value omits the kwarg.
    # Mistral: only "high"/"none" — low/minimal map to "none", medium maps to "high".
    reasoning_effort_remap: tuple[tuple[str, str], ...] = ()

    # Models whose API rejects the reasoning_effort kwarg because reasoning is
    # implicit (Magistral always reasons; sending the kwarg returns HTTP 400).
    # Substring match against the wire model name (lowercased).
    implicit_reasoning_models: tuple[str, ...] = ()

    # Capabilities for providers/models served through the shared Responses path.
    responses: ResponsesCapabilities | None = None

    # When the model returns content as a list of {"type":"thinking",...} +
    # {"type":"text",...} blocks, extract the thinking text into
    # reasoning_content. Mistral's Magistral / reasoning-enabled responses use
    # this shape.
    extract_thinking_blocks: bool = False

    # Strip ``reasoning_content`` from assistant history messages before
    # sending. Mistral validates its request schema strictly and 400s on
    # any extra fields; other providers (DeepSeek) require this key on the
    # wire to keep thinking-mode history intact.
    strip_history_reasoning_content: bool = False

    @property
    def label(self) -> str:
        return self.display_name or self.name.title()

    def request_model_name(self, model: str) -> str:
        """Remove only the provider prefixes owned by this adapter."""
        if "/" not in model:
            return model
        if self.strip_model_prefix:
            return model.rsplit("/", 1)[-1]
        prefix, routed_model = model.split("/", 1)
        prefix_key = to_snake(prefix.replace("-", "_")).lower()
        if any(
            to_snake(value.replace("-", "_")).lower() == prefix_key
            for value in self.strip_model_prefixes
        ):
            return routed_model
        return model

    def model_metadata(self, model: str) -> ProviderModelSpec | None:
        """Look up curated metadata without rewriting configured or wire model IDs."""
        model_id = model.rsplit("/", 1)[-1].lower()
        return next(
            (
                entry
                for entry in self.builtin_models
                if model_id == entry.id or model_id in entry.aliases
            ),
            None,
        )

    def default_model_api(
        self,
        model: str,
        reasoning_effort: str | None = None,
        *,
        api_base: str | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> ModelAPICapabilities:
        """Resolve automatic API defaults without constructing or probing a client."""
        if self.responses is None:
            return ModelAPICapabilities()
        return self.responses.default_model_api(
            self.request_model_name(model),
            reasoning_effort,
            api_base=api_base,
            default_api_base=self.default_api_base,
            extra_body=extra_body,
        )

    @property
    def provider_api_configurable(self) -> bool:
        return self.name == "openai" or (
            self.is_direct
            and self.backend == "openai_compat"
            and "anthropic_messages" in self.request_apis
        )

    def validate_model_api(self, api: ModelAPICapabilities) -> None:
        unsupported = set(api.supported_apis).difference(self.request_apis)
        if unsupported:
            raise ValueError(
                f"Provider '{self.label}' does not support {', '.join(sorted(unsupported))}. "
                f"Available request APIs: {', '.join(self.request_apis)}."
            )
