"""Builtin subscriptions provider definitions."""

from __future__ import annotations

from cirno_core.providers.catalog.contracts import ProviderModelSpec, ProviderSpec
from cirno_core.providers.model_api import (
    ResponsesCapabilities,
)

OPENAI_CODEX = ProviderSpec(
    name="openai_codex",
    keywords=("openai-codex",),
    env_key="",
    request_apis=("responses",),
    display_name="OpenAI Codex",
    model_catalog="hybrid",
    builtin_models=(
        ProviderModelSpec(
            id="openai-codex/gpt-5.6-sol",
            label="GPT-5.6-Sol",
            description="Latest frontier agentic coding model.",
            context_window=272_000,
            reasoning_efforts=("low", "medium", "high", "xhigh", "max", "ultra"),
        ),
        ProviderModelSpec(
            id="openai-codex/gpt-5.6-terra",
            label="GPT-5.6-Terra",
            description="Balanced agentic coding model for everyday work.",
            context_window=272_000,
            reasoning_efforts=("low", "medium", "high", "xhigh", "max", "ultra"),
        ),
        ProviderModelSpec(
            id="openai-codex/gpt-5.6-luna",
            label="GPT-5.6-Luna",
            description="Fast and affordable agentic coding model.",
            context_window=272_000,
            reasoning_efforts=("low", "medium", "high", "xhigh", "max"),
        ),
        ProviderModelSpec(
            id="openai-codex/gpt-5.5",
            label="GPT-5.5",
            description="Frontier model for complex coding, research, and real-world work.",
            context_window=272_000,
            reasoning_efforts=("low", "medium", "high", "xhigh"),
        ),
        ProviderModelSpec(
            id="openai-codex/gpt-5.4",
            label="GPT-5.4",
            description="Strong model for everyday coding.",
            context_window=272_000,
            reasoning_efforts=("low", "medium", "high", "xhigh"),
        ),
        ProviderModelSpec(
            id="openai-codex/gpt-5.4-mini",
            label="GPT-5.4-Mini",
            description="Small, fast, and cost-efficient model for simpler coding tasks.",
            context_window=272_000,
            reasoning_efforts=("low", "medium", "high", "xhigh"),
        ),
        ProviderModelSpec(
            id="openai-codex/gpt-5.3-codex-spark",
            label="GPT-5.3-Codex-Spark",
            description="Ultra-fast coding model.",
            context_window=128_000,
            reasoning_efforts=("low", "medium", "high", "xhigh"),
        ),
    ),
    backend="openai_codex",
    detect_by_base_keyword="codex",
    default_api_base="https://chatgpt.com/backend-api",
    is_oauth=True,
)


XAI_GROK = ProviderSpec(
    name="xai_grok",
    keywords=("xai-grok", "xai_grok"),
    env_key="",
    request_apis=("responses",),
    display_name="xAI Grok",
    model_catalog="hybrid",
    builtin_models=(
        ProviderModelSpec(
            id="xai-grok/grok-4.6",
            label="Grok 4.6",
            description="Grok via xAI subscription; X Search is enabled when supported.",
            context_window=500_000,
        ),
        ProviderModelSpec(
            id="xai-grok/grok-4.5",
            label="Grok 4.5",
            description="Grok via xAI subscription; X Search is enabled when supported.",
            context_window=500_000,
        ),
    ),
    backend="xai_grok",
    default_api_base="https://cli-chat-proxy.grok.com/v1",
    is_oauth=True,
)


GITHUB_COPILOT = ProviderSpec(
    name="github_copilot",
    keywords=("github_copilot", "copilot"),
    env_key="",
    request_apis=("chat_completions", "responses"),
    display_name="Github Copilot",
    model_catalog="hybrid",
    builtin_models=(
        ProviderModelSpec(
            id="github-copilot/gpt-5.4-mini",
            label="GPT-5.4 Mini",
            description="GitHub Copilot Responses model.",
        ),
        ProviderModelSpec(
            id="github-copilot/gpt-4.1",
            label="GPT-4.1",
            description="GitHub Copilot chat model.",
        ),
    ),
    backend="github_copilot",
    default_api_base="https://api.githubcopilot.com",
    strip_model_prefix=True,
    is_oauth=True,
    supports_max_completion_tokens=True,
    responses=ResponsesCapabilities(
        model_prefixes=("gpt-5", "gpt-6", "o1", "o3", "o4"),
        route_reasoning=True,
        reasoning_replay="encrypted",
        allows_chat_fallback=False,
    ),
)
