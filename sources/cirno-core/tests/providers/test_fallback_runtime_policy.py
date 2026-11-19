"""Adding a fallback must preserve the configured primary runtime policy."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_core.agent.tools.filesystem import read
from cirno_core.config.models import ModelPresetConfig
from cirno_core.config.schema import Config
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.factory import build_provider_snapshot
from cirno_core.providers.fallback_provider import FallbackProvider
from cirno_core.providers.generation import GenerationSettings
from cirno_core.providers.media_capabilities import MediaCapabilities
from cirno_core.providers.reasoning_history import history_policy
from cirno_core.providers.retry import ProviderRetryPolicy
from cirno_core.utils import token_estimation
from loguru import logger


class Provider(LLMProvider):
    def __init__(self):
        super().__init__(provider_name="fixture")

    def get_default_model(self):
        return "fixture-model"

    async def chat(self, **_kwargs):
        return LLMResponse("temporarily unavailable", finish_reason="error", error_kind="server_error")


def wrapper(primary):
    return FallbackProvider(primary, [ModelPresetConfig(model="backup")], lambda _: Provider())


def test_wrapper_owns_copies_of_configured_retry_and_timeout_settings():
    primary = Provider()
    primary.retry_policy = ProviderRetryPolicy(delays=(1, 2, 4, 8, 16), heartbeat_seconds=7, identical_error_limit=20)
    primary.request_timeout_s = 600
    primary.stream_idle_timeout_s = 180
    result = wrapper(primary)
    assert result.retry_policy == primary.retry_policy
    assert result.timeouts == primary.timeouts
    assert result.retry_policy is not primary.retry_policy
    assert result.timeouts is not primary.timeouts


def test_wrapper_preserves_generation_and_keeps_explicit_changes_forwarded():
    primary = Provider()
    configured = GenerationSettings(temperature=0.2, max_tokens=12345, reasoning_effort="high")
    primary.generation = configured
    result = wrapper(primary)
    assert primary.generation is configured
    assert result.generation is configured
    changed = GenerationSettings(max_tokens=6789)
    result.generation = changed
    assert primary.generation is changed
    primary.generation = configured
    assert result.generation is configured


def test_base_initialization_does_not_call_subclass_configuration_setters():
    class ForwardingProvider(Provider):
        @LLMProvider.generation.setter
        def generation(self, value):
            raise AssertionError("Forwarding target is not initialized yet")

    provider = ForwardingProvider()
    assert provider.generation == GenerationSettings()


def test_saved_model_and_network_settings_survive_provider_snapshot(monkeypatch):
    class FakeCompat(Provider):
        def __init__(self, **_kwargs):
            super().__init__()

    monkeypatch.setattr("cirno_core.providers.openai_compat_provider.OpenAICompatProvider", FakeCompat)
    config = Config.model_validate({
        "network": {"requestTimeoutS": 600, "streamIdleTimeoutS": 180, "providerMaxRetries": 5},
        "agents": {"defaults": {"modelPreset": "primary", "fallbackModels": ["backup"]}},
        "modelPresets": {
            "primary": {"model": "fixture-primary", "provider": "openai", "imageInput": False, "videoInput": False, "reasoningHistory": "omit"},
            "backup": {"model": "fixture-backup", "provider": "openai"},
        },
        "providers": {"openai": {"apiKey": "fake-key"}},
    })
    result = build_provider_snapshot(config).provider
    assert isinstance(result, FallbackProvider)
    assert result.retry_policy.delays == (1, 2, 4, 8, 16)
    assert result.request_timeout_s == 600
    assert result.stream_idle_timeout_s == 180
    assert result.media_capabilities == MediaCapabilities(False, False)
    assert history_policy(result, for_count=True) == "omit"


async def test_persistent_retry_uses_configured_chain_delay_schedule(monkeypatch):
    primary = Provider()
    primary.retry_policy = ProviderRetryPolicy(delays=(1, 2, 4, 8, 16))
    result = wrapper(primary)
    result.retry_executor.wait = AsyncMock()
    monkeypatch.setattr("cirno_core.providers.retry.random.uniform", lambda _low, high: high)
    failure = LLMResponse("busy", finish_reason="error", error_kind="server_error", error_status_code=503)
    call = AsyncMock(side_effect=[failure] * 4 + [LLMResponse("ready")])
    response = await result.retry_executor.attempts(call, {"messages": []}, [], retry_mode="persistent", on_retry_wait=None, on_retry_exhausted=None, on_retry_status=None)
    assert response.content == "ready"
    waits = [entry.args[0] for entry in result.retry_executor.wait.await_args_list]
    assert waits == [1, 2, 4, 8]


@pytest.mark.parametrize("enabled", [False, True])
def test_file_image_guard_sees_primary_capability_through_wrapper(monkeypatch, enabled):
    primary = Provider()
    primary.media_capabilities = MediaCapabilities(image=enabled, video=False)
    result = wrapper(primary)
    monkeypatch.setattr(read, "current_request_context", lambda: SimpleNamespace(runtime=SimpleNamespace(provider=result)))
    assert (read.image_input_error() is None) is enabled
    assert result.media_capabilities.video is False


@pytest.mark.parametrize("policy,spec_name,strip,tools,expected", [
    ("omit", "custom", False, None, "omit"),
    ("auto", "mistral", True, None, "omit"),
    ("auto", "deepseek", False, None, "omit"),
    ("preserve", "custom", False, None, "preserve"),
    ("auto", "deepseek", False, [{"type": "function"}], "preserve"),
])
def test_context_estimator_uses_primary_reasoning_history(monkeypatch, policy, spec_name, strip, tools, expected):
    primary = Provider()
    primary.reasoning_history = policy
    primary._spec = SimpleNamespace(name=spec_name, strip_history_reasoning_content=strip)
    result = wrapper(primary)
    assert history_policy(result, tools=tools, for_count=True) == expected
    messages = [{"role": "assistant", "content": "Answer", "reasoning_content": "Long working notes", "thinking_blocks": [{"type": "redacted_thinking", "data": "opaque"}]}]
    original = deepcopy(messages)
    estimate = Mock(return_value=(12, "fixture"))
    monkeypatch.setattr(token_estimation, "_estimate_prompt_tokens_with_source", estimate)
    assert token_estimation.estimate_prompt_tokens_chain(result, "fixture", messages, tools) == (12, "fixture")
    counted = estimate.call_args.args[0]
    assert ("reasoning_content" in counted[0]) is (expected == "preserve")
    assert counted[0]["thinking_blocks"] == original[0]["thinking_blocks"]
    assert messages == original


def test_deepseek_tool_reasoning_requirement_applies_through_wrapper():
    primary = Provider()
    primary.reasoning_history = "omit"
    primary._spec = SimpleNamespace(name="deepseek", strip_history_reasoning_content=False)
    with pytest.raises(ValueError, match="require reasoning history"):
        history_policy(wrapper(primary), tools=[{"type": "function"}], for_count=True)


async def test_fallback_constructor_log_does_not_publish_exception_body():
    detail = "Invalid proxy http://private-user:PrivatePassword2026@proxy.test; PrivatePrompt2026"
    primary, backup = Provider(), Provider()
    backup.chat = AsyncMock(return_value=LLMResponse("ready"))
    def factory(preset):
        if preset.model == "bad":
            raise ValueError(detail)
        return backup
    result = FallbackProvider(primary, [ModelPresetConfig(model="bad"), ModelPresetConfig(model="backup")], factory)
    lines = []
    sink = logger.add(lambda message: lines.append(str(message)), format="{message}")
    try:
        response = await result.chat(messages=[])
    finally:
        logger.remove(sink)
    assert response.content == "ready"
    text = "\n".join(lines)
    assert "PrivatePassword2026" not in text
    assert "PrivatePrompt2026" not in text
    assert "ValueError" in text
