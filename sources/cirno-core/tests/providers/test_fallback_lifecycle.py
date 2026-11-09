"""Rejected continuation candidates still release their provider transports."""

from unittest.mock import AsyncMock, Mock

import pytest

from cirno_core.config.models import ModelPresetConfig
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.contracts import LLMResponse, ProviderCallContext, ProviderConversationState
from cirno_core.providers.fallback_provider import FallbackProvider


class Provider(LLMProvider):
    def get_default_model(self):
        return "model"

    async def chat(self, **kwargs):
        return LLMResponse("unavailable", finish_reason="error", error_kind="server_error")


@pytest.mark.parametrize("capability_error", [False, True])
async def test_unused_fallback_is_closed_when_continuation_cannot_be_prepared(capability_error):
    primary, fallback = Provider(provider_name="primary"), Provider(provider_name="backup")
    fallback.aclose = AsyncMock()
    fallback.chat = AsyncMock()
    if capability_error:
        fallback.can_resume_conversation_state = Mock(side_effect=ValueError("invalid continuation"))
    wrapper = FallbackProvider(
        primary, [ModelPresetConfig(model="backup")], lambda _preset: fallback,
    )
    context = ProviderCallContext(
        conversation_state=ProviderConversationState("opaque", "primary", "model", 1),
        compaction_input_budget=1000,
    )
    if capability_error:
        with pytest.raises(ValueError, match="invalid continuation"):
            await wrapper.chat_with_context(messages=[], provider_context=context)
    else:
        response = await wrapper.chat_with_context(messages=[], provider_context=context)
        assert response.finish_reason == "error"
    fallback.chat.assert_not_awaited()
    fallback.aclose.assert_awaited_once()
