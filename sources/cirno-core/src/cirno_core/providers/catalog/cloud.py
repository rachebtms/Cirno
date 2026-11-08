"""Builtin cloud provider definitions."""

from __future__ import annotations

from cirno_core.providers.catalog.contracts import ProviderModelSpec, ProviderSpec
from cirno_core.providers.catalog.models import _DEEPSEEK_REASONING_EFFORTS
from cirno_core.providers.model_api import (
    ResponsesCapabilities,
)

DEEPSEEK = ProviderSpec(
    name="deepseek",
    keywords=("deepseek",),
    env_key="DEEPSEEK_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="DeepSeek",
    backend="openai_compat",
    default_api_base="https://api.deepseek.com",
    thinking_style="thinking_type",
    builtin_models=(
        ProviderModelSpec(
            id="deepseek-flash",
            aliases=("deepseek-v4-flash", "deepseek-v4-flash-vision-exp"),
            context_window=1_000_000,
            max_output_tokens=393_216,
            input_modalities=("text", "image"),
            output_modalities=("text",),
            reasoning_efforts=_DEEPSEEK_REASONING_EFFORTS,
            default_reasoning_effort="high",
        ),
        ProviderModelSpec(
            id="deepseek-v4-pro",
            context_window=1_000_000,
            max_output_tokens=393_216,
            input_modalities=("text",),
            output_modalities=("text",),
            reasoning_efforts=_DEEPSEEK_REASONING_EFFORTS,
            default_reasoning_effort="high",
        ),
    ),
    responses=ResponsesCapabilities(
        models=(
            "deepseek-v4-flash",
            "deepseek-v4-pro",
            "deepseek-v4-flash-vision-exp",
        ),
        endpoint_models=(("https://api.deepseek.com", ("deepseek-flash",)),),
        reasoning_replay="plaintext",
        supports_hosted_web_search=False,
    ),
)


GEMINI = ProviderSpec(
    name="gemini",
    keywords=("gemini", "gemma"),
    env_key="GEMINI_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="Gemini",
    backend="openai_compat",
    default_api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
)


ZHIPU = ProviderSpec(
    name="zhipu",
    keywords=("zhipu", "glm", "zai"),
    env_key="ZAI_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="Zhipu AI",
    backend="openai_compat",
    env_extras=(("ZHIPUAI_API_KEY", "{api_key}"),),
    default_api_base="https://open.bigmodel.cn/api/paas/v4",
)


DASHSCOPE = ProviderSpec(
    name="dashscope",
    keywords=("qwen", "dashscope"),
    env_key="DASHSCOPE_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="DashScope",
    backend="openai_compat",
    default_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
    thinking_style="enable_thinking",
)


MOONSHOT = ProviderSpec(
    name="moonshot",
    keywords=("moonshot", "kimi"),
    env_key="MOONSHOT_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="Moonshot",
    backend="openai_compat",
    default_api_base="https://api.moonshot.ai/v1",
    model_overrides=(
        ("kimi-k2.7", {"temperature": 1.0}),
        ("kimi-k2.7-code", {"temperature": 1.0}),
        ("kimi-k2.7-code-highspeed", {"temperature": 1.0}),
    ),
)


KIMI_CODING = ProviderSpec(
    name="kimi_coding",
    keywords=("kimi-coding", "kimi_coding", "kimi-for-coding"),
    env_key="KIMI_CODING_API_KEY",
    request_apis=("anthropic_messages",),
    display_name="Kimi Coding",
    backend="anthropic",
    default_api_base="https://api.kimi.com/coding/v1",
    default_extra_headers=(("User-Agent", "claude-code/0.1.0"),),
)


MINIMAX = ProviderSpec(
    name="minimax",
    keywords=("minimax",),
    env_key="MINIMAX_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="MiniMax",
    backend="openai_compat",
    default_api_base="https://api.minimax.io/v1",
    thinking_style="reasoning_split",
    builtin_models=(
        ProviderModelSpec(
            id="MiniMax-M3.1-Flash",
            label="MiniMax-M3.1-Flash",
            aliases=("minimax-m3.1-flash",),
            context_window=1_000_000,
            reasoning_efforts=("low", "medium", "high", "xhigh", "max"),
            default_reasoning_effort="max",
            input_modalities=("text", "image"),
        ),
    ),
    reasoning_effort_remap=(
        ("none", "low"),
        ("minimal", "low"),
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
    ),
)


MINIMAX_ANTHROPIC = ProviderSpec(
    name="minimax_anthropic",
    keywords=("minimax_anthropic",),
    env_key="MINIMAX_API_KEY",
    request_apis=("anthropic_messages",),
    display_name="MiniMax (Anthropic)",
    backend="anthropic",
    default_api_base="https://api.minimax.io/anthropic",
)


MISTRAL = ProviderSpec(
    name="mistral",
    keywords=("mistral", "magistral", "ministral", "codestral", "devstral"),
    env_key="MISTRAL_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="Mistral",
    backend="openai_compat",
    default_api_base="https://api.mistral.ai/v1",
    reasoning_effort_remap=(
        ("minimal", "none"),
        ("low", "none"),
        ("medium", "high"),
        ("high", "high"),
        ("none", "none"),
    ),
    implicit_reasoning_models=("magistral",),
    extract_thinking_blocks=True,
    strip_history_reasoning_content=True,
)


STEPFUN = ProviderSpec(
    name="stepfun",
    keywords=("stepfun", "step"),
    env_key="STEPFUN_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="Step Fun",
    backend="openai_compat",
    default_api_base="https://api.stepfun.com/v1",
    reasoning_as_content=True,
)


XIAOMI_MIMO = ProviderSpec(
    name="xiaomi_mimo",
    keywords=("xiaomi_mimo", "mimo"),
    env_key="XIAOMIMIMO_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="Xiaomi MIMO",
    backend="openai_compat",
    default_api_base="https://api.xiaomimimo.com/v1",
    thinking_style="thinking_type",
)


LONGCAT = ProviderSpec(
    name="longcat",
    keywords=("longcat",),
    env_key="LONGCAT_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="LongCat",
    backend="openai_compat",
    default_api_base="https://api.longcat.chat/openai/v1",
)


ANT_LING = ProviderSpec(
    name="ant_ling",
    keywords=("ant_ling", "ant-ling", "ling-", "ring-"),
    env_key="ANT_LING_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="Ant Ling",
    backend="openai_compat",
    detect_by_base_keyword="ant-ling.com",
    default_api_base="https://api.ant-ling.com/v1",
)


NVIDIA = ProviderSpec(
    name="nvidia",
    keywords=("nvidia", "nemotron", "nvapi"),
    env_key="NVIDIA_NIM_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="NVIDIA NIM",
    backend="openai_compat",
    is_gateway=False,
    detect_by_key_prefix="nvapi-",
    detect_by_base_keyword="nvidia.com",
    default_api_base="https://integrate.api.nvidia.com/v1",
)


GROQ = ProviderSpec(
    name="groq",
    keywords=("groq",),
    env_key="GROQ_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="Groq",
    backend="openai_compat",
    default_api_base="https://api.groq.com/openai/v1",
)


QIANFAN = ProviderSpec(
    name="qianfan",
    keywords=("qianfan", "ernie"),
    env_key="QIANFAN_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="Qianfan",
    backend="openai_compat",
    default_api_base="https://qianfan.baidubce.com/v2",
)
