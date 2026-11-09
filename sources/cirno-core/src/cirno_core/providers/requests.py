"""Execute one physical provider call and record its final or cancelled outcome."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

from cirno_core.providers.contracts import LLMResponse, ProviderCallContext
from cirno_core.providers.errors import is_billing_error, response_from_exception
from cirno_core.providers.request_budget import bound_request_output
from cirno_core.providers.media_capabilities import media_input_error
from cirno_core.providers.messages import (
    contains_image_content,
    strip_image_content,
    strip_image_content_inplace,
)
from loguru import logger

if TYPE_CHECKING:
    from cirno_core.providers.base import LLMProvider


class ProviderRequestExecutor:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def complete(self, **kwargs: Any) -> LLMResponse:
        """Call chat() and convert unexpected exceptions to error responses."""
        started_at_ms = time.time_ns() // 1_000_000
        started_at_ns = time.monotonic_ns()
        unsupported = media_input_error(self.provider, kwargs["messages"])
        if unsupported is not None:
            return unsupported
        try:
            kwargs = bound_request_output(self.provider, kwargs)
            provider_context = kwargs.pop("provider_context", None)
            if isinstance(provider_context, ProviderCallContext):
                response = await self.provider.chat_with_context(
                    provider_context=provider_context,
                    **kwargs,
                )
            else:
                response = await self.provider.chat(**kwargs)
        except asyncio.CancelledError:
            self.provider.usage_recorder.observe(
                LLMResponse(
                    content=None,
                    finish_reason="cancelled",
                    error_kind="cancelled",
                ),
                kwargs,
                started_at_ms=started_at_ms,
                started_at_ns=started_at_ns,
                stream=False,
            )
            raise
        except Exception as exc:
            response = response_from_exception(exc)
        return await self.provider.usage_recorder.observe_async(
            response,
            kwargs,
            started_at_ms=started_at_ms,
            started_at_ns=started_at_ns,
            stream=False,
        )

    async def stream(self, **kwargs: Any) -> LLMResponse:
        """Call chat_stream() and convert unexpected exceptions to error responses."""
        started_at_ms = time.time_ns() // 1_000_000
        started_at_ns = time.monotonic_ns()
        first_output_at_ns: int | None = None

        def _mark_output(delta: str) -> None:
            nonlocal first_output_at_ns
            if delta and first_output_at_ns is None:
                first_output_at_ns = time.monotonic_ns()

        if self.provider.usage_recorder.observer is not None:
            content_callback = kwargs.get("on_content_delta")
            if callable(content_callback):
                typed_content_callback = cast(
                    Callable[[str], Awaitable[None]],
                    content_callback,
                )

                async def _timed_content_delta(delta: str) -> None:
                    _mark_output(delta)
                    await typed_content_callback(delta)

                kwargs["on_content_delta"] = _timed_content_delta

            thinking_callback = kwargs.get("on_thinking_delta")
            if callable(thinking_callback):
                typed_thinking_callback = cast(
                    Callable[[str], Awaitable[None]],
                    thinking_callback,
                )

                async def _timed_thinking_delta(delta: str) -> None:
                    _mark_output(delta)
                    await typed_thinking_callback(delta)

                kwargs["on_thinking_delta"] = _timed_thinking_delta

        def _attach_stream_timing(response: LLMResponse) -> LLMResponse:
            if first_output_at_ns is None:
                return response
            finished_at_ns = time.monotonic_ns()
            if response.ttft_ms is None:
                response.ttft_ms = max(0, round((first_output_at_ns - started_at_ns) / 1_000_000))
            if response.generation_ms is None:
                response.generation_ms = max(
                    1,
                    round((finished_at_ns - first_output_at_ns) / 1_000_000),
                )
            return response

        unsupported = media_input_error(self.provider, kwargs["messages"])
        if unsupported is not None:
            return unsupported
        try:
            kwargs = bound_request_output(self.provider, kwargs)
            provider_context = kwargs.pop("provider_context", None)
            if isinstance(provider_context, ProviderCallContext):
                response = await self.provider.chat_stream_with_context(
                    provider_context=provider_context,
                    **kwargs,
                )
            else:
                response = await self.provider.chat_stream(**kwargs)
        except asyncio.CancelledError:
            self.provider.usage_recorder.observe(
                LLMResponse(
                    content=None,
                    finish_reason="cancelled",
                    error_kind="cancelled",
                ),
                kwargs,
                started_at_ms=started_at_ms,
                started_at_ns=started_at_ns,
                stream=True,
            )
            raise
        except Exception as exc:
            response = response_from_exception(exc)
        return await self.provider.usage_recorder.observe_async(
            _attach_stream_timing(response),
            kwargs,
            started_at_ms=started_at_ms,
            started_at_ns=started_at_ns,
            stream=True,
        )


async def retry_without_images(
    call: Callable[..., Awaitable[LLMResponse]],
    kw: dict[str, Any],
    original_messages: list[dict[str, Any]],
    response: LLMResponse,
) -> LLMResponse:
    """Try image compatibility repair once, outside transient retries."""
    # Removing the user's images cannot repair account access.
    if (
        (response.error_kind or "").lower() in {"authentication", "oauth_auth_required", "unsupported_media"}
        or response.error_status_code in {401, 403}
        or is_billing_error(response)
    ):
        return response
    stripped = strip_image_content(kw["messages"])
    provider_context = kw.get("provider_context")
    stripped_context: ProviderCallContext | None = None
    if isinstance(provider_context, ProviderCallContext):
        state = provider_context.conversation_state
        if state is not None and (
            stripped is not None
            or strip_image_content(state.pending_messages) is not None
            or contains_image_content(state.payload)
        ):
            # Native payloads may retain images: rebuild from the public transcript.
            stripped_context = ProviderCallContext(
                context_window_tokens=provider_context.context_window_tokens,
                session_id=provider_context.session_id,
                events=provider_context.events,
                response_preset=provider_context.response_preset,
                response_is_fallback=provider_context.response_is_fallback,
            )
    if stripped is None and stripped_context is None:
        return response
    logger.warning("Non-transient LLM error with image content, retrying without images")
    retry_kw = dict(kw)
    if stripped is not None:
        retry_kw["messages"] = stripped
    if stripped_context is not None:
        retry_kw["provider_context"] = stripped_context
    result = await call(**retry_kw)
    # Keep later iterations from repeating the same image repair.
    if result.finish_reason != "error":
        strip_image_content_inplace(original_messages)
    return result
