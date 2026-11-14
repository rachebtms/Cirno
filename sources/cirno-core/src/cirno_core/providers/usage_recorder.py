"""Physical model-call accounting and bounded asynchronous usage estimation."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, cast

from cirno_usage.types import LLMUsage
from cirno_core.providers.contracts import LLMCallObserver, LLMResponse
from cirno_core.providers.errors import public_error_kind
from cirno_core.utils.cancellation import shield_and_drain
from loguru import logger

if TYPE_CHECKING:
    from cirno_core.providers.base import LLMProvider


class ProviderUsageRecorder:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        self.observer: LLMCallObserver | None = None
        self._estimate_slots = asyncio.Semaphore(2)

    def _usage_for_call(
        self,
        response: LLMResponse,
        kwargs: dict[str, Any],
    ) -> LLMUsage | None:
        usage = response.usage
        if usage is None or usage.total_tokens == 0:
            if response.finish_reason in {"error", "cancelled"}:
                return None
            messages = kwargs.get("messages")
            if not isinstance(messages, list):
                return usage
            tools_value = kwargs.get("tools")
            tools = (
                cast(list[dict[str, Any]], tools_value) if isinstance(tools_value, list) else None
            )
            model_value = kwargs.get("model")
            model = (
                model_value if isinstance(model_value, str) else self.provider.get_default_model()
            )
            try:
                from cirno_core.utils.model_messages import build_assistant_message
                from cirno_core.utils.token_estimation import estimate_message_tokens, estimate_prompt_tokens_chain

                input_tokens, _ = estimate_prompt_tokens_chain(
                    self.provider,
                    model,
                    cast(list[dict[str, Any]], messages),
                    tools,
                )
                assistant_message = build_assistant_message(
                    response.content or "",
                    tool_calls=[call.to_openai_tool_call() for call in response.tool_calls],
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )
                usage = LLMUsage.estimated(
                    input_tokens=max(0, input_tokens),
                    output_tokens=max(0, estimate_message_tokens(assistant_message)),
                )
            except Exception:
                logger.exception("failed to estimate usage for {}", self.provider.provider_name)
                return usage
        return usage.with_timing(
            generation_ms=response.generation_ms,
            ttft_ms=response.ttft_ms,
        )

    def observe(
        self,
        response: LLMResponse,
        kwargs: dict[str, Any],
        *,
        started_at_ms: int,
        started_at_ns: int,
        stream: bool,
    ) -> LLMResponse:
        if response.finish_reason == "error":
            logger.warning(
                "Model request failed: provider={} model={} kind={} http_status={}",
                self.provider.provider_name,
                kwargs.get("model") or self.provider.get_default_model(),
                public_error_kind(response),
                response.error_status_code,
            )
        observer = self.observer
        if observer is None:
            return response
        finished_at_ns = time.monotonic_ns()
        usage = self._usage_for_call(response, kwargs)
        return self._record_llm_call(
            response,
            kwargs,
            observer=observer,
            usage=usage,
            started_at_ms=started_at_ms,
            started_at_ns=started_at_ns,
            finished_at_ns=finished_at_ns,
            stream=stream,
        )

    async def observe_async(
        self,
        response: LLMResponse,
        kwargs: dict[str, Any],
        *,
        started_at_ms: int,
        started_at_ns: int,
        stream: bool,
    ) -> LLMResponse:
        observer = self.observer
        if (
            observer is None
            or response.finish_reason in {"error", "cancelled"}
            or (response.usage is not None and response.usage.total_tokens > 0)
        ):
            return self.observe(
                response,
                kwargs,
                started_at_ms=started_at_ms,
                started_at_ns=started_at_ns,
                stream=stream,
            )
        finished_at_ns = time.monotonic_ns()

        async def observe() -> LLMResponse:
            async with self._estimate_slots:
                usage = await asyncio.to_thread(self._usage_for_call, response, kwargs)
            return self._record_llm_call(
                response,
                kwargs,
                observer=observer,
                usage=usage,
                started_at_ms=started_at_ms,
                started_at_ns=started_at_ns,
                finished_at_ns=finished_at_ns,
                stream=stream,
            )

        # Once the request completes, settle its usage and observer before cancellation.
        return await shield_and_drain(observe())

    def _record_llm_call(
        self,
        response: LLMResponse,
        kwargs: dict[str, Any],
        *,
        observer: LLMCallObserver,
        usage: LLMUsage | None,
        started_at_ms: int,
        started_at_ns: int,
        finished_at_ns: int,
        stream: bool,
    ) -> LLMResponse:
        if usage is not None:
            response.usage = usage
        model_value = kwargs.get("model")
        model = (
            model_value
            if isinstance(model_value, str) and model_value
            else self.provider.get_default_model()
        )
        try:
            from cirno_usage.context import current_llm_usage_source
            from cirno_usage.models import LLMCallRecord

            observer(
                LLMCallRecord(
                    started_at_ms=started_at_ms,
                    duration_ms=max(0, (finished_at_ns - started_at_ns) // 1_000_000),
                    provider=self.provider.provider_name,
                    model=model,
                    source=current_llm_usage_source(),
                    stream=stream,
                    finish_reason=response.finish_reason,
                    usage=usage,
                    error_status_code=response.error_status_code,
                    error_kind=response.error_kind,
                )
            )
        except Exception:
            logger.exception("LLM call observer failed for {}", self.provider.provider_name)
        return response
