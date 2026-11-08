"""Durable follow-up journal and coordination delivery receipts."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass

from cirno_core.bus.events import InboundMessage
from cirno_core.session.model import Session
from cirno_core.session.sqlite_store import SessionConflictError

from .operations import SessionOperations
from .repository import SessionRepository


@dataclass
class SessionInbox:
    repository: SessionRepository
    operations: SessionOperations

    async def queue_followup(self, key: str, message: InboundMessage) -> str | None:
        if (
            message.channel != "websocket"
            and not message.metadata.get("_session_message")
            and not message.metadata.get("_heartbeat")
        ):
            return None

        from cirno_core.session.recovery.pending import record_pending_followup

        payload = deepcopy(message)

        def commit() -> str | None:
            def write() -> tuple[Session, str | None, bool]:
                session = self.repository.load(key, history=False)
                if session is None:
                    with self.repository.lock:
                        retired = key in self.repository.retired
                    if (
                        retired
                        or payload.require_existing_session
                        or payload.session_generation is not None
                    ):
                        raise SessionConflictError("follow-up requires an existing session")
                    # The inbox can accept a second input before the first turn
                    # has loaded its session. Journal that input, but never revive
                    # a deleted generation or a discarded Temporary Chat.
                    session = Session(key=key)
                if (
                    payload.session_generation is not None
                    and session.generation != payload.session_generation
                ):
                    raise SessionConflictError("follow-up belongs to a replaced session")
                from cirno_core.session.recovery.contracts import PENDING_FOLLOWUP_ID_KEY
                from cirno_core.session.session_messages import session_message_envelope

                envelope = session_message_envelope(payload.metadata)
                receipt_id = None
                digest = None
                if envelope is not None:
                    import hashlib
                    import json

                    if not session.policy.persist:
                        raise SessionConflictError("coordination requires a persistent session")
                    receipt_id = "session:" + envelope["message_id"]
                    digest = hashlib.sha256(
                        json.dumps(
                            [
                                envelope["source_session_key"],
                                key,
                                payload.content,
                                payload.media,
                                envelope["expect_reply"],
                                payload.metadata.get("_work_report"),
                            ],
                            ensure_ascii=False,
                            sort_keys=True,
                        ).encode()
                    ).hexdigest()
                    receipt = self.repository.store.inbox_receipt(
                        key, session.generation, receipt_id
                    )
                    if receipt is not None:
                        if receipt["digest"] != digest:
                            raise SessionConflictError(
                                "coordination message ID was reused with different content"
                            )
                        if receipt["read"]:
                            return session, None, True
                    # A pending record from an older release already has a journal ID.
                    # Keep it so recovery and consumption acknowledge the same input.
                    existing = next(
                        (
                            record.get("id")
                            for record in session.metadata.get("pending_user_followups", [])
                            if record.get("metadata", {})
                            .get("_session_message", {})
                            .get("message_id")
                            == envelope["message_id"]
                        ),
                        None,
                    )
                    payload.metadata[PENDING_FOLLOWUP_ID_KEY] = existing or receipt_id
                identifier = record_pending_followup(session, payload)
                assert identifier is not None, "accepted follow-up requires a journal ID"
                header_only = session.policy.persist and session.persisted
                if header_only:
                    self.repository.store.replace_metadata(
                        key, session.metadata, updated_at=session.updated_at
                    )
                    session.revision += 1
                else:
                    self.repository.commit(session)
                if receipt_id is not None:
                    assert digest is not None
                    self.repository.store.record_inbox_receipt(
                        key, session.generation, receipt_id, identifier, digest
                    )
                return session, identifier, header_only

            session, identifier, header_only = self.repository.store.run_write(write)
            self.repository.publish(session, history=not header_only)
            return identifier

        return await self.operations.execute(key, commit, operation_name="queue_followup")

    async def acknowledge_followups(self, key: str, identifiers: Sequence[str]) -> None:
        from cirno_core.session.recovery.pending import acknowledge_pending_followups

        values = tuple(identifiers)

        def change(session: Session) -> None:
            acknowledge_pending_followups(session, values)
            if session.policy.persist:
                self.repository.store.mark_inbox_read(key, session.generation, values)

        await self.operations.execute(
            key, lambda: self.repository.change(key, change, history=False)
        )
