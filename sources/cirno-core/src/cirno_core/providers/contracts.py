"""Provider request, response and private continuation contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, cast

from cirno_core.bus.agent_events import NO_EVENTS, EventSink, RetryStatusEvent
from cirno_usage.types import LLMUsage
from cirno_core.providers.tool_calls import ToolCallRequest

if TYPE_CHECKING:
    from cirno_usage.models import LLMCallRecord


RetryEventCallback = Callable[[str], Awaitable[None]]


LLMCallObserver = Callable[["LLMCallRecord"], None]


ProviderCompactionScope = Literal["prior_context", "current_request"]


RetryStatusCallback = Callable[[RetryStatusEvent], Awaitable[None]]


@dataclass
class ProviderConversationState:
    """Opaque provider-owned continuation state.

    ``payload`` may contain encrypted reasoning or other provider-private
    protocol items. Keep it out of normal logs and public chat history.
    ``pending_messages`` are Chat-style messages produced after the most
    recent provider response and are materialized by the owning provider on
    the next request.
    """

    kind: str
    provider: str
    model: str
    version: int
    payload: dict[str, Any] = field(default_factory=dict, repr=False)
    pending_messages: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def with_pending_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> ProviderConversationState:
        """Return a state copy with an isolated pending-message list."""
        return ProviderConversationState(
            kind=self.kind,
            provider=self.provider,
            model=self.model,
            version=self.version,
            payload=self.payload,
            pending_messages=deepcopy(messages),
        )

    def to_private_record(self) -> dict[str, Any]:
        """Serialize for the private session sidecar, never for public history."""
        return {
            "kind": self.kind,
            "provider": self.provider,
            "model": self.model,
            "version": self.version,
            "payload": deepcopy(self.payload),
            "pending_messages": deepcopy(self.pending_messages),
        }

    @classmethod
    def from_private_record(
        cls,
        value: object,
    ) -> ProviderConversationState | None:
        """Validate and deserialize a private session-sidecar value."""
        if not isinstance(value, dict):
            return None
        data = cast(dict[str, Any], value)
        kind = data.get("kind")
        provider = data.get("provider")
        model = data.get("model")
        version = data.get("version")
        payload = data.get("payload")
        pending = data.get("pending_messages", [])
        if (
            not isinstance(kind, str)
            or not kind
            or not isinstance(provider, str)
            or not provider
            or not isinstance(model, str)
            or not model
            or isinstance(version, bool)
            or not isinstance(version, int)
            or not isinstance(payload, dict)
            or not isinstance(pending, list)
            or any(not isinstance(message, dict) for message in cast(list[object], pending))
        ):
            return None
        return cls(
            kind=kind,
            provider=provider,
            model=model,
            version=version,
            payload=deepcopy(cast(dict[str, Any], payload)),
            pending_messages=deepcopy(cast(list[dict[str, Any]], pending)),
        )


@dataclass(frozen=True)
class ProviderCallContext:
    """Optional provider-owned continuation data for one model request.

    The regular ``chat`` contract stays provider-agnostic. Responses-capable
    providers consume this context through the opt-in ``chat_with_context``
    hooks, while every other provider inherits the context-free delegation.
    ``session_id`` gives providers a stable conversation-scoped routing key
    without exposing that identity in the public message transcript.
    """

    conversation_state: ProviderConversationState | None = field(default=None, repr=False)
    context_window_tokens: int | None = None
    session_id: str | None = field(default=None, repr=False)
    events: EventSink = field(default=NO_EVENTS, repr=False, compare=False)
    # None opts out (auxiliary calls); an empty name denotes an unnamed preset.
    response_preset: str | None = None
    response_is_fallback: bool = False
    # A pre-request compactor must fit this budget before sending the pending input.
    compaction_input_budget: int | None = None


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: LLMUsage | None = None
    # Locally measured streaming telemetry. ``generation_ms`` excludes time to
    # first token and provider retry gaps; ``ttft_ms`` measures the first
    # streamed reasoning/content delta from request start. They stay separate
    # from provider usage because providers do not report these consistently.
    generation_ms: int | None = None
    ttft_ms: int | None = None
    retry_after: float | None = None  # Provider supplied retry wait in seconds.
    reasoning_content: str | None = None  # Kimi, DeepSeek-R1, MiMo etc.
    thinking_blocks: list[dict[str, Any]] | None = None  # Anthropic extended thinking
    provider_state: ProviderConversationState | None = field(default=None, repr=False)
    # True only when this response installed a new provider-native compaction
    # boundary. Replaying an older compaction item does not set this flag.
    provider_compaction_applied: bool = field(default=False, repr=False)
    # Identity of the native lifecycle already reported by its operation owner.
    provider_compaction_event_id: str | None = field(default=None, repr=False)
    # State immediately after native compaction, before the normal response
    # continues. An archive prompt can resume this state without replaying H.
    provider_compaction_state: ProviderConversationState | None = field(
        default=None,
        repr=False,
    )
    # Which model input the native compaction state replaces. Providers that
    # compact before attaching the current request delta report
    # ``prior_context``; in-request compaction reports ``current_request``.
    provider_compaction_scope: ProviderCompactionScope | None = field(
        default=None,
        repr=False,
    )
    # Routing wrappers may preserve or discard an incoming provider-owned
    # continuation independently of the final fallback error's retry policy.
    preserve_provider_state_on_error: bool | None = field(default=None, repr=False)
    # Structured error metadata used by retry policy when finish_reason == "error".
    error_status_code: int | None = None
    error_kind: str | None = None  # e.g. "timeout", "connection"
    error_type: str | None = None  # Provider/type semantic, e.g. insufficient_quota.
    error_code: str | None = None  # Provider/code semantic, e.g. rate_limit_exceeded.
    error_retry_after_s: float | None = None
    error_should_retry: bool | None = None
    # A failed fallback must not replace the selected model's public diagnosis.
    # Keep this separate from the last response's retry policy.
    primary_error_kind: str | None = field(default=None, repr=False)
    is_fallback: bool = field(default=False, repr=False)

    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return len(self.tool_calls) > 0

    @property
    def should_execute_tools(self) -> bool:
        """Tools execute only when has_tool_calls AND finish_reason is a tool-capable stop.
        Blocks gateway-injected calls under ``refusal`` / ``content_filter`` / ``error`` (#3220)."""
        if not self.has_tool_calls:
            return False
        return self.finish_reason in ("tool_calls", "function_call", "stop")
