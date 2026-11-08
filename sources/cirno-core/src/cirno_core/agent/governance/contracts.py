"""Model request policy and execution state contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cirno_core.agent.context import TranscriptInput
from cirno_core.bus.agent_events import NO_EVENTS, EventSink
from cirno_core.providers.contracts import (
    ProviderConversationState,
)
from cirno_core.providers.conversation_state import (
    ProviderConversationStateController,
)
from cirno_usage.types import LLMUsage

if TYPE_CHECKING:
    from cirno_core.agent.governance.state import ContextCompactionState
    from cirno_core.agent.tools.registry import ToolRegistry
    from cirno_core.providers.base import LLMProvider


TranscriptBuilder = Callable[[TranscriptInput], list[dict[str, Any]]]
SummaryTranscriptBuilder = Callable[[str], list[dict[str, Any]]]
HistoryConsolidator = Callable[
    [list[dict[str, Any]], str | None],
    Awaitable[str | None],
]
ProviderCompactionConsolidator = Callable[
    [ProviderConversationState, list[dict[str, Any]], str | None],
    Awaitable[str | None],
]


class ContextWindowExceededError(RuntimeError):
    """Raised before a request that exceeds its local context budget."""

    def __init__(
        self,
        *,
        session_key: str | None,
        estimated_tokens: int,
        input_budget: int,
        source: str,
    ) -> None:
        self.session_key = session_key
        self.estimated_tokens = estimated_tokens
        self.input_budget = input_budget
        self.source = source
        super().__init__(
            "Model input exceeds the local context budget "
            f"for {session_key or 'default'}: {estimated_tokens}/{input_budget} via {source}"
        )


@dataclass(slots=True)
class ContextGovernanceConfig:
    provider: LLMProvider
    model: str
    tools: ToolRegistry
    workspace: Path | None
    session_key: str | None
    max_tool_result_chars: int
    context_window_tokens: int | None = None
    max_tokens: int | None = None
    active_compact_percent: int = 100
    checkpoint_reminder_percent: int = 85


@dataclass(slots=True)
class ModelRequestState:
    """Context state shared by every provider request in one runner turn."""

    config: ContextGovernanceConfig
    conversation: ProviderConversationStateController
    compaction: ContextCompactionState
    usage: LLMUsage | None = None
    messages: list[dict[str, Any]] | None = None
    tool_definitions: list[dict[str, Any]] | None = None
    provider_compaction_applied: bool = False
    checkpoint_needed: bool = False
    compacted_tool_results: set[str] = field(default_factory=set)
    events: EventSink = NO_EVENTS
