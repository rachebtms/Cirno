"""Visual probing must prove perception, not just acceptance of a request."""
import base64
import io
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.media_capabilities import MediaCapabilities, probe_visual_inputs, probe_image
from cirno_core.providers.openai_compat_provider import OpenAICompatProvider


@pytest.mark.parametrize("failure", [False, True])
async def test_probe_uses_actual_pixels_and_does_not_turn_service_failure_into_unsupported(monkeypatch, failure):
    provider = OpenAICompatProvider(api_key="test", default_model="test")
    monkeypatch.setattr("secrets.SystemRandom.sample", lambda self, values, count: ["green", "blue", "red"])
    async def complete(**kwargs):
        assert not kwargs.get("tools")
        content = kwargs["messages"][0]["content"]
        assert "green" not in content[0]["text"]
        if content[1]["type"] == "image_url":
            png = Image.open(io.BytesIO(base64.b64decode(content[1]["image_url"]["url"].split(",", 1)[1])))
            assert png.getpixel((0, 0)) == (0, 255, 0)
        else:
            clip = base64.b64decode(content[1]["video_url"]["url"].split(",", 1)[1])
            assert b"ftyp" in clip[:32]
        return LLMResponse(content="Connection timed out", finish_reason="error", error_kind="timeout") if failure else LLMResponse(content="green blue red")
    monkeypatch.setattr(provider, "chat", complete)
    try:
        result = await probe_visual_inputs(provider, model="test", video_transport=True)
        assert result["image"]["supported"] is (None if failure else True)
        assert result["video"]["supported"] is (None if failure else True)
    finally:
        await provider.aclose()


async def test_declared_text_only_model_does_not_retry_by_silently_removing_images(monkeypatch):
    provider = OpenAICompatProvider(api_key="test", default_model="test")
    provider.media_capabilities = MediaCapabilities(image=False)
    chat = AsyncMock()
    monkeypatch.setattr(provider, "chat", chat)
    messages = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": probe_image(("red", "blue", "green"))}}]}]
    try:
        result = await provider.chat_with_retry(messages, max_tokens=128)
        assert result.finish_reason == "error" and result.error_kind == "unsupported_media"
        chat.assert_not_awaited()
        assert messages[0]["content"][0]["type"] == "image_url"
    finally:
        await provider.aclose()


async def test_fallback_leaf_checks_its_own_declared_capabilities():
    from cirno_core.providers.fallback_provider import FallbackProvider
    provider = OpenAICompatProvider(api_key="test", default_model="text-only")
    provider.media_capabilities = MediaCapabilities(image=False)
    wrapper = FallbackProvider(provider, [], lambda preset: provider)
    call = AsyncMock()
    try:
        result, error = await wrapper._call_provider(call, provider, {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": probe_image(("red", "blue", "green"))}}]}]})
        assert error is None and result.error_kind == "unsupported_media"
        call.assert_not_awaited()
    finally:
        await wrapper.aclose()
