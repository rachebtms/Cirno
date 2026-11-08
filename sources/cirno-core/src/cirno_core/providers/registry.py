"""Ordered builtin providers and dynamic provider identity resolution."""

from __future__ import annotations

from cirno_core.providers.catalog import cloud, contracts, direct, local, routers, subscriptions
from pydantic.alias_generators import to_snake

# Order controls automatic matching priority.
PROVIDERS: tuple[contracts.ProviderSpec, ...] = (
    direct.CUSTOM,
    direct.AZURE_OPENAI,
    direct.BEDROCK,
    routers.OPENROUTER,
    routers.ORCAROUTER,
    routers.EDENAI,
    routers.OPENCODE,
    routers.OPENCODE_GO,
    routers.HUGGINGFACE,
    routers.SKYWORK,
    routers.AIHUBMIX,
    routers.SILICONFLOW,
    routers.NOVITA,
    routers.VOLCENGINE,
    routers.VOLCENGINE_CODING_PLAN,
    routers.BYTEPLUS,
    routers.BYTEPLUS_CODING_PLAN,
    direct.ANTHROPIC,
    direct.OPENAI,
    subscriptions.OPENAI_CODEX,
    subscriptions.XAI_GROK,
    subscriptions.GITHUB_COPILOT,
    cloud.DEEPSEEK,
    cloud.GEMINI,
    cloud.ZHIPU,
    cloud.DASHSCOPE,
    routers.MODELSCOPE,
    cloud.MOONSHOT,
    cloud.KIMI_CODING,
    cloud.MINIMAX,
    cloud.MINIMAX_ANTHROPIC,
    cloud.MISTRAL,
    cloud.STEPFUN,
    cloud.XIAOMI_MIMO,
    cloud.LONGCAT,
    cloud.ANT_LING,
    local.VLLM,
    local.OLLAMA,
    local.LM_STUDIO,
    local.ATOMIC_CHAT,
    local.OVMS,
    cloud.NVIDIA,
    cloud.GROQ,
    cloud.QIANFAN,
)


def find_by_name(name: str) -> contracts.ProviderSpec | None:
    """Find a provider spec by config field name, e.g. "dashscope"."""
    normalized = to_snake(name.replace("-", "_"))
    for spec in PROVIDERS:
        if spec.name == normalized:
            return spec
    return None


def create_dynamic_spec(
    name: str,
    *,
    display_name: str = "",
    thinking_style: str = "",
) -> contracts.ProviderSpec:
    """Create a dynamic contracts.ProviderSpec for custom user-defined providers."""
    normalized = to_snake(name.replace("-", "_"))
    strip_prefixes = tuple(dict.fromkeys((name, normalized)))
    return contracts.ProviderSpec(
        name=normalized,
        keywords=(),
        env_key="",
        request_apis=("chat_completions", "responses", "anthropic_messages"),
        display_name=display_name or name.replace("-", " ").replace("_", " ").title(),
        backend="openai_compat",
        is_direct=True,
        strip_model_prefixes=strip_prefixes,
        thinking_style=thinking_style,
    )
