"""Bounded and persistent retry execution over physical provider calls."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from cirno_core.bus.agent_events import (
    ResponseSource,
    ResponseSourceEvent,
    RetryStatusEvent,
    RetryWaitEvent,
)
from cirno_core.providers.contracts import (
    LLMResponse,
    ProviderCallContext,
    RetryEventCallback,
    RetryStatusCallback,
)
from cirno_core.providers.errors import (
    is_transient_response,
    public_error_kind,
    retry_after_response,
)
from cirno_core.providers.requests import retry_without_images
from loguru import logger

if TYPE_CHECKING:
    from cirno_core.providers.base import LLMProvider

RETRY_AFTER_BUFFER = 1


@dataclass
class ProviderRetryPolicy:
    delays: tuple[float, ...] = (1, 2, 4)
    persistent_max_delay: float = 60
    identical_error_limit: int = 10
    heartbeat_seconds: float = 30


class ProviderRetryExecutor:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def run(
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
        """Run one chat entry point through this provider's retry policy."""
        call = (
            self.provider.request_executor.stream
            if stream
            else self.provider.request_executor.complete
        )

        async def attributed_call(**kwargs: Any) -> LLMResponse:
            context = kwargs.get("provider_context")
            if (
                not isinstance(context, ProviderCallContext)
                or context.response_preset is None
                or not context.events.accepts(ResponseSourceEvent)
            ):
                return await call(**kwargs)
            source = (
                ResponseSource(
                    provider=self.provider.provider_name,
                    model=kwargs.get("model") or self.provider.get_default_model(),
                    preset=context.response_preset,
                    fallback=context.response_is_fallback,
                )
                if context.response_preset
                else None
            )
            await context.events.emit(ResponseSourceEvent(None))
            delta_callback = kwargs.get("on_content_delta")
            source_sent = False

            async def attributed_delta(text: str) -> None:
                nonlocal source_sent
                if text and not source_sent:
                    await context.events.emit(ResponseSourceEvent(source))
                    source_sent = True
                if delta_callback is not None:
                    await delta_callback(text)

            if delta_callback is not None:
                kwargs["on_content_delta"] = attributed_delta
            response = await call(**kwargs)
            await context.events.emit(
                ResponseSourceEvent(
                    source if response.finish_reason != "error" and response.content else None,
                    content=response.content if response.finish_reason != "error" else None,
                )
            )
            return response

        return await self.attempts(
            attributed_call,
            kw,
            original_messages,
            retry_mode=retry_mode,
            on_retry_wait=on_retry_wait,
            on_retry_exhausted=on_retry_exhausted,
            on_retry_status=on_retry_status,
            should_retry_guard=should_retry_guard,
            on_stream_recover=on_stream_recover,
        )

    async def attempts(
        self,
        call: Callable[..., Awaitable[LLMResponse]],
        kw: dict[str, Any],
        original_messages: list[dict[str, Any]],
        *,
        retry_mode: str,
        on_retry_wait: RetryEventCallback | None,
        on_retry_exhausted: RetryEventCallback | None,
        on_retry_status: RetryStatusCallback | None,
        should_retry_guard: Callable[[], bool] | None = None,
        on_stream_recover: Callable[[], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        response = await call(**kw)
        if response.finish_reason != "error":
            return response

        attempt = 1
        delays = self.provider.retry_policy.delays
        persistent = retry_mode == "persistent"
        max_attempts = None if persistent else len(delays) + 1
        last_error_key: str | None = None
        identical_error_count = 0

        async def _finish_retry_status(
            state: Literal["recovered", "cleared", "exhausted"],
            result: LLMResponse,
        ) -> None:
            if on_retry_status and (attempt > 1 or state == "exhausted"):
                await on_retry_status(
                    RetryStatusEvent(
                        state=state,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        error_kind=public_error_kind(result),
                    )
                )

        while True:
            if should_retry_guard is not None and not should_retry_guard():
                recoverable_stream = (
                    (response.error_kind or "").lower() in {"timeout", "invalid_response"}
                    and is_transient_response(response)
                )
                if recoverable_stream:
                    if on_stream_recover:
                        logger.warning(
                            "LLM stream interrupted after content was emitted; "
                            "starting a new stream segment and retrying"
                        )
                        await on_stream_recover()
                    else:
                        logger.warning(
                            "LLM stream interrupted after content was emitted; "
                            "suppressing delta callbacks and retrying"
                        )
                        kw["on_content_delta"] = None
                        kw["on_thinking_delta"] = None
                        kw["on_tool_call_delta"] = None
                        should_retry_guard = None
                else:
                    logger.warning("LLM stream failed after content was emitted; skipping retry")
                    await _finish_retry_status("cleared", response)
                    return response
            error_key = (response.content or "").strip().lower() or None
            if error_key and error_key == last_error_key:
                identical_error_count += 1
            else:
                last_error_key = error_key
                identical_error_count = 1 if error_key else 0

            if not is_transient_response(response):
                response = await retry_without_images(
                    call,
                    kw,
                    original_messages,
                    response,
                )
                await _finish_retry_status(
                    "recovered" if response.finish_reason != "error" else "cleared",
                    response,
                )
                return response

            if (
                persistent
                and identical_error_count >= self.provider.retry_policy.identical_error_limit
                or not persistent
                and attempt > len(delays)
            ):
                break

            retry_after = retry_after_response(response)
            base_delay = delays[min(attempt - 1, len(delays) - 1)]
            delay = (
                retry_after + RETRY_AFTER_BUFFER
                if retry_after
                else random.uniform(base_delay / 2, base_delay)
            )
            if persistent:
                delay = min(delay, self.provider.retry_policy.persistent_max_delay)
            logger.warning(
                "LLM transient error (attempt {}{}), retrying in {}s: {}",
                attempt,
                "+" if persistent and attempt > len(delays) else f"/{len(delays)}",
                int(round(delay)),
                (response.content or "")[:120].lower(),
            )
            await self.wait(
                delay,
                attempt=attempt,
                persistent=persistent,
                error_kind=public_error_kind(response),
                max_attempts=max_attempts,
                on_retry_wait=on_retry_wait,
                on_retry_status=on_retry_status,
            )
            attempt += 1
            response = await call(**kw)
            if response.finish_reason != "error":
                await _finish_retry_status("recovered", response)
                return response

        if persistent:
            logger.warning(
                "Stopping persistent retry after {} identical transient errors: {}",
                identical_error_count,
                (response.content or "")[:120].lower(),
            )
            exhausted_message = (
                f"Persistent retry stopped after {identical_error_count} identical errors."
            )
        else:
            logger.warning(
                "LLM request failed after {} attempts, giving up: {}",
                attempt,
                (response.content or "")[:120].lower(),
            )
            exhausted_message = f"Model request failed after {attempt} attempts, giving up."
        if on_retry_exhausted:
            await on_retry_exhausted(exhausted_message)
        await _finish_retry_status("exhausted", response)
        return response

    async def wait(
        self,
        delay: float,
        *,
        attempt: int,
        persistent: bool,
        error_kind: str,
        max_attempts: int | None,
        on_retry_wait: RetryEventCallback | None = None,
        on_retry_status: RetryStatusCallback | None = None,
    ) -> None:
        next_retry_at = time.time() + max(0.0, delay)
        remaining = max(0.0, delay)
        while remaining > 0:
            if on_retry_wait:
                kind = "persistent retry" if persistent else "retry"
                await on_retry_wait(
                    f"Model request failed, {kind} in {max(1, int(round(remaining)))}s "
                    f"(attempt {attempt})."
                )
            if on_retry_status:
                await on_retry_status(
                    RetryStatusEvent(
                        state="waiting",
                        attempt=attempt,
                        max_attempts=max_attempts,
                        error_kind=error_kind,
                        next_retry_at=next_retry_at,
                    )
                )
            chunk = min(remaining, self.provider.retry_policy.heartbeat_seconds)
            await asyncio.sleep(chunk)
            remaining -= chunk


async def notifications_for_retry(
    context: ProviderCallContext | None,
    on_wait: RetryEventCallback | None,
    on_exhausted: RetryEventCallback | None,
    on_status: RetryStatusCallback | None,
) -> tuple[RetryEventCallback | None, RetryEventCallback | None, RetryStatusCallback | None]:
    """Adapt once at the retry-chain boundary, before candidate callbacks.

    Explicit callbacks retain precedence. In particular a fallback candidate
    exhaustion callback captures its result; it must not also notify the UI.
    """
    if on_wait is None and context is not None and context.events.publish is not None:

        async def publish(content: str) -> None:
            await context.events.emit(RetryWaitEvent(content))

        on_wait = publish
    if on_status is None and context is not None and context.events.accepts(RetryStatusEvent):
        on_status = context.events.emit
        # A turn may continue after an exhausted request; the new chain owns
        # its own retry state, including when its first attempt is terminal.
        await on_status(RetryStatusEvent("cleared", 1, None, "unknown"))
    return on_wait, on_exhausted or on_wait, on_status
