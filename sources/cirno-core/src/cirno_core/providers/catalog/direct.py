"""Builtin direct provider definitions."""

from __future__ import annotations

from cirno_core.providers.catalog.contracts import ProviderSpec
from cirno_core.providers.model_api import (
    ResponsesCapabilities,
)

CUSTOM = ProviderSpec(
    name="custom",
    keywords=(),
    env_key="",
    request_apis=("chat_completions", "responses", "anthropic_messages"),
    display_name="Custom",
    backend="openai_compat",
    is_direct=True,
)


AZURE_OPENAI = ProviderSpec(
    name="azure_openai",
    keywords=("azure", "azure-openai"),
    env_key="",
    request_apis=("responses",),
    display_name="Azure OpenAI",
    backend="azure_openai",
    is_direct=True,
)


BEDROCK = ProviderSpec(
    name="bedrock",
    keywords=(
        "bedrock",
        "anthropic.claude",
        "amazon.nova",
        "meta.",
        "mistral.",
        "cohere.",
        "qwen.",
        "deepseek.",
        "openai.gpt-oss",
        "ai21.",
        "moonshot.",
        "writer.",
        "zai.",
    ),
    env_key="AWS_BEARER_TOKEN_BEDROCK",
    request_apis=("bedrock_converse",),
    display_name="AWS Bedrock",
    backend="bedrock",
    is_direct=True,
)


ANTHROPIC = ProviderSpec(
    name="anthropic",
    keywords=("anthropic", "claude"),
    env_key="ANTHROPIC_API_KEY",
    request_apis=("anthropic_messages",),
    display_name="Anthropic",
    backend="anthropic",
    supports_prompt_caching=True,
)


OPENAI = ProviderSpec(
    name="openai",
    keywords=("openai", "gpt"),
    env_key="OPENAI_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="OpenAI",
    backend="openai_compat",
    supports_max_completion_tokens=True,
    responses=ResponsesCapabilities(
        model_prefixes=("gpt-5", "gpt-6", "o1", "o3", "o4"),
        route_reasoning=True,
        requires_direct_openai_base=True,
        reasoning_replay="encrypted",
        supports_native_compaction=True,
    ),
)
