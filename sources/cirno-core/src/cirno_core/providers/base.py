"""Base LLM provider interface."""

from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any, cast

from cirno_core.providers.contracts import (
    LLMCallObserver,
    LLMResponse,
    ProviderCallContext,
    ProviderConversationState,
    RetryEventCallback,
    RetryStatusCallback,
)
from cirno_core.providers.generation import GenerationSettings
from cirno_core.providers.media_capabilities import MediaCapabilities
from cirno_core.providers.context_budget import CONTEXT_SAFETY_BUFFER as CONTEXT_SAFETY_BUFFER
from cirno_core.providers.requests import ProviderRequestExecutor
from cirno_core.providers.retry import (
    ProviderRetryExecutor,
    ProviderRetryPolicy,
    notifications_for_retry,
)
from cirno_core.providers.timeouts import ProviderTimeouts
from cirno_core.providers.usage_recorder import ProviderUsageRecorder

class LLMProvider(ABC):
    """Base class for LLM providers."""

    reasoning_history: str = "auto"

    retry_policy = ProviderRetryPolicy()

    _SENTINEL = object()

    media_capabilities = MediaCapabilities()

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        *,
        provider_name: str,
    ):
        runtime_provider_name = cast(object, provider_name)
        if not isinstance(runtime_provider_name, str) or not runtime_provider_name.strip():
            raise ValueError("provider_name must be a non-empty configured identity")
        self.api_key = api_key
        self.api_base = api_base
        self.provider_name = provider_name
        self.retry_policy = replace(self.retry_policy)
        configured_retries = os.environ.get("CIRNO_PROVIDER_MAX_RETRIES")
        if configured_retries is not None:
            retries = int(configured_retries)
            if retries < 3:
                raise ValueError("CIRNO_PROVIDER_MAX_RETRIES must be at least 3")
            self.retry_policy.delays = tuple(min(2**attempt, 60) for attempt in range(retries))
        self.timeouts = ProviderTimeouts()
        self.generation: GenerationSettings = GenerationSettings()
        self.usage_recorder = ProviderUsageRecorder(self)
        self.request_executor = ProviderRequestExecutor(self)
        self.retry_executor = ProviderRetryExecutor(self)

    @property
    def request_timeout_s(self) -> float:
        return self.timeouts.request_s

    @request_timeout_s.setter
    def request_timeout_s(self, seconds: float) -> None:
        self.timeouts.request_s = seconds

    @property
    def stream_idle_timeout_s(self) -> float:
        return self.timeouts.stream_idle_s

    @stream_idle_timeout_s.setter
    def stream_idle_timeout_s(self, seconds: float) -> None:
        self.timeouts.stream_idle_s = seconds

    def set_llm_call_observer(self, observer: LLMCallObserver | None) -> None:
        """Attach a fail-open observer for each physical retry-managed call."""
        self.usage_recorder.observer = observer

    def can_resume_conversation_state(
        self,
        state: ProviderConversationState,
        model: str | None = None,
    ) -> bool:
        """Whether this provider can safely consume an opaque saved state."""
        return False

    def supports_native_compaction(self, model: str | None = None) -> bool:
        """Whether requests may include provider-native context compaction."""
        return False

    def supports_pre_request_compaction(self, model: str | None = None) -> bool:
        """Whether the provider enforces compaction_input_budget before generation."""
        return False

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        """
        Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            tools: Optional list of tool definitions.
            model: Model identifier (provider-specific).
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.
            tool_choice: Tool selection strategy ("auto", "required", or specific tool dict).

        Returns:
            LLMResponse with content and/or tool calls.
        """
        pass

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
        on_thinking_delta: Callable[[str], Awaitable[None]] | None = None,
        on_tool_call_delta: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        """Stream a chat completion, calling *on_content_delta* for each text chunk.

        *on_thinking_delta* is reserved for providers that expose incremental
        thinking/reasoning on the wire; the default fallback invokes neither
        callback for native deltas (only the optional single *on_content_delta*
        after :meth:`chat`).

        Returns the same ``LLMResponse`` as :meth:`chat`.  The default
        implementation falls back to a non-streaming call and delivers the
        full content as a single delta.  Providers that support native
        streaming should override this method.
        """
        _ = on_thinking_delta, on_tool_call_delta
        response = await asyncio.wait_for(
            self.chat(
                messages=messages,
                tools=tools,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
                tool_choice=tool_choice,
            ),
            timeout=self.stream_idle_timeout_s,
        )
        if on_content_delta and response.content and response.finish_reason != "error":
            await on_content_delta(response.content)
        return response

    async def chat_with_context(
        self,
        *,
        provider_context: ProviderCallContext,
        **kwargs: Any,
    ) -> LLMResponse:
        """Opt-in continuation hook; ordinary providers delegate to ``chat``."""
        _ = provider_context
        return await self.chat(**kwargs)

    async def chat_stream_with_context(
        self,
        *,
        provider_context: ProviderCallContext,
        **kwargs: Any,
    ) -> LLMResponse:
        """Streaming continuation hook with a context-free default."""
        _ = provider_context
        return await self.chat_stream(**kwargs)

    async def chat_stream_with_retry(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: object = _SENTINEL,
        temperature: object = _SENTINEL,
        reasoning_effort: object = _SENTINEL,
        tool_choice: str | dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
        on_thinking_delta: Callable[[str], Awaitable[None]] | None = None,
        on_tool_call_delta: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        on_stream_recover: Callable[[], Awaitable[None]] | None = None,
        retry_mode: str = "standard",
        on_retry_wait: RetryEventCallback | None = None,
        provider_context: ProviderCallContext | None = None,
        on_retry_exhausted: RetryEventCallback | None = None,
        on_retry_status: RetryStatusCallback | None = None,
    ) -> LLMResponse:
        """Call chat_stream() with retry on transient provider failures."""
        if max_tokens is self._SENTINEL or max_tokens is None:
            max_tokens = self.generation.max_tokens
        if temperature is self._SENTINEL or temperature is None:
            temperature = self.generation.temperature
        if reasoning_effort is self._SENTINEL:
            reasoning_effort = self.generation.reasoning_effort

        has_streamed_content = False

        async def _tracking_delta(text: str) -> None:
            nonlocal has_streamed_content
            if text:
                has_streamed_content = True
            if on_content_delta:
                await on_content_delta(text)

        async def _recover_stream() -> None:
            nonlocal has_streamed_content
            if on_stream_recover:
                await on_stream_recover()
            has_streamed_content = False

        kw: dict[str, Any] = dict(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
            on_content_delta=_tracking_delta if on_content_delta is not None else None,
            on_thinking_delta=on_thinking_delta,
            on_tool_call_delta=on_tool_call_delta,
        )
        if provider_context is not None:
            kw["provider_context"] = provider_context
        if on_stream_recover and getattr(self, "supports_stream_recover_callback", False):
            kw["on_stream_recover"] = _recover_stream
        on_retry_wait, on_retry_exhausted, on_retry_status = await notifications_for_retry(
            provider_context,
            on_retry_wait,
            on_retry_exhausted,
            on_retry_status,
        )
        return await self._run_chat_with_retry(
            kw,
            messages,
            stream=True,
            retry_mode=retry_mode,
            on_retry_wait=on_retry_wait,
            on_retry_exhausted=on_retry_exhausted,
            on_retry_status=on_retry_status,
            should_retry_guard=lambda: not has_streamed_content,
            on_stream_recover=_recover_stream if on_stream_recover else None,
        )

    async def chat_with_retry(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: object = _SENTINEL,
        temperature: object = _SENTINEL,
        reasoning_effort: object = _SENTINEL,
        tool_choice: str | dict[str, Any] | None = None,
        retry_mode: str = "standard",
        on_retry_wait: RetryEventCallback | None = None,
        provider_context: ProviderCallContext | None = None,
        on_retry_exhausted: RetryEventCallback | None = None,
        on_retry_status: RetryStatusCallback | None = None,
    ) -> LLMResponse:
        """Call chat() with retry on transient provider failures.

        Parameters default to ``self.generation`` when not explicitly passed,
        so callers no longer need to thread temperature / max_tokens /
        reasoning_effort through every layer. Explicit ``None`` is also
        normalized to the provider's generation defaults so that downstream
        ``_build_kwargs`` never sees ``None`` for ``max_tokens`` / ``temperature``
        (which would crash ``max(1, max_tokens)``).
        """
        if max_tokens is self._SENTINEL or max_tokens is None:
            max_tokens = self.generation.max_tokens
        if temperature is self._SENTINEL or temperature is None:
            temperature = self.generation.temperature
        if reasoning_effort is self._SENTINEL:
            reasoning_effort = self.generation.reasoning_effort

        kw: dict[str, Any] = dict(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
        )
        if provider_context is not None:
            kw["provider_context"] = provider_context
        on_retry_wait, on_retry_exhausted, on_retry_status = await notifications_for_retry(
            provider_context,
            on_retry_wait,
            on_retry_exhausted,
            on_retry_status,
        )
        return await self._run_chat_with_retry(
            kw,
            messages,
            stream=False,
            retry_mode=retry_mode,
            on_retry_wait=on_retry_wait,
            on_retry_exhausted=on_retry_exhausted,
            on_retry_status=on_retry_status,
        )

    async def _run_chat_with_retry(
        self,
        kw: dict[str, Any],
        original_messages: list[dict[str, Any]],
        *,
        stream: bool,
        retry_mode: str,
        on_retry_wait: RetryEventCallback | None,
        on_retry_exhausted: RetryEventCallback | None,
        on_retry_status: RetryStatusCallback | None,
        should_retry_guard: Callable[[], bool] | None = None,
        on_stream_recover: Callable[[], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        """Execute the selected provider policy; fallback providers override the chain."""
        return await self.retry_executor.run(
            kw,
            original_messages,
            stream=stream,
            retry_mode=retry_mode,
            on_retry_wait=on_retry_wait,
            on_retry_exhausted=on_retry_exhausted,
            on_retry_status=on_retry_status,
            should_retry_guard=should_retry_guard,
            on_stream_recover=on_stream_recover,
        )

    async def aclose(self) -> None:
        """Close provider-owned transports after their active requests have stopped."""

    @abstractmethod
    def get_default_model(self) -> str:
        """Get the default model for this provider."""
        pass
