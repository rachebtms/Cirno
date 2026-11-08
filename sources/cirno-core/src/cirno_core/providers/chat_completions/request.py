"""Build Chat Completions requests from explicit provider and model policy."""

from typing import Any, Protocol

from cirno_core.providers.messages import sanitize_empty_content
from cirno_core.providers.catalog.models import KIMI_K3_MODELS
from cirno_core.providers.catalog.contracts import ProviderSpec
from cirno_core.providers.request_bodies import merge_chat_extra_body

from .cache import apply_cache_control
from .generation import (
    _KIMI_ALWAYS_THINKING_MODELS,
    _KIMI_SERVER_MANAGED_TEMPERATURE_MODELS,
    _KIMI_THINKING_MODELS,
    gateway_reasoning_extra_body,
    model_slug,
    model_thinking_style,
    requires_max_completion_tokens,
    supports_temperature,
    thinking_extra_body,
    thinking_styles_for,
)


class MessagePreparer(Protocol):
    def __call__(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]: ...


def build_chat_request(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    model: str | None,
    max_tokens: int,
    temperature: float,
    reasoning_effort: str | None,
    tool_choice: str | dict[str, Any] | None,
    extra_headers: dict[str, str] | None = None,
    *,
    default_model: str,
    spec: ProviderSpec | None,
    extra_body: dict[str, Any],
    prepare_messages: MessagePreparer,
) -> dict[str, Any]:
    model_name = model or default_model

    if spec and spec.supports_prompt_caching:
        model_name = model or default_model
        if any(model_name.lower().startswith(k) for k in ("anthropic/", "claude")):
            messages, tools = apply_cache_control(messages, tools)

    model_name = spec.request_model_name(model_name) if spec else model_name

    kwargs: dict[str, Any] = {
        "model": model_name,
        "messages": prepare_messages(
            sanitize_empty_content(messages),
            model_name,
            tools=tools,
        ),
    }

    if supports_temperature(model_name, reasoning_effort):
        kwargs["temperature"] = temperature

    if (spec and spec.supports_max_completion_tokens) or requires_max_completion_tokens(model_name):
        kwargs["max_completion_tokens"] = max(1, max_tokens)
    else:
        kwargs["max_tokens"] = max(1, max_tokens)

    if spec:
        model_lower = model_name.lower()
        for pattern, overrides in spec.model_overrides:
            if pattern in model_lower:
                kwargs.update(overrides)
                break

    # Moonshot selects the only valid temperature from the K2.5/K2.6 thinking mode:
    # 1.0 when enabled and 0.6 when disabled. Omitting the parameter lets the API
    # apply the matching value for both its default and explicit thinking controls.
    if (
        spec
        and spec.name == "moonshot"
        and model_slug(model_name) in _KIMI_SERVER_MANAGED_TEMPERATURE_MODELS
    ):
        kwargs.pop("temperature", None)

    # Normalize reasoning_effort into a semantic form (OpenAI vocab)
    # used for internal decisions, and a wire form actually sent out.
    # "minimum" is accepted as a DashScope-native alias for "minimal".
    semantic_effort: str | None = None
    if isinstance(reasoning_effort, str):
        semantic_effort = reasoning_effort.lower()
        if semantic_effort == "minimum":
            semantic_effort = "minimal"

    wire_effort = reasoning_effort
    slug = model_slug(model_name)
    if slug in KIMI_K3_MODELS and semantic_effort is not None:
        # K3 always reasons and accepts top-level low/high/max effort.
        # Keep disabled presets on the default and normalize other legacy
        # enabled values to "max".
        if semantic_effort in ("none", "minimal"):
            wire_effort = None
        else:
            if semantic_effort not in ("low", "high", "max"):
                semantic_effort = "max"
            wire_effort = semantic_effort
    if spec and spec.name == "dashscope" and semantic_effort == "minimal":
        # DashScope accepts none/minimum/low/medium/high/xhigh; "minimal" 400s.
        wire_effort = "minimum"
    elif spec and spec.name == "deepseek" and semantic_effort == "minimal":
        # DeepSeek's minimal alias enables low-effort thinking.
        semantic_effort = wire_effort = "low"

    # Magistral and other providers where reasoning is implicit reject the
    # reasoning_effort kwarg entirely. Strip it before the remap so we don't
    # accidentally send "none"/"high" to a model that always reasons.
    strip_effort = False
    if spec and spec.implicit_reasoning_models:
        model_lower = model_name.lower()
        strip_effort = any(pat in model_lower for pat in spec.implicit_reasoning_models)

    # Some providers accept a constrained reasoning_effort vocabulary
    # (Mistral: only "high"/"none"). Remap from OpenAI vocab to the
    # provider's accepted set; an empty mapped value means "omit".
    if (
        not strip_effort
        and spec
        and spec.reasoning_effort_remap
        and isinstance(semantic_effort, str)
    ):
        remap = dict(spec.reasoning_effort_remap)
        mapped = remap.get(semantic_effort)
        if mapped is not None:
            wire_effort = mapped or None
            semantic_effort = mapped or "none"

    if strip_effort:
        wire_effort = None
    elif wire_effort and semantic_effort != "none":
        kwargs["reasoning_effort"] = wire_effort

    # Only send thinking controls when reasoning_effort is explicit so
    # omitting the config preserves each provider's default.
    if reasoning_effort is not None:
        thinking_enabled = semantic_effort not in ("none", "minimal")
        for thinking_style in thinking_styles_for(spec, model_name):
            if not thinking_enabled and slug in _KIMI_ALWAYS_THINKING_MODELS:
                continue
            extra = thinking_extra_body(thinking_style, thinking_enabled)
            if extra:
                kwargs.setdefault("extra_body", {}).update(extra)
        gateway_style = spec.gateway_reasoning_style if spec else ""
        if (
            gateway_style
            and model_thinking_style(model_name)
            and (thinking_enabled or slug not in _KIMI_ALWAYS_THINKING_MODELS)
        ):
            extra = gateway_reasoning_extra_body(gateway_style, semantic_effort)
            if extra:
                kwargs.setdefault("extra_body", {}).update(extra)

        # Moonshot rejects requests that carry both 'reasoning_effort'
        # and the native 'thinking' param.  We already expressed the
        # user's intent via the provider-native shape, so drop the
        # redundant wire-level kwarg.  Only kimi models need this —
        # Xiaomi's API accepts both params.
        if slug in _KIMI_THINKING_MODELS:
            kwargs.pop("reasoning_effort", None)

    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice or "auto"

    # Backfill reasoning_content="" on assistants missing it: DeepSeek
    # thinking mode rejects history otherwise (#3554, #3584); "" reads
    # as "no thinking that turn". DeepSeek Flash/V4/reasoner reason natively,
    # so backfill even without explicit reasoning_effort.
    explicit_thinking = (
        reasoning_effort is not None
        and semantic_effort not in ("none", "minimal")
        and ((spec and spec.thinking_style) or model_thinking_style(model_name))
    )
    implicit_deepseek_thinking = (
        spec is not None
        and spec.name == "deepseek"
        and semantic_effort not in ("none", "minimal", "minimum")
        and (
            slug == "deepseek-flash"
            or any(t in model_name.lower() for t in ("deepseek-v4", "deepseek-reasoner"))
        )
    )
    if explicit_thinking or implicit_deepseek_thinking:
        for msg in kwargs["messages"]:
            if msg.get("role") == "assistant" and "reasoning_content" not in msg:
                msg["reasoning_content"] = ""

    # Merge user-configured extra_body last so ordinary fields can override
    # provider defaults. Keep configured tools at the top level: the SDK
    # otherwise lets extra_body.tools replace cirno's generated functions.
    if extra_body:
        kwargs = merge_chat_extra_body(kwargs, extra_body)
    if extra_headers:
        kwargs["extra_headers"] = extra_headers

    return kwargs
