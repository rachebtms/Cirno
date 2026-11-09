"""Shared provider for OpenAI-compatible Chat Completions and Responses APIs."""

# pyright: reportPrivateImportUsage=false

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

from cirno_core.providers.base import LLMProvider
from cirno_core.providers.chat_completions.complete import parse_response
from cirno_core.providers.chat_completions.errors import error_response
from cirno_core.providers.chat_completions.generation import (
    supports_temperature,
)
from cirno_core.providers.chat_completions.history import sanitize_messages
from cirno_core.providers.chat_completions.request import build_chat_request
from cirno_core.providers.chat_completions.streaming import ChatStreamAccumulator
from cirno_core.providers.contracts import (
    LLMResponse,
    ProviderCallContext,
    ProviderConversationState,
)
from cirno_core.providers.endpoints import (
    is_local_endpoint,
    uses_opencode_affinity,
    uses_openrouter_attribution,
)
from cirno_core.providers.images import prepare_inline_images
from cirno_core.providers.messages import (
    sanitize_empty_content,
)
from cirno_core.providers.model_api import (
    ModelAPICapabilities,
    ResponsesCapabilities,
    hosted_web_search_enabled,
    is_direct_openai_base,
    is_hosted_web_search_tool,
)
from cirno_core.providers.openai_responses import ResponsesBackend, responses_state_matches
from cirno_core.providers.reasoning_history import prepare_reasoning_history
from cirno_core.providers.request_bodies import merge_responses_extra_body
from cirno_core.utils.cancellation import shield_and_drain
from loguru import logger

if TYPE_CHECKING:
    from cirno_core.providers.catalog.contracts import ProviderSpec
    from openai import AsyncOpenAI as AsyncOpenAIType

# Module-level placeholder — set lazily by _ensure_client on first real
# use, or replaced by tests via ``patch(...)``.  Kept as a plain name so
# that ``unittest.mock.patch`` can find and replace it.
AsyncOpenAI: Any = None


def _is_named_function_tool(tool: object, name: str) -> bool:
    """Return whether a Responses tool is a function with the given name."""
    if not isinstance(tool, dict):
        return False
    record = cast(dict[object, object], tool)
    if record.get("type") != "function":
        return False
    function = record.get("function")
    if isinstance(function, dict):
        return cast(dict[object, object], function).get("name") == name
    return record.get("name") == name


_DEFAULT_OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://github.com/rachebtms/Cirno",
    "X-OpenRouter-Title": "cirno",
    "X-OpenRouter-Categories": "cli-agent,personal-agent",
}
_OPENAI_COMPAT_REQUEST_TIMEOUT_S = 120.0


def _openai_compat_timeout_s() -> float:
    """Return the bounded request timeout used for OpenAI-compatible providers."""
    return _float_env("CIRNO_OPENAI_COMPAT_TIMEOUT_S", _OPENAI_COMPAT_REQUEST_TIMEOUT_S)


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning("Ignoring invalid {}={!r}; using {}", name, raw, default)
        return default
    if not math.isfinite(value) or value <= 0:
        logger.warning("Ignoring non-finite or non-positive {}={!r}; using {}", name, raw, default)
        return default
    return value


_RESPONSES_FAILURE_THRESHOLD = 3
_RESPONSES_PROBE_INTERVAL_S = 300  # 5 minutes


def _responses_circuit_key(
    model: str | None,
    default_model: str,
    reasoning_effort: str | None,
) -> str:
    model_name = (model or default_model).lower()
    effort = reasoning_effort.lower() if isinstance(reasoning_effort, str) else ""
    return f"{model_name}:{effort}"


class OpenAICompatProvider(LLMProvider):
    """Provider for OpenAI-compatible Chat Completions and Responses endpoints.

    Receives a resolved ``ProviderSpec`` from the caller — no internal
    registry lookups needed.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "gpt-4o",
        extra_headers: dict[str, str] | None = None,
        spec: ProviderSpec | None = None,
        extra_body: dict[str, Any] | None = None,
        model_api: ModelAPICapabilities | None = None,
        extra_query: dict[str, str] | None = None,
        proxy: str | None = None,
        provider_name: str = "openai",
    ):
        super().__init__(api_key, api_base, provider_name=provider_name)
        self.default_model = default_model
        self.extra_headers = extra_headers or {}
        self._spec = spec
        self._preset_model_api = model_api
        self._extra_body = (
            spec.responses.request_extra_body(extra_body)
            if spec and spec.responses is not None
            else dict(extra_body or {})
        )
        self._extra_query = extra_query or {}
        self._proxy = proxy or None
        self.request_timeout_s = _openai_compat_timeout_s()
        self._responses = ResponsesBackend(timeouts=self.timeouts)

        effective_base = api_base or (spec.default_api_base if spec else None) or None
        self._effective_base = effective_base
        self._default_headers = {"x-session-affinity": uuid.uuid4().hex}
        if uses_openrouter_attribution(spec, effective_base):
            self._default_headers.update(_DEFAULT_OPENROUTER_HEADERS)
        if extra_headers:
            self._default_headers.update(extra_headers)
        self._opencode_session_affinity = uses_opencode_affinity(spec, effective_base) and not any(
            name.lower() == "x-opencode-session" for name in self.extra_headers
        )
        if self._opencode_session_affinity:
            # Calls without conversation context still need a stable routing header.
            self._default_headers["x-opencode-session"] = uuid.uuid4().hex
        self._api_key_for_client = api_key or "no-key"
        self._is_local = is_local_endpoint(spec, effective_base)

        # Lazy-init: the OpenAI client and its httpx transport are expensive
        # to create (~700 ms on Windows). Defer until first use.
        self._client: AsyncOpenAIType | None = None
        self._client_lock = asyncio.Lock()

        # Responses API circuit breaker: skip after repeated failures,
        # probe again after _RESPONSES_PROBE_INTERVAL_S seconds.
        self._responses_failures: dict[str, int] = {}
        self._responses_tripped_at: dict[str, float] = {}

    def _build_client(self) -> None:
        """Create the OpenAI client using the current module-level AsyncOpenAI."""
        import httpx

        timeout_s = self.request_timeout_s
        http_client: httpx.AsyncClient | None = None
        if self._proxy:
            http_client = httpx.AsyncClient(
                timeout=timeout_s,
                proxy=self._proxy,
                trust_env=False,
                follow_redirects=True,
            )
        elif self._is_local:
            # Local model servers (Ollama, llama.cpp, vLLM) often close idle
            # HTTP connections before the client-side keepalive expires. When
            # two LLM calls happen seconds apart, the second may grab a dead
            # pooled connection, causing a transient APIConnectionError on every first
            # attempt. Disabling keepalive for local endpoints avoids this by
            # opening a fresh connection for each request, which is cheap on a
            # LAN. Cloud providers benefit from keepalive, so we leave the
            # default pool settings for them.
            #
            # Also disable proxy for local endpoints: when the host has
            # HTTP_PROXY / HTTPS_PROXY / ALL_PROXY set, httpx would try to
            # route local traffic through the proxy, which typically cannot
            # reach localhost or LAN addresses.
            _local_limits = httpx.Limits(keepalive_expiry=0)
            http_client = httpx.AsyncClient(
                limits=_local_limits,
                timeout=timeout_s,
                transport=httpx.AsyncHTTPTransport(proxy=None, limits=_local_limits),
            )
        else:
            http_client = httpx.AsyncClient(
                timeout=timeout_s,
                trust_env=False,
                follow_redirects=True,
            )
        self._client = AsyncOpenAI(
            api_key=self._api_key_for_client,
            base_url=self._effective_base,
            default_headers=self._default_headers,
            default_query=self._extra_query or None,
            max_retries=0,
            timeout=timeout_s,
            http_client=http_client,
        )

    async def _ensure_client(self) -> AsyncOpenAIType:
        """Return the shared OpenAI client, creating it on first call."""
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is not None:
                return self._client
            global AsyncOpenAI
            if AsyncOpenAI is None:
                from openai import AsyncOpenAI as _AsyncOpenAI

                AsyncOpenAI = _AsyncOpenAI

            self._build_client()
            if self._client is None:
                raise RuntimeError("OpenAI client initialization did not produce a client")
            return self._client

    async def aclose(self) -> None:
        try:
            await self._responses.aclose()
        finally:
            client, self._client = self._client, None
            if client is not None:
                await client.close()

    # ------------------------------------------------------------------
    # Build kwargs
    # ------------------------------------------------------------------

    def prepare_messages(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        prepared = prepare_reasoning_history(self, messages, tools=tools)
        return sanitize_messages(prepared, spec=self._spec, model=model or self.default_model)

    def _request_model_name(self, model_name: str) -> str:
        return self._spec.request_model_name(model_name) if self._spec else model_name

    def _opencode_affinity_headers(
        self,
        provider_context: "ProviderCallContext | None",
    ) -> dict[str, str] | None:
        """Override the instance fallback with an opaque, ASCII-safe conversation key."""
        if (
            not self._opencode_session_affinity
            or provider_context is None
            or not provider_context.session_id
        ):
            return None
        session_key = hashlib.sha256(provider_context.session_id.encode("utf-8")).hexdigest()
        return {"x-opencode-session": session_key}

    def _build_kwargs(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str | None,
        max_tokens: int,
        temperature: float,
        reasoning_effort: str | None,
        tool_choice: str | dict[str, Any] | None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return build_chat_request(
            messages,
            tools,
            model,
            max_tokens,
            temperature,
            reasoning_effort,
            tool_choice,
            extra_headers,
            default_model=self.default_model,
            spec=self._spec,
            extra_body=self._extra_body,
            prepare_messages=self.prepare_messages,
        )

    def _should_use_responses_api(
        self,
        model: str | None,
        reasoning_effort: str | None,
    ) -> bool:
        """Choose Responses for providers/models that explicitly support it."""
        api = self._model_api_capabilities(model, reasoning_effort)
        if self._hosted_web_search_enabled() and "responses" in api.supported_apis:
            return True
        if api.preferred_api != "responses":
            return False
        if self._responses_is_required(model, reasoning_effort):
            return True
        return self._responses_circuit_allows_probe(model, reasoning_effort)

    def _model_api_capabilities(
        self,
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> ModelAPICapabilities:
        """Apply a preset's declaration before the provider's curated defaults."""
        if self._preset_model_api is not None:
            return self._preset_model_api
        if self._spec is None:
            return ModelAPICapabilities()
        return self._spec.default_model_api(
            model or self.default_model,
            reasoning_effort,
            api_base=self._effective_base,
            extra_body=self._extra_body,
        )

    def _responses_is_required(
        self,
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> bool:
        api = self._model_api_capabilities(model, reasoning_effort)
        return "chat_completions" not in api.supported_apis or self._hosted_web_search_enabled()

    def _hosted_web_search_enabled(self) -> bool:
        return hosted_web_search_enabled(self._extra_body)

    def _responses_capabilities(self) -> ResponsesCapabilities | None:
        capabilities = self._spec.responses if self._spec is not None else None
        if capabilities is not None:
            return capabilities
        if (
            self._preset_model_api is not None
            and "responses" in self._preset_model_api.supported_apis
        ):
            return ResponsesCapabilities()
        return None

    def _responses_state_provider(self) -> str:
        spec_name = self._spec.name if self._spec is not None else "custom"
        effective_base = self._effective_base or "https://api.openai.com/v1"
        return f"openai_compat:{spec_name}:{effective_base.rstrip('/')}"

    def _responses_state_model(self, model: str | None) -> str:
        return self._request_model_name(model or self.default_model)

    def can_resume_conversation_state(
        self,
        state: ProviderConversationState,
        model: str | None = None,
    ) -> bool:
        return responses_state_matches(
            state,
            provider=self._responses_state_provider(),
            model=self._responses_state_model(model),
        )

    def supports_native_compaction(self, model: str | None = None) -> bool:
        """Enable server compaction only on direct OpenAI Responses endpoints."""
        capabilities = self._responses_capabilities()
        if (
            not self._responses.native_compaction_available
            or capabilities is None
            or not capabilities.supports_native_compaction
        ):
            return False
        if self._preset_model_api is not None:
            if "responses" not in self._preset_model_api.supported_apis:
                return False
            if (
                self._preset_model_api.preferred_api != "responses"
                and not self._hosted_web_search_enabled()
            ):
                return False
        if capabilities.requires_direct_openai_base and not is_direct_openai_base(
            self._effective_base
        ):
            return False
        return True

    def _responses_circuit_allows_probe(
        self,
        model: str | None,
        reasoning_effort: str | None,
    ) -> bool:
        """Return False when the Responses API circuit breaker is open."""
        key = _responses_circuit_key(model, self.default_model, reasoning_effort)
        failures = self._responses_failures.get(key, 0)
        if failures >= _RESPONSES_FAILURE_THRESHOLD:
            tripped = self._responses_tripped_at.get(key, 0.0)
            if (time.monotonic() - tripped) < _RESPONSES_PROBE_INTERVAL_S:
                return False
            # Half-open: allow one probe attempt
        return True

    def _record_responses_failure(self, model: str | None, reasoning_effort: str | None) -> None:
        key = _responses_circuit_key(model, self.default_model, reasoning_effort)
        count = self._responses_failures.get(key, 0) + 1
        self._responses_failures[key] = count
        if count >= _RESPONSES_FAILURE_THRESHOLD:
            self._responses_tripped_at[key] = time.monotonic()
            logger.warning(
                "Responses API circuit open for {} — falling back to Chat Completions",
                key,
            )

    def _record_responses_success(self, model: str | None, reasoning_effort: str | None) -> None:
        key = _responses_circuit_key(model, self.default_model, reasoning_effort)
        self._responses_failures.pop(key, None)
        self._responses_tripped_at.pop(key, None)

    @staticmethod
    def _should_fallback_from_responses_error(e: Exception) -> bool:
        """Fallback only for likely Responses API compatibility errors."""
        response = getattr(e, "response", None)
        status_code = getattr(e, "status_code", None)
        if status_code is None and response is not None:
            status_code = getattr(response, "status_code", None)
        if status_code not in {400, 404, 422}:
            return False

        body = (
            getattr(e, "body", None) or getattr(e, "doc", None) or getattr(response, "text", None)
        )
        body_text = str(body).lower() if body is not None else ""
        compatibility_markers = (
            "responses",
            "response api",
            "max_output_tokens",
            "instructions",
            "previous_response",
            "unsupported",
            "not supported",
            "unknown parameter",
            "unrecognized request argument",
        )
        return any(marker in body_text for marker in compatibility_markers)

    def _build_responses_body(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str | None,
        max_tokens: int,
        temperature: float,
        reasoning_effort: str | None,
        tool_choice: str | dict[str, Any] | None,
        provider_context: ProviderCallContext | None = None,
    ) -> dict[str, Any]:
        """Build a Responses API body for direct OpenAI requests."""
        model_name = model or self.default_model
        model_name = self._request_model_name(model_name)
        sanitized_messages = self.prepare_messages(
            sanitize_empty_content(messages),
            model_name,
            tools=tools,
        )
        sanitized_state = (
            provider_context.conversation_state if provider_context is not None else None
        )
        if sanitized_state is not None:
            sanitized_state = sanitized_state.with_pending_messages(
                self.prepare_messages(
                    sanitize_empty_content(sanitized_state.pending_messages),
                    model_name,
                    tools=tools,
                )
            )
        supports_reasoning_none = bool(
            self._spec and self._spec.name in {"deepseek", "xiaomi_mimo"}
        )
        capabilities = self._responses_capabilities()
        preserve_reasoning = (
            capabilities is not None and capabilities.reasoning_replay == "plaintext"
        )
        prepared = self._responses.prepare(
            sanitized_messages,
            state=sanitized_state,
            provider=self._responses_state_provider(),
            model=model_name,
            tools=tools,
            tool_choice=tool_choice,
            preserve_reasoning=preserve_reasoning,
        )
        body = prepared.body
        body["max_output_tokens"] = max(1, max_tokens)
        if self.supports_native_compaction(model_name):
            self._responses.add_compaction(
                body,
                provider_context.context_window_tokens if provider_context else None,
                max_tokens,
                output_reserve_percent=provider_context.output_reserve_percent if provider_context else 5,
            )

        temperature_supported = supports_temperature(model_name, reasoning_effort)
        if temperature_supported:
            body["temperature"] = temperature

        reasoning_enabled = bool(reasoning_effort and reasoning_effort.lower() != "none")
        if (
            (not temperature_supported or reasoning_enabled)
            and capabilities is not None
            and capabilities.reasoning_replay == "encrypted"
        ):
            body["include"] = ["reasoning.encrypted_content"]
        if reasoning_effort and (reasoning_effort.lower() != "none" or supports_reasoning_none):
            body["reasoning"] = {"effort": reasoning_effort}
        if prepared.replayed and "gpt-5.6" in model_name.lower():
            body.setdefault("reasoning", {})["context"] = "all_turns"

        extra_body = getattr(self, "_extra_body", {})
        if extra_body:
            body = merge_responses_extra_body(body, extra_body)

        if self._hosted_web_search_enabled():
            configured_tools = body.get("tools")
            if isinstance(configured_tools, list):
                managed_tools: list[object] = []
                hosted_search_seen = False
                for tool in cast(list[object], configured_tools):
                    if _is_named_function_tool(tool, "web_search"):
                        continue
                    if is_hosted_web_search_tool(tool):
                        if hosted_search_seen:
                            continue
                        hosted_search_seen = True
                    managed_tools.append(tool)
                body["tools"] = managed_tools
            if self._spec and self._spec.name == "openai":
                source_include = "web_search_call.action.sources"
                configured_include = body.get("include")
                if isinstance(configured_include, list):
                    if source_include not in configured_include:
                        body["include"] = [*configured_include, source_include]
                else:
                    body["include"] = [source_include]

        return body

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat_with_context(
        self,
        *,
        provider_context: ProviderCallContext,
        **kwargs: Any,
    ) -> LLMResponse:
        return await self.chat(
            **kwargs,
            provider_context=provider_context,
        )

    async def chat_stream_with_context(
        self,
        *,
        provider_context: ProviderCallContext,
        **kwargs: Any,
    ) -> LLMResponse:
        return await self.chat_stream(
            **kwargs,
            provider_context=provider_context,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        provider_context: ProviderCallContext | None = None,
    ) -> LLMResponse:
        client = await self._ensure_client()
        affinity = self._opencode_affinity_headers(provider_context)
        try:
            if self._should_use_responses_api(model, reasoning_effort):
                try:
                    body = self._build_responses_body(
                        messages,
                        tools,
                        model,
                        max_tokens,
                        temperature,
                        reasoning_effort,
                        tool_choice,
                        provider_context,
                    )
                    result = await self._responses.sdk_request(
                        client,
                        body,
                        provider=self._responses_state_provider(),
                        extra_headers=affinity,
                    )
                    self._record_responses_success(model, reasoning_effort)
                    return result
                except Exception as responses_error:
                    if self._responses_is_required(model, reasoning_effort):
                        raise
                    if not self._should_fallback_from_responses_error(responses_error):
                        raise
                    self._record_responses_failure(model, reasoning_effort)

            kwargs = self._build_kwargs(
                messages,
                tools,
                model,
                max_tokens,
                temperature,
                reasoning_effort,
                tool_choice,
                extra_headers=affinity,
            )
            kwargs = await prepare_inline_images(kwargs)
            chat_raw = cast(
                Any,
                await client.chat.completions.create(**kwargs),
            )
            return parse_response(chat_raw, spec=self._spec)
        except Exception as e:
            return error_response(e, spec=self._spec, api_base=self.api_base)

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
        provider_context: ProviderCallContext | None = None,
    ) -> LLMResponse:
        client = await self._ensure_client()
        idle_timeout_s = self.stream_idle_timeout_s
        affinity = self._opencode_affinity_headers(provider_context)
        try:
            if self._should_use_responses_api(model, reasoning_effort):
                try:
                    body = self._build_responses_body(
                        messages,
                        tools,
                        model,
                        max_tokens,
                        temperature,
                        reasoning_effort,
                        tool_choice,
                        provider_context,
                    )
                    body["stream"] = True
                    result = await self._responses.sdk_request(
                        client,
                        body,
                        provider=self._responses_state_provider(),
                        extra_headers=affinity,
                        on_content_delta=on_content_delta,
                        on_thinking_delta=on_thinking_delta,
                        on_tool_call_delta=on_tool_call_delta,
                    )
                    self._record_responses_success(model, reasoning_effort)
                    return result
                except Exception as responses_error:
                    if self._responses_is_required(model, reasoning_effort):
                        raise
                    if not self._should_fallback_from_responses_error(responses_error):
                        raise
                    self._record_responses_failure(model, reasoning_effort)

            kwargs = self._build_kwargs(
                messages,
                tools,
                model,
                max_tokens,
                temperature,
                reasoning_effort,
                tool_choice,
                extra_headers=affinity,
            )
            kwargs = await prepare_inline_images(kwargs)
            if self._spec and self._spec.name == "zhipu" and tools and on_tool_call_delta:
                # Z.AI/GLM keeps streaming tool-call arguments behind an
                # explicit provider flag.  Pass it through the OpenAI SDK's
                # extra_body escape hatch so the usual delta.tool_calls path
                # can surface live file-edit progress.
                kwargs.setdefault("extra_body", {})["tool_stream"] = True
            kwargs["stream"] = True
            kwargs["timeout"] = self.timeouts.httpx(stream=True)
            kwargs["stream_options"] = {"include_usage": True}
            chat_stream = cast(
                Any,
                await client.chat.completions.create(**kwargs),
            )
            accumulator = ChatStreamAccumulator()
            stream_iter: AsyncIterator[Any] = chat_stream.__aiter__()
            try:
                while True:
                    try:
                        chunk = await asyncio.wait_for(
                            stream_iter.__anext__(), timeout=idle_timeout_s
                        )
                    except StopAsyncIteration:
                        break
                    delta = accumulator.consume(chunk)
                    if delta.content and on_content_delta:
                        await on_content_delta(delta.content)
                    if delta.reasoning and on_thinking_delta:
                        await on_thinking_delta(delta.reasoning)
                    if on_tool_call_delta:
                        for call in delta.tool_calls:
                            await on_tool_call_delta(call)
                if not accumulator.completed:
                    raise ConnectionError("Model stream ended before a finish reason was received")
                return accumulator.response()
            finally:
                close = getattr(chat_stream, "close", None) or getattr(chat_stream, "aclose", None)
                if close is not None:
                    await shield_and_drain(close())
        except asyncio.TimeoutError:
            return LLMResponse(
                content=(
                    f"Error calling LLM: stream stalled for more than {idle_timeout_s:g} seconds"
                ),
                finish_reason="error",
                error_kind="timeout",
            )
        except Exception as e:
            return error_response(e, spec=self._spec, api_base=self.api_base)

    def get_default_model(self) -> str:
        return self.default_model
