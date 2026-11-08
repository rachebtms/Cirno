"""Provider and model reasoning controls on the Chat Completions wire."""

from typing import Any, Callable

from cirno_core.providers.catalog.models import KIMI_K3_MODELS
from cirno_core.providers.catalog.contracts import ProviderSpec

_KIMI_THINKING_MODELS: frozenset[str] = frozenset(
    {
        "kimi-k2.5",
        "kimi-k2.6",
        "kimi-k2.7",
        "kimi-k2.7-code",
        "kimi-k2.7-code-highspeed",
        "k2.6-code-preview",
    }
)


_KIMI_ALWAYS_THINKING_MODELS: frozenset[str] = frozenset(
    {
        "kimi-k2.7-code",
        "kimi-k2.7-code-highspeed",
    }
)


_KIMI_SERVER_MANAGED_TEMPERATURE_MODELS: frozenset[str] = frozenset(
    {
        "kimi-k2.5",
        "kimi-k2.6",
    }
)


_MIMO_THINKING_MODELS: frozenset[str] = frozenset(
    {
        "mimo-v2.5-pro",
        "mimo-v2.5",
        "mimo-v2-pro",
        "mimo-v2-omni",
    }
)


_THINKING_STYLE_MAP: dict[
    str,
    Callable[[bool], dict[str, Any]],
] = {
    "thinking_type": lambda on: {"thinking": {"type": "enabled" if on else "disabled"}},
    "enable_thinking": lambda on: {"enable_thinking": on},
    "reasoning_split": lambda on: {"reasoning_split": on},
}


_GATEWAY_REASONING_STYLE_MAP: dict[
    str,
    Callable[[str], dict[str, Any]],
] = {
    "reasoning_effort": lambda effort: {"reasoning": {"effort": effort}},
}


_QWEN_THINKING_MODELS: frozenset[str] = frozenset(
    {
        "qwen3.7-max",
        "qwen3.7-plus",
        "qwen3.6-max-preview",
        "qwen3.6-plus",
        "qwen3.6-flash",
        "qwen3.5-plus",
        "qwen3.5-flash",
    }
)


_MODEL_THINKING_STYLES: dict[str, str] = {
    **dict.fromkeys(_KIMI_THINKING_MODELS, "thinking_type"),
    **dict.fromkeys(_MIMO_THINKING_MODELS, "thinking_type"),
    **dict.fromkeys(_QWEN_THINKING_MODELS, "enable_thinking"),
}


def model_slug(model_name: str) -> str:
    return model_name.lower().rsplit("/", 1)[-1]


def requires_max_completion_tokens(model_name: str) -> bool:
    """Return True for models that require ``max_completion_tokens``."""
    slug = model_slug(model_name)
    return (
        slug in KIMI_K3_MODELS
        or "gpt-5" in slug
        or any(slug == p or slug.startswith((p + "-", p + ".")) for p in ("o1", "o3", "o4"))
    )


def model_thinking_style(model_name: str) -> str:
    return _MODEL_THINKING_STYLES.get(model_slug(model_name), "")


def thinking_styles_for(spec: ProviderSpec | None, model_name: str) -> list[str]:
    styles: list[str] = []
    if spec and spec.thinking_style:
        styles.append(spec.thinking_style)
    elif (
        spec
        and spec.name == "zhipu"
        and model_slug(model_name)
        in {
            "glm-4.6",
            "glm-4.7",
            "glm-5",
            "glm-5.1",
            "glm-5.2",
        }
    ):
        # Keep this model-specific: GLM-5.3 requires thinking and cannot disable it.
        styles.append("thinking_type")
    model_style = model_thinking_style(model_name)
    if model_style and model_style not in styles:
        styles.append(model_style)
    return styles


def thinking_extra_body(style: str, thinking_enabled: bool) -> dict[str, Any] | None:
    builder = _THINKING_STYLE_MAP.get(style)
    return builder(thinking_enabled) if builder else None


def gateway_reasoning_extra_body(style: str, effort: str | None) -> dict[str, Any] | None:
    if not effort:
        return None
    builder = _GATEWAY_REASONING_STYLE_MAP.get(style)
    return builder(effort) if builder else None


def supports_temperature(
    model_name: str,
    reasoning_effort: str | None = None,
) -> bool:
    """Return True when the model accepts a temperature parameter.

    Temperature is omitted for fixed-temperature Kimi K3, GPT-5, and
    o-series models. GPT-6 requires explicit ``"none"`` effort; its
    default enables reasoning.
    """
    if model_slug(model_name) in KIMI_K3_MODELS:
        return False
    name = model_name.lower()
    if "gpt-6" in name:
        return bool(reasoning_effort and reasoning_effort.lower() == "none")
    return not any(token in name for token in ("gpt-5", "o1", "o3", "o4"))
