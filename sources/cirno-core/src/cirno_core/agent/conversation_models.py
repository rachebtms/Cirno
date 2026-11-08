"""Conversation model admission, persisted selections and change notifications."""

from __future__ import annotations

from collections.abc import Callable

from cirno_core.agent.model_runtime import ModelRuntimeResolver
from cirno_core.bus.runtime_events import RuntimeEventPublisher
from cirno_core.session.manager import SessionManager
from cirno_core.session.model import Session
from cirno_core.session.model_selection import (
    SESSION_MODEL_PRESET_METADATA_KEY,
    model_preset_from_metadata,
)
from cirno_core.utils.llm_runtime import LLMRuntime
from loguru import logger


class ConversationModels:
    def __init__(
        self,
        resolver: ModelRuntimeResolver,
        sessions: SessionManager,
        events: RuntimeEventPublisher,
        on_change: Callable[[str, str | None], None] | None,
    ) -> None:
        self.resolver = resolver
        self.sessions = sessions
        self.events = events
        self.on_change = on_change

    def admit(self) -> LLMRuntime:
        """Resolve the immutable default used to admit the next turn."""
        previous = self.resolver.runtime
        runtime = self.resolver.admit()
        if (
            runtime.model != previous.model
            or runtime.model_preset != previous.model_preset
            or runtime.snapshot_signature != previous.snapshot_signature
        ):
            self.publish(runtime)
        return runtime

    def refresh(self) -> LLMRuntime:
        """Refresh runtime config now and publish the canonical selection."""
        self.resolver.invalidate()
        runtime = self.resolver.admit()
        self.publish(runtime)
        return runtime

    def _resolve(
        self,
        session: Session,
        *,
        recover_removed: bool,
    ) -> LLMRuntime | None:
        """Return the selected runtime, or clear a removed preset for persistence."""
        name = model_preset_from_metadata(session.metadata)
        if name is None:
            return self.admit()
        try:
            return self.resolver.resolve_preset(name)
        except KeyError:
            if not recover_removed or name in self.resolver.model_presets:
                raise
            logger.warning(
                "Session '{}' references removed model preset '{}'; falling back to default",
                session.key,
                name,
            )
            session.metadata.pop(SESSION_MODEL_PRESET_METADATA_KEY, None)
            return None

    async def for_session(
        self,
        session: Session,
        *,
        recover_removed: bool = True,
    ) -> LLMRuntime:
        """Resolve a session runtime without blocking on recovery persistence."""
        runtime = self._resolve(session, recover_removed=recover_removed)
        if runtime is not None:
            return runtime
        await self.sessions.state.update_metadata(
            session.key,
            {},
            remove=(SESSION_MODEL_PRESET_METADATA_KEY,),
            expected_generation=session.generation,
        )
        return self.admit()

    async def select_session(
        self,
        session_key: str,
        name: str,
    ) -> LLMRuntime:
        """Validate and persist one session's preset selection without blocking."""
        runtime = self.resolver.resolve_preset(name)
        await self.sessions.state.update_metadata(
            session_key,
            {SESSION_MODEL_PRESET_METADATA_KEY: runtime.model_preset},
            create_if_missing=True,
        )
        return runtime

    def publish(
        self,
        runtime: LLMRuntime,
        *,
        publish_update: bool = True,
    ) -> None:
        if not publish_update:
            return
        if self.on_change is not None:
            self.on_change(runtime.model, runtime.model_preset)
        self.events.runtime_model_changed(
            runtime.model,
            runtime.model_preset,
        )

    def select_default(
        self,
        name: str | None,
        *,
        publish_update: bool = True,
    ) -> LLMRuntime:
        """Select a named default runtime for future turns."""
        old_model = self.resolver.runtime.model
        runtime = self.resolver.select_preset(name)
        self.publish(runtime, publish_update=publish_update)
        logger.info(
            "Runtime model switched for next turn: {} -> {}",
            old_model,
            runtime.model,
        )
        return runtime

    def select_model(self, model: str) -> LLMRuntime:
        runtime = self.resolver.select_model(model)
        self.publish(runtime)
        return runtime
