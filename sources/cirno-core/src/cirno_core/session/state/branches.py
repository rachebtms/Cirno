"""Atomic message edits and conversation forks."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass

from cirno_core.bus.events import InboundMessage
from cirno_core.session.display_history import HistoryFact, HistoryKind
from cirno_core.session.branching import fork_session, session_prefix
from cirno_core.session.model import Session
from cirno_core.session.recovery.contracts import PENDING_USER_TURN_KEY, RUNTIME_CHECKPOINT_KEY
from cirno_core.session.sqlite_store import SessionConflictError

from .operations import SessionOperations
from .repository import SessionRepository


@dataclass
class SessionBranches:
    repository: SessionRepository
    operations: SessionOperations

    async def edit_user_input(self, key: str, turn_id: str, content: str) -> InboundMessage:
        """Rewind a human prompt and durably queue its replacement atomically.

        The new generation revokes queued work and old snapshots. File changes
        and external tool side effects are deliberately outside this transaction.
        """
        if not turn_id or not content.strip():
            raise ValueError("A saved user turn and non-empty replacement text are required.")
        from uuid import uuid4

        from cirno_core.bus.events import INBOUND_META_TURN_ID
        from cirno_core.session.history_visibility import is_hidden_history_message
        from cirno_core.session.recovery.contracts import PENDING_FOLLOWUP_ID_KEY
        from cirno_core.session.recovery.pending import record_pending_followup
        from cirno_core.session.session_identity import webui_chat_id
        from cirno_core.session.transcript import session_display_facts

        chat_id = webui_chat_id(key)
        if not chat_id:
            raise ValueError("Message editing requires a saved Web conversation.")

        def commit() -> InboundMessage:
            def write() -> tuple[Session, InboundMessage]:
                source = self.repository.load(key)
                if source is None or not source.policy.persist:
                    raise ValueError("The conversation no longer exists or is temporary.")
                if source.metadata.get(PENDING_USER_TURN_KEY) or source.metadata.get(
                    RUNTIME_CHECKPOINT_KEY
                ):
                    raise SessionConflictError("Stop the conversation before editing a message.")
                selected = None
                index = 0
                for message in source.messages:
                    if message.get("role") != "user" or is_hidden_history_message(message):
                        continue
                    if message.get(INBOUND_META_TURN_ID) == turn_id:
                        selected = message
                        break
                    index += 1
                if selected is None or selected.get("input_origin") or selected.get("_command"):
                    raise ValueError(
                        "Only a saved human message can be edited; reload the conversation if it changed."
                    )
                original_fact = self.repository.store.project_history(
                    key,
                    lambda history: next(
                        (
                            fact
                            for _, _, fact in history.navigation()
                            if fact.kind is HistoryKind.INPUT and fact.turn_id == turn_id
                        ),
                        None,
                    ),
                )
                original_fields = dict(original_fact.content) if original_fact else {}
                if original_fields.get("input_origin") or original_fields.get("session_message"):
                    raise ValueError("Agent and system inputs cannot be edited as human messages.")
                target = session_prefix(source, key, index)
                assert target is not None
                for name in ("title", "title_user_edited", "session_handle"):
                    if name in source.metadata:
                        target.metadata[name] = deepcopy(source.metadata[name])
                # Internal reports can exist only in model context. Anchor the
                # display rewind to the selected turn, never its model index.
                facts = self.repository.store.history_prefix(key, index, before_turn_id=turn_id)
                if facts is None:
                    facts = session_display_facts(target)
                message = InboundMessage(
                    channel="websocket",
                    sender_id="webui:owner",
                    chat_id=chat_id,
                    content=content,
                    media=list(selected.get("media") or original_fields.get("media_paths") or []),
                    session_key_override=key,
                    require_existing_session=True,
                    session_generation=target.generation,
                    metadata={
                        "webui": True,
                        "_wants_stream": True,
                        INBOUND_META_TURN_ID: uuid4().hex,
                        "_history_generation": target.generation,
                        **{
                            name: original_fields[name]
                            for name in (
                                "cli_apps",
                                "mcp_presets",
                                "session_mentions",
                                "local_media_paths",
                            )
                            if name in original_fields
                        },
                    },
                )
                identifier = record_pending_followup(target, message)
                assert identifier is not None
                message.metadata[PENDING_FOLLOWUP_ID_KEY] = identifier
                self.repository.store.delete(key)
                self.repository.commit(target)
                if facts:
                    self.repository.store.append_history(
                        key, facts, expected_generation=target.generation
                    )
                return target, message

            target, message = self.repository.store.run_write(write)
            self.repository.publish(target)
            return message

        message = await self.operations.execute(key, commit, operation_name="edit_user_input")
        if self.repository.on_delete is not None:
            self.repository.on_delete(key)
        return message

    async def fork(
        self,
        source_key: str,
        target_key: str,
        before_user_index: int,
        *,
        title: str | None = None,
        history_projection: Callable[[Session], list[HistoryFact]] | None = None,
    ) -> Session | None:
        def commit() -> Session | None:
            def write() -> Session | None:
                source = self.repository.load(source_key)
                if source is None:
                    return None
                context_index = self.repository.store.fork_context_index(source, before_user_index)
                if context_index is None:
                    return None
                target = fork_session(source, target_key, context_index)
                if target is None:
                    return None
                if title:
                    target.metadata["title"] = title
                self.repository.commit(target)
                copied = self.repository.store.copy_history_prefix(
                    source_key, target, before_user_index
                )
                if not copied and history_projection is not None:
                    facts = history_projection(target)
                    facts.append(
                        HistoryFact(
                            HistoryKind.FORK_BOUNDARY,
                            created_at_ms=int(target.created_at.timestamp() * 1000),
                        )
                    )
                    self.repository.store.append_history(
                        target.key, facts, expected_generation=target.generation
                    )
                return target

            target = self.repository.store.run_write(write)
            if target is None:
                return None
            self.repository.publish(target)
            return self.repository.draft(target)

        return await self.operations.execute(
            (source_key, target_key),
            commit,
            operation_name="fork",
        )
