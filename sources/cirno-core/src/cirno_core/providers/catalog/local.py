"""Builtin local provider definitions."""

from __future__ import annotations

from cirno_core.providers.catalog.contracts import ProviderSpec

VLLM = ProviderSpec(
    name="vllm",
    keywords=("vllm",),
    env_key="HOSTED_VLLM_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="vLLM",
    backend="openai_compat",
    is_local=True,
)


OLLAMA = ProviderSpec(
    name="ollama",
    keywords=("ollama", "nemotron"),
    env_key="OLLAMA_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="Ollama",
    backend="openai_compat",
    is_local=True,
    detect_by_base_keyword="11434",
    default_api_base="http://localhost:11434/v1",
)


LM_STUDIO = ProviderSpec(
    name="lm_studio",
    keywords=("lm-studio", "lmstudio", "lm_studio"),
    env_key="LM_STUDIO_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="LM Studio",
    backend="openai_compat",
    is_local=True,
    detect_by_base_keyword="1234",
    default_api_base="http://localhost:1234/v1",
)


ATOMIC_CHAT = ProviderSpec(
    name="atomic_chat",
    keywords=("atomic-chat", "atomic_chat", "atomicchat"),
    env_key="ATOMIC_CHAT_API_KEY",
    request_apis=("chat_completions", "responses"),
    display_name="Atomic Chat",
    backend="openai_compat",
    is_local=True,
    detect_by_base_keyword="1337",
    default_api_base="http://localhost:1337/v1",
)


OVMS = ProviderSpec(
    name="ovms",
    keywords=("openvino", "ovms"),
    env_key="",
    request_apis=("chat_completions", "responses"),
    display_name="OpenVINO Model Server",
    backend="openai_compat",
    is_direct=True,
    is_local=True,
    default_api_base="http://localhost:8000/v3",
)
