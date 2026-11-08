"""State carried through one admitted turn pipeline."""

from __future__ import annotations

import asyncio
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Awaitable, Callable

from cirno_core.agent.context import TranscriptInput
from cirno_core.agent.hook import AgentHook, AgentTurnHookFactory
from cirno_core.agent.tools.context import (
    RequestContext,
)
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.agent.turn_delivery import (
    TurnDelivery,
)
from cirno_core.bus.agent_events import NO_EVENTS, EventSink
from cirno_core.bus.events import (
    InboundMessage,
    OutboundMessage,
)
from cirno_core.providers.contracts import ProviderConversationState
from cirno_core.runtime.context import (
    RuntimeContextBlock,
)
from cirno_core.session.model import Session
from cirno_core.session.summary import (
    SessionSummary,
    SessionSummaryCheckpoint,
)
from cirno_core.utils.llm_runtime import LLMRuntime
from cirno_usage.types import LLMUsage


class TurnKind(Enum):
    USER = auto()
    SYSTEM = auto()


@dataclass
class TurnContext:
    msg: InboundMessage
    session_key: str
    turn_id: str
    runtime: LLMRuntime | None
    kind: TurnKind
    delivery: TurnDelivery
    original_user_text: str | None = None
    session: Session | None = None

    history: list[dict[str, Any]] = field(default_factory=list)
    transcript_input: TranscriptInput | None = None
    provider_state: ProviderConversationState | None = field(default=None, repr=False)
    request_context: RequestContext | None = None
    runtime_context_blocks: list[RuntimeContextBlock] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)

    final_content: str | None = None
    all_messages: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = ""
    failure_error_kind: str | None = None
    streamed_content: bool = False

    input_persisted_early: bool = False
    save_skip: int = 0

    outbound: OutboundMessage | None = None
    suppress_response: bool = False

    events: EventSink = NO_EVENTS
    streaming: bool = False
    on_runtime_admitted: Callable[[LLMRuntime], Awaitable[None]] | None = None

    pending_queue: asyncio.Queue[InboundMessage] | None = None
    pending_summary: SessionSummary | None = None
    summary_checkpoint: SessionSummaryCheckpoint | None = None
    provider_compaction_applied: bool = False

    ephemeral: bool = False
    # SDK temporary turns use an isolated draft; gateway temporary chats retain owner state.
    commit_session: bool = True
    run_extra_hooks_for_ephemeral: bool = False
    hooks: list[AgentHook] = field(default_factory=list)
    hook_factories: list[AgentTurnHookFactory] = field(default_factory=list)
    turn_scopes: list[AbstractContextManager[Any]] = field(default_factory=list)
    tools: ToolRegistry | None = None

    turn_wall_started_at: float = field(default_factory=time.time)
    visible_run_started_at: float | None = None
    turn_latency_ms: int | None = None
    usage: LLMUsage | None = None

    def require_runtime(self) -> LLMRuntime:
        """Return the runtime established by the BUILD stage."""
        if self.runtime is None:
            raise RuntimeError("turn runtime is not initialized; BUILD must run before this stage")
        return self.runtime

    def require_session(self) -> Session:
        """Return the session established by the RESTORE stage."""
        if self.session is None:
            raise RuntimeError(
                "turn session is not initialized; RESTORE must run before this stage"
            )
        return self.session
