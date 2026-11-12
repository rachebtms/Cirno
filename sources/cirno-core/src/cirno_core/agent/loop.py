"""Agent loop: the core processing engine."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import os
import time
import weakref
from collections.abc import Coroutine, Mapping
from contextlib import AbstractContextManager, suppress
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from loguru import logger

from cirno_core.agent import model_presets as preset_helpers
from cirno_core.agent.autocompact import AutoCompact
from cirno_core.agent.context import ContextBuilder, PersistedPromptContextResolver
from cirno_core.agent.context_usage import measure_context_usage
from cirno_core.agent.conversation_models import ConversationModels
from cirno_core.agent.cron_turns import CronTurnCoordinator
from cirno_core.agent.execution.cancellation import cancel_session_work
from cirno_core.agent.execution.command_execution import TurnCommands
from cirno_core.agent.execution.dispatch import SessionDispatcher
from cirno_core.agent.execution.inputs import TurnInputs
from cirno_core.agent.execution.lifecycle import AgentLifecycle
from cirno_core.agent.execution.model_turn import ModelTurnExecutor
from cirno_core.agent.execution.persistence import TurnPersistence
from cirno_core.agent.execution.preparation import TurnPreparation
from cirno_core.agent.execution.processing import TurnProcessor
from cirno_core.agent.execution.reports import WorkerReports
from cirno_core.agent.hook import AgentHook, AgentTurnHookFactory
from cirno_core.agent.model_runtime import ModelRuntimeResolver
from cirno_core.agent.runner.engine import AgentRunner
from cirno_core.agent.subagents.manager import SubagentManager
from cirno_core.agent.tools.context import (
    current_request_context,
)
from cirno_core.agent.tools.file_state import FileStateStore
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.agent.tools.runtime_control import AgentRuntimeControl
from cirno_core.agent.tools.selection import conversation_tools
from cirno_core.agent.turn_delivery import (
    TurnDeliveryFactory,
)
from cirno_core.bus.agent_events import NO_EVENTS, EventSink
from cirno_core.bus.events import (
    InboundMessage,
    OutboundMessage,
)
from cirno_core.bus.queue import MessageBus
from cirno_core.command import CommandRouter, register_builtin_commands
from cirno_core.config.agents import AgentDefaults
from cirno_core.config.models import ModelPresetConfig
from cirno_core.config.network import NetworkConfig
from cirno_core.memory.consolidation import Consolidator
from cirno_core.processes.sessions import ExecSessionManager
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.factory import ProviderSnapshot
from cirno_core.runtime.context import (
    RuntimeContextProvider,
)
from cirno_core.security.workspace_access import (
    WorkspaceScopeResolver,
)
from cirno_core.session import turn_continuation
from cirno_core.session.manager import SESSION_CACHE_MAX_SIZE, SessionManager
from cirno_core.session.model import Session, SessionPolicy
from cirno_core.session.request_usage import RECENT_REQUEST_USAGE_KEY
from cirno_core.session.recovery.contracts import RecoveryAdmission
from cirno_core.triggers.local_turns import LocalTriggerTurnCoordinator
from cirno_core.utils.cancellation import shield_and_drain
from cirno_core.utils.llm_runtime import LLMRuntime

if TYPE_CHECKING:
    from cirno_core.config.channels import ChannelsConfig
    from cirno_core.config.schema import Config
    from cirno_core.config.tools import ToolsConfig
    from cirno_core.cron.service import CronService
    from cirno_core.triggers.local_store import LocalTriggerStore


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    @property
    def tool_names(self) -> list[str]:
        context = current_request_context()
        return [
            ToolRegistry._schema_name(schema)
            for schema in conversation_tools(
                self.tools,
                context.session_key if context else None,
            ).get_definitions()
        ]

    @property
    def provider(self) -> LLMProvider:
        """Provider selected for future turn admissions."""
        return self.runtime_resolver.runtime.provider

    @property
    def model(self) -> str:
        """Model selected for future turn admissions."""
        return self.runtime_resolver.runtime.model

    @property
    def context_window_tokens(self) -> int:
        """Context limit selected for future turn admissions."""
        return self.runtime_resolver.runtime.context_window_tokens

    @property
    def model_presets(self) -> Mapping[str, ModelPresetConfig]:
        """Configured model presets exposed for selection and display."""
        return self.runtime_resolver.model_presets

    @property
    def model_preset(self) -> str | None:
        return self.runtime_resolver.model_preset

    @model_preset.setter
    def model_preset(self, name: str | None) -> None:
        self.set_model_preset(name)

    def llm_runtime(self) -> LLMRuntime:
        return self.models.admit()

    def dream_runtime(self) -> LLMRuntime | None:
        """Resolve the optional preset used for Dream without changing defaults."""
        if not self.dream_model_preset:
            return None
        return self.runtime_resolver.resolve_preset(self.dream_model_preset)

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int | None = None,
        max_concurrent_subagents: int | None = None,
        context_window_tokens: int | None = None,
        max_tool_result_chars: int | None = None,
        provider_retry_mode: str = "standard",
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        tool_registry: ToolRegistry | None = None,
        channels_config: ChannelsConfig | None = None,
        timezone: str | None = None,
        idle_compact_after_minutes: int = 0,
        hooks: list[AgentHook] | None = None,
        hook_factories: list[AgentTurnHookFactory] | None = None,
        disabled_skills: list[str] | None = None,
        tools_config: ToolsConfig | None = None,
        network_config: NetworkConfig | None = None,
        provider_snapshot_loader: Callable[..., ProviderSnapshot] | None = None,
        provider_signature: tuple[object, ...] | None = None,
        model_presets: dict[str, ModelPresetConfig] | None = None,
        preset_catalog_loader: preset_helpers.PresetCatalogLoader | None = None,
        model_preset: str | None = None,
        dream_model_preset: str | None = None,
        preset_snapshot_loader: preset_helpers.PresetSnapshotLoader | None = None,
        turn_delivery_factory: TurnDeliveryFactory | None = None,
        runtime_model_publisher: Callable[[str, str | None], None] | None = None,
        restart_mode: str = "auto",
        local_trigger_store: LocalTriggerStore | None = None,
        idle_compact_check_interval_seconds: int = 0,
        idle_compact_percent: float | None = None,
        idle_compact_keep_percent: float | None = None,
        goal_continuation_limit: int = 0,
        idle_compact_min_tokens: int = 32_000,
        idle_compact_keep_recent_tokens: int = 8_000,
        recovery_admission: RecoveryAdmission | None = None,
    ):
        from cirno_core.config.tools import ToolsConfig

        _tc = tools_config or ToolsConfig()
        defaults = AgentDefaults()
        self.bus = bus
        self.recovery_admission = recovery_admission
        if turn_delivery_factory is not None:
            if turn_delivery_factory.bus is not bus:
                raise ValueError("turn delivery factory must use the agent message bus")
            self.turn_delivery_factory = turn_delivery_factory
        else:
            self.turn_delivery_factory = TurnDeliveryFactory(bus)
        self.runtime_event_publisher = self.turn_delivery_factory.runtime_event_publisher
        self.channels_config = channels_config
        self.restart_mode = restart_mode
        self.workspace = workspace
        initial_model = model or provider.get_default_model()
        self.max_iterations = (
            max_iterations if max_iterations is not None else defaults.max_tool_iterations
        )
        initial_context_window = (
            context_window_tokens
            if context_window_tokens is not None
            else defaults.context_window_tokens
        )
        configured_presets = model_presets or {}
        self.runtime_resolver = ModelRuntimeResolver(
            LLMRuntime.capture(
                provider,
                initial_model,
                context_window_tokens=initial_context_window,
                snapshot_signature=provider_signature,
            ),
            model_presets=configured_presets,
            preset_catalog_loader=preset_catalog_loader,
            configured_default_preset=model_preset,
            provider_snapshot_loader=provider_snapshot_loader,
            preset_snapshot_loader=preset_snapshot_loader,
        )
        self.dream_model_preset = dream_model_preset
        self.dream_max_iterations = 24
        self.max_tool_result_chars = (
            max_tool_result_chars
            if max_tool_result_chars is not None
            else defaults.max_tool_result_chars
        )
        self.provider_retry_mode = provider_retry_mode
        self.tools_config = _tc
        self.network_config = network_config or NetworkConfig()
        self.web_config = _tc.web
        self.exec_config = _tc.exec
        self.cron_service = cron_service
        self.local_trigger_store = local_trigger_store
        self.restrict_to_workspace = restrict_to_workspace
        self.workspace_scopes = WorkspaceScopeResolver(
            default_workspace=workspace,
            default_restrict_to_workspace=restrict_to_workspace,
        )
        self._start_time = time.time()
        self._extra_hooks: list[AgentHook] = hooks or []
        self._hook_factories: list[AgentTurnHookFactory] = hook_factories or []

        self.release_archived_runtime = False
        self.context = ContextBuilder(workspace, timezone=timezone, disabled_skills=disabled_skills)
        self.sessions = session_manager or SessionManager(workspace)
        self.models = ConversationModels(
            self.runtime_resolver, self.sessions, self.runtime_event_publisher,
            runtime_model_publisher,
        )
        # One file-read/write tracker per logical session. The tool registry is
        # shared by this loop, so tools resolve the active state via contextvars.
        self._file_state_store = FileStateStore(max_sessions=SESSION_CACHE_MAX_SIZE)
        # SessionManager owns every durable deletion entrypoint, including the
        # WebUI and fork rollback paths.  Observe that boundary once instead of
        # duplicating cleanup in each consumer.
        self.sessions.set_delete_observer(self._file_state_store.discard)
        self.tools = tool_registry if tool_registry is not None else ToolRegistry()
        self._exec_session_manager = ExecSessionManager()
        self.runner = AgentRunner()
        self.model_turn = ModelTurnExecutor(self)
        self.dispatch = SessionDispatcher(self)
        self.lifecycle = AgentLifecycle(self)
        self.inputs = TurnInputs(self)
        self.preparation = TurnPreparation(self)
        self.persistence = TurnPersistence(self)
        self.reports = WorkerReports(self)
        self.processing = TurnProcessor(self)
        self.command_execution = TurnCommands(self)
        self.consolidator = Consolidator(
            store=self.context.memory,
            sessions=self.sessions,
            build_messages=self.context.build_messages,
            get_tool_definitions=lambda session: conversation_tools(
                self.tools,
                session.key,
                ptc_mode=session.metadata.get("ptc_mode") is True,
            ).get_definitions(),
            resolve_prompt_context=PersistedPromptContextResolver(
                workspace_scopes=self.workspace_scopes,
            ),
        )
        self.subagents = SubagentManager(
            workspace=workspace,
            bus=bus,
            tools_config=_tc,
            network_config=self.network_config,
            max_tool_result_chars=self.max_tool_result_chars,
            restrict_to_workspace=restrict_to_workspace,
            disabled_skills=disabled_skills,
            max_iterations=self.max_iterations,
            max_concurrent_subagents=max_concurrent_subagents,
            consolidator=self.consolidator,
            session_manager=self.sessions,
        )
        self._running = False
        self._runtime_context_providers: list[RuntimeContextProvider] = []
        self._active_tasks: dict[str, set[asyncio.Task[Any]]] = {}
        self._discarding_sessions: set[str] = set()
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._close_lock = asyncio.Lock()
        self._intake_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        self._session_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        # A queue is installed before its single session worker is scheduled.
        # It remains the only admission path until that worker atomically
        # observes the queue empty and removes it.
        self._pending_queues: dict[str, asyncio.Queue[InboundMessage]] = {}
        self._journaled_input_ids: dict[str, set[str]] = {}
        self._preserve_inflight_turns_on_shutdown = False
        self._deferred_automation_turns: dict[str, list[InboundMessage]] = {}
        self._cron_turns = CronTurnCoordinator(
            enqueue=self.dispatch.enqueue,
            deferred_queues=self._deferred_automation_turns,
        )
        self._local_trigger_turns = LocalTriggerTurnCoordinator(
            enqueue=self.dispatch.enqueue,
            deferred_queues=self._deferred_automation_turns,
        )
        self._automation_turn_coordinators = (
            self._cron_turns,
            self._local_trigger_turns,
        )
        # CIRNO_MAX_CONCURRENT_REQUESTS: unset or <=0 means unlimited.
        _max = int(os.environ.get("CIRNO_MAX_CONCURRENT_REQUESTS", "0"))
        self.max_concurrent_requests = max(0, _max)
        self._executing_sessions: set[str] = set()
        self._concurrency_gate: asyncio.Semaphore | None = (
            asyncio.Semaphore(_max) if _max > 0 else None
        )
        self.goal_continuation_limit = goal_continuation_limit
        self.auto_compact = AutoCompact(
            sessions=self.sessions,
            consolidator=self.consolidator,
            idle_compact_after_minutes=idle_compact_after_minutes,
            bind_events=self._idle_events,
            session_lock=self._get_session_lock,
            trigger_percent=idle_compact_percent,
            keep_percent=idle_compact_keep_percent,
            min_context_tokens=idle_compact_min_tokens,
            keep_recent_tokens=idle_compact_keep_recent_tokens,
        )
        self._idle_compact_check_interval_s = idle_compact_check_interval_seconds
        self._next_idle_compact_check_at = time.monotonic()
        self._next_goal_check_at = 0.0
        self._goal_check_task: asyncio.Task[Any] | None = None
        self.memory_idle_callback: Callable[[], Awaitable[None]] | None = None
        if model_preset:
            self.set_model_preset(model_preset, publish_update=False)
        self._register_default_tools(provider_snapshot_loader=provider_snapshot_loader)
        self.commands = CommandRouter()
        register_builtin_commands(self.commands)

    @classmethod
    def from_config(
        cls,
        config: Config,
        bus: MessageBus | None = None,
        *,
        tool_registry: ToolRegistry,
        **extra: Any,
    ) -> AgentLoop:
        """Create an AgentLoop from config with the common parameter set.

        The tool registry is caller-owned so application composition can share
        it with infrastructure such as an ``MCPProvider``.

        Extra keyword arguments are forwarded to ``AgentLoop.__init__``,
        allowing callers to override or extend the standard config-derived
        parameters (e.g. ``cron_service``, ``session_manager``).
        """
        from cirno_core.providers.factory import make_provider

        if bus is None:
            bus = MessageBus()
        defaults = config.agents.defaults
        if "session_manager" not in extra:
            data_dir = config.runtime_data_dir
            extra["session_manager"] = SessionManager(
                config.workspace_path,
                sessions_root=data_dir / "sessions" if data_dir is not None else None,
            )
        provider = extra.pop("provider", None) or make_provider(config)
        resolved = config.resolve_preset()
        model = extra.pop("model", None) or resolved.model
        context_window_tokens = (
            extra.pop("context_window_tokens", None) or resolved.context_window_tokens
        )
        provider_snapshot_loader = extra.pop("provider_snapshot_loader", None)
        preset_snapshot_loader = extra.pop(
            "preset_snapshot_loader", None
        ) or preset_helpers.make_preset_snapshot_loader(
            config,
            provider_snapshot_loader,
        )
        loop = cls(
            bus=bus,
            provider=provider,
            workspace=config.workspace_path,
            model=model,
            max_iterations=defaults.max_tool_iterations,
            max_concurrent_subagents=defaults.max_concurrent_subagents,
            context_window_tokens=context_window_tokens,
            max_tool_result_chars=defaults.max_tool_result_chars,
            provider_retry_mode=defaults.provider_retry_mode,
            restrict_to_workspace=config.tools.restrict_to_workspace,
            channels_config=config.channels,
            timezone=defaults.timezone,
            disabled_skills=defaults.disabled_skills,
            idle_compact_after_minutes=defaults.idle_compact_after_minutes,
            idle_compact_check_interval_seconds=defaults.idle_compact_check_interval_seconds,
            idle_compact_percent=defaults.idle_compact_percent,
            idle_compact_keep_percent=defaults.idle_compact_keep_percent,
            goal_continuation_limit=defaults.goal_continuation_limit,
            idle_compact_min_tokens=defaults.idle_compact_min_tokens,
            idle_compact_keep_recent_tokens=defaults.idle_compact_keep_recent_tokens,
            tools_config=config.tools,
            network_config=config.network,
            model_presets=preset_helpers.configured_model_presets(config),
            model_preset=defaults.model_preset,
            dream_model_preset=defaults.dream.model_override,
            restart_mode=config.server.restart_mode,
            provider_snapshot_loader=provider_snapshot_loader,
            preset_snapshot_loader=preset_snapshot_loader,
            tool_registry=tool_registry,
            **extra,
        )
        loop.context.memory_context_tokens = defaults.memory.context_tokens
        loop.context.checkpoint_context_tokens = defaults.memory.checkpoint_tokens
        loop.context.system_prompts = defaults.system_prompts.model_copy(deep=True)
        loop.subagents.tools.system_prompts = defaults.system_prompts.model_copy(deep=True)
        if source_path := config.source_path:
            from cirno_core.config.loader import load_config

            loop.context.system_prompts_loader = lambda: load_config(source_path).agents.defaults.system_prompts
            loop.subagents.tools.system_prompts_loader = loop.context.current_system_prompts
        loop.dream_max_iterations = defaults.dream.max_tool_iterations
        loop.release_archived_runtime = defaults.memory.release_archived_runtime
        loop.consolidator.on_compaction_saved = loop.persistence.release_archive
        return loop

    def _sync_subagent_runtime_limits(self) -> None:
        """Keep subagent runtime limits aligned with mutable loop settings."""
        self.subagents.limits.max_iterations = self.max_iterations

    def set_runtime_max_iterations(self, value: int) -> None:
        self.max_iterations = value
        self._sync_subagent_runtime_limits()

    def invalidate_runtime_config(self) -> None:
        """Invalidate runtime config for lazy refresh at the next admission."""
        self.runtime_resolver.invalidate()

    def refresh_runtime_config(self) -> LLMRuntime:
        return self.models.refresh()


    async def runtime_for_session(
        self, session: Session, *, recover_removed: bool = True,
    ) -> LLMRuntime:
        return await self.models.for_session(session, recover_removed=recover_removed)

    async def set_session_model_preset(self, session_key: str, name: str) -> LLMRuntime:
        return await self.models.select_session(session_key, name)


    def set_model_preset(
        self, name: str | None, *, publish_update: bool = True,
    ) -> LLMRuntime:
        return self.models.select_default(name, publish_update=publish_update)

    def set_runtime_model(self, model: str) -> LLMRuntime:
        """Select a model on the current provider for future turns."""
        return self.models.select_model(model)

    def set_runtime_context_window(self, context_window_tokens: int) -> LLMRuntime:
        """Select a context limit for future turns."""
        return self.runtime_resolver.select_context_window(context_window_tokens)

    def _register_default_tools(
        self,
        *,
        provider_snapshot_loader: Callable[..., ProviderSnapshot] | None,
    ) -> None:
        """Register the default set of tools via plugin loader."""
        from cirno_core.agent.approval.service import OperationApproval
        from cirno_core.agent.conversation_control import ConversationControl
        from cirno_core.agent.tools.context import ToolContext
        from cirno_core.agent.tools.loader import ToolLoader

        self.operation_approval = OperationApproval(
            self.sessions, self.bus, model_resolver=self.runtime_resolver
        )
        self.conversation_control = ConversationControl(self)
        runtime_control = AgentRuntimeControl(self)
        self.register_runtime_context_provider(runtime_control.workspace_context)
        self.register_runtime_context_provider(
            partial(turn_continuation.iteration_limit_context, self.sessions.state),
        )
        ctx = ToolContext(
            goal_continuation_limit=self.goal_continuation_limit,
            config=self.tools_config,
            network=self.network_config,
            workspace=str(self.workspace),
            bus=self.bus,
            subagent_manager=self.subagents,
            cron_service=self.cron_service,
            exec_session_manager=self._exec_session_manager,
            sessions=self.sessions,
            provider_snapshot_loader=provider_snapshot_loader,
            timezone=self.context.timezone or "UTC",
            workspace_sandbox=self.workspace_scopes.sandbox_status,
            runtime_control=runtime_control,
            conversation_control=self.conversation_control,
        )
        loader = ToolLoader()
        registered = loader.load(ctx, self.tools)

        logger.info("Registered {} tools: {}", len(registered), registered)

    def register_runtime_context_provider(
        self,
        provider: RuntimeContextProvider,
    ) -> Callable[[], None]:
        """Register a per-turn context provider and return an unsubscribe callback."""
        if provider in self._runtime_context_providers:
            return lambda: None
        self._runtime_context_providers.append(provider)

        def _unsubscribe() -> None:
            with suppress(ValueError):
                self._runtime_context_providers.remove(provider)

        return _unsubscribe

    async def submit_cron_turn(self, msg: InboundMessage) -> OutboundMessage | None:
        return await self._cron_turns.submit(msg)

    async def submit_local_trigger_turn(self, msg: InboundMessage) -> OutboundMessage | None:
        return await self._local_trigger_turns.submit(msg)

    def pending_cron_job_ids_for_session(self, session_key: str) -> set[str]:
        return self._cron_turns.pending_job_ids_for_session(session_key)

    def pending_local_trigger_ids_for_session(self, session_key: str) -> set[str]:
        return self._local_trigger_turns.pending_trigger_ids_for_session(session_key)


    def _track_active_task(self, key: str, task: asyncio.Task[Any]) -> None:
        """Track active session work until its task group becomes empty."""
        tasks = self._active_tasks.setdefault(key, set())
        tasks.add(task)
        task.add_done_callback(partial(self._active_task_done, key, tasks))

    def _active_task_done(
        self,
        key: str,
        tasks: set[asyncio.Task[Any]],
        task: asyncio.Task[Any],
    ) -> None:
        tasks.discard(task)
        if not tasks and self._active_tasks.get(key) is tasks:
            self._active_tasks.pop(key, None)

    async def cancel_session_work(self, key: str, *, stop_goal: bool = True) -> int:
        """Stop this session's workers, child agents and processes through one owner."""
        return await shield_and_drain(cancel_session_work(
            key, sessions=self.sessions, active_tasks=self._active_tasks,
            pending_queues=self._pending_queues, cancel_pending=self.dispatch.cancel_pending,
            cancel_children=self.subagents.cancel_by_session, processes=self._exec_session_manager,
            recovery=self.recovery_admission, stop_goal=stop_goal,
        ))

    async def discard_session(self, key: str) -> None:
        """Stop active work for *key* and forget its cached session."""
        with self.bus.admission.activity():
            self._discarding_sessions.add(key)
            try:
                await self.sessions.state.discard(key)
                await self.cancel_session_work(key)
            finally:
                self.discard_session_file_state(key)
                self._discarding_sessions.discard(key)

    def discard_session_file_state(self, key: str) -> None:
        """Forget ephemeral file-read state for a reset or removed session."""
        self._file_state_store.discard(key)

    def _idle_events(
        self,
        session_key: str,
    ) -> EventSink:
        """Bind one idle compaction to its current user-facing destination."""
        session = self.sessions.state.peek_header(session_key, include_runtime=False)
        if session is None:
            return NO_EVENTS
        return self.turn_delivery_factory.session_events(
            session_key,
            session.metadata,
            generation=session.generation,
        )

    async def estimate_session_context_usage(self, key: str) -> dict[str, Any]:
        """Measure the current committed request, including prompts and tool schemas."""
        session = await self.sessions.state.read(key)
        if session is None:
            raise KeyError(key)
        runtime = await self.runtime_for_session(session)
        tokens, source = await measure_context_usage(
            session, runtime,
            consolidator=self.consolidator, workspace_scopes=self.workspace_scopes,
        )
        return {
            "context_tokens": tokens,
            "context_window_tokens": runtime.context_window_tokens,
            "estimated": True,
            "source": source,
            "recent_requests": session.metadata.get(RECENT_REQUEST_USAGE_KEY, []),
        }

    async def run(self) -> None:
        return await self.lifecycle.run()

    def maintenance(self) -> AbstractContextManager[None]:
        return self.lifecycle.maintenance()

    def preserve_inflight_turns_on_shutdown(self) -> None:
        return self.lifecycle.preserve_inflight_turns_on_shutdown()

    def session_intake_lock(self, key: str) -> asyncio.Lock:
        """Serialize short admission/control operations, never a model's execution."""
        lock = self._intake_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._intake_locks[key] = lock
        return lock

    async def aclose(self) -> None:
        return await self.lifecycle.aclose()

    def schedule_background(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        return self.lifecycle.schedule_background(coro)

    def stop(self) -> None:
        return self.lifecycle.stop()

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        sender_id: str = "user",
        media: list[str] | None = None,
        on_progress: Callable[..., Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        ephemeral: bool = False,
        _run_extra_hooks_for_ephemeral: bool = False,
        hooks: list[AgentHook] | None = None,
        hook_factories: list[AgentTurnHookFactory] | None = None,
        tools: ToolRegistry | None = None,
        persist_user_message: bool = True,
        runtime: LLMRuntime | None = None,
        on_runtime_admitted: Callable[[LLMRuntime], Awaitable[None]] | None = None,
        attributes: Mapping[str, Any] | None = None,
        _session_policy: SessionPolicy | None = None,
    ) -> OutboundMessage | None:
        """Process an external message directly and return the outbound payload.

        ``ephemeral`` skips Memory journaling and extra hooks. SDK temporary
        turns also supply a non-persistent policy for a detached session.
        """
        if channel == "system":
            raise ValueError("channel 'system' is reserved for internal messages")
        metadata: dict[str, Any] = {}
        if not persist_user_message:
            metadata[turn_continuation.SKIP_USER_PERSIST_META] = True
        msg = InboundMessage(
            channel=channel,
            sender_id=sender_id,
            chat_id=chat_id,
            content=content,
            media=media or [],
            metadata=metadata,
        )
        # Share the dispatch lock so direct calls serialize with bus turns.
        lock = self._get_session_lock(session_key)
        with self.bus.admission.activity():
            temporary_parent = False
            try:
                async with lock:
                    if not ephemeral:
                        await self.persistence.release_archive(session_key)
                    kwargs: dict[str, Any] = {
                        "session_key": session_key,
                        "on_progress": on_progress,
                        "on_stream": on_stream,
                        "on_stream_end": on_stream_end,
                        "ephemeral": ephemeral,
                    }
                    if _session_policy is not None:
                        # Isolate per-run state before any early save or checkpoint;
                        # the cached conversation must survive a temporary SDK turn.
                        session = (
                            await self.sessions.state.read(session_key) or Session(key=session_key)
                            if not _session_policy.persist
                            else await self.sessions.state.get(session_key)
                        )
                        temporary_parent = not _session_policy.persist and not session.persisted
                        session.policy = SessionPolicy(
                            persist=session.policy.persist and _session_policy.persist,
                            log_content=session.policy.log_content and _session_policy.log_content,
                            disabled_tools=session.policy.disabled_tools
                            | _session_policy.disabled_tools,
                        )
                        kwargs["session"] = session
                    if _run_extra_hooks_for_ephemeral:
                        kwargs["run_extra_hooks_for_ephemeral"] = True
                    if hooks is not None:
                        kwargs["hooks"] = hooks
                    if hook_factories is not None:
                        kwargs["hook_factories"] = hook_factories
                    if tools is not None:
                        kwargs["tools"] = tools
                    if runtime is not None:
                        kwargs["runtime"] = runtime
                    if on_runtime_admitted is not None:
                        kwargs["on_runtime_admitted"] = on_runtime_admitted
                    if attributes is not None:
                        kwargs["attributes"] = dict(attributes)
                    try:
                        return await self.processing.process(msg, **kwargs)
                    finally:
                        if temporary_parent:
                            parent = self.sessions.state.peek_header(
                                session_key, include_runtime=False
                            )
                            if parent is not None and not parent.policy.persist:
                                await self.sessions.state.delete(
                                    session_key, expected_generation=parent.generation
                                )
            finally:
                await self.runtime_event_publisher.run_status_changed(msg, session_key, "idle")
                self.runtime_event_publisher.clear_turn(session_key)

    def _get_session_lock(self, session_key: str) -> asyncio.Lock:
        """Return the shared lock while allowing idle session entries to expire."""
        lock = self._session_locks.get(session_key)
        if lock is None:
            lock = asyncio.Lock()
            self._session_locks[session_key] = lock
        return lock
