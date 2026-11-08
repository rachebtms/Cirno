"""Builtin routers provider definitions."""

from __future__ import annotations

from cirno_core.providers.catalog.contracts import ProviderSpec
from cirno_core.providers.model_api import (
    ResponsesCapabilities,
)

OPENROUTER = ProviderSpec(
    name="openrouter",
    keywords=("openrouter",),
    env_key="OPENROUTER_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="OpenRouter",
    backend="openai_compat",
    is_gateway=True,
    detect_by_key_prefix="sk-or-",
    detect_by_base_keyword="openrouter",
    default_api_base="https://openrouter.ai/api/v1",
    supports_prompt_caching=True,
    gateway_reasoning_style="reasoning_effort",
)


ORCAROUTER = ProviderSpec(
    name="orcarouter",
    keywords=("orcarouter",),
    env_key="ORCAROUTER_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="OrcaRouter",
    backend="openai_compat",
    is_gateway=True,
    detect_by_key_prefix="sk-orca-",
    detect_by_base_keyword="orcarouter",
    default_api_base="https://api.orcarouter.ai/v1",
)


EDENAI = ProviderSpec(
    name="edenai",
    keywords=("edenai",),
    env_key="EDENAI_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="Eden AI",
    backend="openai_compat",
    is_gateway=True,
    detect_by_base_keyword="edenai",
    default_api_base="https://api.edenai.run/v3",
)


OPENCODE = ProviderSpec(
    name="opencode",
    keywords=("opencode/", "opencode", "opencode-zen", "opencode_zen"),
    env_key="OPENCODE_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="OpenCode Zen",
    backend="openai_compat",
    is_gateway=True,
    detect_by_base_keyword="opencode.ai/zen",
    default_api_base="https://opencode.ai/zen/v1",
    strip_model_prefixes=("opencode", "opencode_zen", "opencode-zen"),
)


OPENCODE_GO = ProviderSpec(
    name="opencode_go",
    keywords=("opencode-go", "opencode_go"),
    env_key="OPENCODE_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="OpenCode Go",
    backend="openai_compat",
    is_gateway=True,
    detect_by_base_keyword="opencode.ai/zen/go",
    default_api_base="https://opencode.ai/zen/go/v1",
    strip_model_prefixes=("opencode-go", "opencode_go"),
    responses=ResponsesCapabilities(
        models=("muse-spark-1.2-contributor", "muse-spark-1.3-contributor"),
        allows_chat_fallback=False,
    ),
)


HUGGINGFACE = ProviderSpec(
    name="huggingface",
    keywords=("huggingface", "hugging-face"),
    env_key="HF_TOKEN",
    request_apis=("chat_completions", "responses"),
    display_name="Hugging Face",
    backend="openai_compat",
    is_gateway=True,
    detect_by_key_prefix="hf_",
    detect_by_base_keyword="huggingface",
    default_api_base="https://router.huggingface.co/v1",
)


SKYWORK = ProviderSpec(
    name="skywork",
    keywords=("skywork", "skyclaw", "apifree"),
    env_key="SKYWORK_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="Skywork",
    model_catalog="official",
    backend="openai_compat",
    env_extras=(("APIFREE_API_KEY", "{api_key}"),),
    is_gateway=True,
    detect_by_base_keyword="apifree.ai",
    default_api_base="https://api.apifree.ai/agent/v1",
)


AIHUBMIX = ProviderSpec(
    name="aihubmix",
    keywords=("aihubmix",),
    env_key="OPENAI_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="AiHubMix",
    backend="openai_compat",
    is_gateway=True,
    detect_by_base_keyword="aihubmix",
    default_api_base="https://aihubmix.com/v1",
    strip_model_prefix=True,
)


SILICONFLOW = ProviderSpec(
    name="siliconflow",
    keywords=("siliconflow",),
    env_key="OPENAI_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="SiliconFlow",
    backend="openai_compat",
    is_gateway=True,
    detect_by_base_keyword="siliconflow",
    default_api_base="https://api.siliconflow.cn/v1",
)


NOVITA = ProviderSpec(
    name="novita",
    keywords=("novita",),
    env_key="NOVITA_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="Novita AI",
    backend="openai_compat",
    is_gateway=True,
    detect_by_base_keyword="novita",
    default_api_base="https://api.novita.ai/openai",
)


VOLCENGINE = ProviderSpec(
    name="volcengine",
    keywords=("volcengine", "volces", "ark"),
    env_key="OPENAI_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="VolcEngine",
    backend="openai_compat",
    is_gateway=True,
    detect_by_base_keyword="volces",
    default_api_base="https://ark.cn-beijing.volces.com/api/v3",
    thinking_style="thinking_type",
    supports_max_completion_tokens=True,
)


VOLCENGINE_CODING_PLAN = ProviderSpec(
    name="volcengine_coding_plan",
    keywords=("volcengine-plan",),
    env_key="OPENAI_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="VolcEngine Coding Plan",
    backend="openai_compat",
    is_gateway=True,
    default_api_base="https://ark.cn-beijing.volces.com/api/coding/v3",
    strip_model_prefix=True,
    thinking_style="thinking_type",
    supports_max_completion_tokens=True,
)


BYTEPLUS = ProviderSpec(
    name="byteplus",
    keywords=("byteplus",),
    env_key="OPENAI_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="BytePlus",
    backend="openai_compat",
    is_gateway=True,
    detect_by_base_keyword="bytepluses",
    default_api_base="https://ark.ap-southeast.bytepluses.com/api/v3",
    strip_model_prefix=True,
    thinking_style="thinking_type",
)


BYTEPLUS_CODING_PLAN = ProviderSpec(
    name="byteplus_coding_plan",
    keywords=("byteplus-plan",),
    env_key="OPENAI_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="BytePlus Coding Plan",
    backend="openai_compat",
    is_gateway=True,
    default_api_base="https://ark.ap-southeast.bytepluses.com/api/coding/v3",
    strip_model_prefix=True,
    thinking_style="thinking_type",
)


MODELSCOPE = ProviderSpec(
    name="modelscope",
    keywords=("modelscope",),
    env_key="MODELSCOPE_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="ModelScope",
    backend="openai_compat",
    is_gateway=True,
    detect_by_base_keyword="modelscope",
    default_api_base="https://api-inference.modelscope.cn/v1",
    strip_model_prefixes=("modelscope",),
    thinking_style="enable_thinking",
)
