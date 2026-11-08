"""Inputs and outcomes of one agent execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cirno_core.agent.context import TranscriptInput
from cirno_core.agent.governance import (
    HistoryConsolidator,
    ProviderCompactionConsolidator,
    TranscriptBuilder,
)
from cirno_core.agent.hook import AgentHook
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.bus.agent_events import NO_EVENTS, EventSink
from cirno_core.providers.contracts import (
    ProviderConversationState,
)
from cirno_core.session.summary import SessionSummaryCheckpoint
from cirno_core.utils.llm_runtime import LLMRuntime
from cirno_usage.context import (
    LLMUsageSource,
)
from cirno_usage.types import LLMUsage

DEFAULT_ERROR_MESSAGE = "Sorry, I encountered an error calling the AI model."

ContinuationCallback = Callable[[], Awaitable[str | None]]


CheckpointCallback = Callable[[dict[str, Any]], Awaitable[None]]


InjectionCallback = Callable[[], Awaitable[Iterable[Any] | None]]


@dataclass(slots=True)
class AgentRunSpec:
    """Configuration for a single agent execution."""

    initial_messages: list[dict[str, Any]] | None
    tools: ToolRegistry
    runtime: LLMRuntime
    max_iterations: int
    max_tool_result_chars: int
    transcript_input: TranscriptInput | None = None
    transcript_builder: TranscriptBuilder | None = None
    hook: AgentHook | None = None
    error_message: str | None = DEFAULT_ERROR_MESSAGE
    max_iterations_message: str | None = None
    concurrent_tools: bool = False
    workspace: Path | None = None
    session_key: str | None = None
    provider_retry_mode: str = "standard"
    checkpoint_callback: CheckpointCallback | None = None
    consolidate_history: HistoryConsolidator | None = None
    consolidate_provider_compaction: ProviderCompactionConsolidator | None = None
    injection_callback: InjectionCallback | None = None
    terminal_injection_callback: InjectionCallback | None = None
    continuation_callback: ContinuationCallback | None = None
    finalize_on_max_iterations: bool = True
    provider_state: ProviderConversationState | None = None
    llm_usage_source: LLMUsageSource | None = None
    events: EventSink = NO_EVENTS


@dataclass(slots=True)
class AgentRunResult:
    """Outcome of a shared agent execution."""

    final_content: str | None
    messages: list[dict[str, Any]]
    tools_used: list[str] = field(default_factory=list)
    usage: LLMUsage | None = None
    # One entry per runner-visible model round. Recovery dispatches needed to
    # produce that round's response are folded into the same usage value.
    round_usages: list[LLMUsage] = field(default_factory=list)
    stop_reason: str = "completed"
    error: str | None = None
    failure_error_kind: str | None = None
    tool_events: list[dict[str, str]] = field(default_factory=list)
    had_injections: bool = False
    # Terminal tail to emit when the preceding final-content prefix was already streamed.
    pending_stream_content: str | None = None
    provider_state: ProviderConversationState | None = field(default=None, repr=False)
    summary_checkpoint: SessionSummaryCheckpoint | None = field(default=None, repr=False)
    provider_compaction_applied: bool = field(default=False, repr=False)
