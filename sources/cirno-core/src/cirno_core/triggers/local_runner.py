"""Server delivery loop for local triggers."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from cirno_core.agent.automation_turns import AutomationTurnError
from cirno_core.bus.events import InboundMessage, OutboundMessage
from cirno_core.runtime.admission import RuntimeAdmission
from cirno_core.session.automation_metadata import automation_origin_metadata
from cirno_core.session.transport_metadata import (
    WEBUI_MESSAGE_SOURCE_METADATA_KEY,
    WEBUI_TURN_METADATA_KEY,
)
from cirno_core.triggers.local_session_turns import LOCAL_TRIGGER_META
from cirno_core.triggers.local_store import UNCONFIRMED_DELIVERY_ERROR, LocalTriggerStore
from cirno_core.triggers.local_types import LocalTrigger, TriggerDelivery


async def run_local_trigger_queue(
    *,
    store: LocalTriggerStore,
    submit_turn: Callable[[InboundMessage], Awaitable[OutboundMessage | None]] | None = None,
    is_channel_enabled: Callable[[str], bool],
    poll_interval_s: float = 0.5,
    batch_size: int = 20,
    admission: RuntimeAdmission | None = None,
) -> None:
    """Poll local trigger deliveries and submit them as session turns."""
    if submit_turn is None:
        raise ValueError("run_local_trigger_queue requires submit_turn")
    gate = admission if admission is not None else RuntimeAdmission()
    logger.info("Local trigger queue started")
    await gate.wait_until_open()
    recovered = store.recover_processing_deliveries()
    if recovered:
        logger.warning(
            "Trigger: recovered {} interrupted delivery file(s) from processing",
            recovered,
        )
    while True:
        await gate.wait_until_open()
        with gate.activity():
            deliveries = store.claim_deliveries(limit=batch_size)
            for delivery in deliveries:
                await _run_delivery(
                    store, delivery, submit_turn=submit_turn,
                    is_channel_enabled=is_channel_enabled,
                )
        if not deliveries:
            await asyncio.sleep(poll_interval_s)


async def _run_delivery(
    store: LocalTriggerStore,
    delivery: TriggerDelivery,
    *,
    submit_turn: Callable[[InboundMessage], Awaitable[OutboundMessage | None]],
    is_channel_enabled: Callable[[str], bool],
) -> None:
    record = store.read_delivery_run_record(delivery)
    if record and record.get("status") in {"ok", "error"}:
        _settle_delivery_result(store, delivery, record)
        return
    if record and record.get("status") == "processing":
        store.fail_delivery(delivery, UNCONFIRMED_DELIVERY_ERROR)
        store.record_delivery(
            delivery.trigger_id, status="error", error=UNCONFIRMED_DELIVERY_ERROR,
            run_at_ms=delivery.created_at_ms, delivery_id=delivery.id,
        )
        logger.warning("Trigger: {} ({})", UNCONFIRMED_DELIVERY_ERROR, delivery.id)
        return
    try:
        trigger, response = await _deliver_delivery(
            store, delivery, submit_turn=submit_turn, is_channel_enabled=is_channel_enabled,
        )
    except asyncio.CancelledError as exc:
        store.retry_delivery(delivery, str(exc) or exc.__class__.__name__)
        _write_delivery_run_record(
            store, delivery, status="interrupted", error=str(exc) or exc.__class__.__name__,
        )
        raise
    except (_TerminalDeliveryError, AutomationTurnError) as exc:
        error = str(exc) or exc.__class__.__name__
        _commit_delivery_result(store, delivery, status="error", error=error)
        logger.warning(
            "Trigger: terminal delivery failure {} for {}: {}",
            delivery.id, delivery.trigger_id, error,
        )
    except Exception as exc:
        error = str(exc) or exc.__class__.__name__
        retried = store.retry_delivery(delivery, error)
        _write_delivery_run_record(
            store, delivery, status="retrying" if retried else "error", error=error,
        )
        store.record_delivery(
            delivery.trigger_id, status="error", error=error, run_at_ms=delivery.created_at_ms,
            delivery_id=delivery.id,
        )
        logger.exception(
            "Trigger: failed delivery {} for {}{}", delivery.id, delivery.trigger_id,
            "; queued retry" if retried else "; moved to failed queue",
        )
    else:
        _commit_delivery_result(store, delivery, trigger=trigger, status="ok", response=response)


def _commit_delivery_result(
    store: LocalTriggerStore,
    delivery: TriggerDelivery,
    *,
    status: str,
    trigger: LocalTrigger | None = None,
    error: str | None = None,
    response: str | None = None,
) -> None:
    """Commit execution outcome before writing the history projection or cleaning the queue."""
    try:
        store.write_delivery_run_record(
            delivery, trigger=trigger, status=status, error=error, response=response,
        )
    except Exception as exc:
        # Atomic replacement can succeed before a directory-fsync error. Reuse
        # that receipt; an unconfirmed completed execution must never auto-replay.
        try:
            record = store.read_delivery_run_record(delivery)
        except Exception:
            record = None
        if not record or record.get("status") not in {"ok", "error"}:
            reason = (
                "Delivery reached a terminal outcome but its result could not be saved; "
                f"inspect the session before resubmitting: {exc}"
            )
            store.fail_delivery(delivery, reason)
            store.record_delivery(
                delivery.trigger_id, status="error", error=reason,
                run_at_ms=delivery.created_at_ms, delivery_id=delivery.id,
            )
            logger.exception("Trigger: result save unconfirmed for {}", delivery.id)
            return
    else:
        record = {"status": status, "error": error}
    _settle_delivery_result(store, delivery, record)


def _settle_delivery_result(
    store: LocalTriggerStore, delivery: TriggerDelivery, record: dict[str, Any],
) -> None:
    try:
        store.record_delivery(
            delivery.trigger_id, status=record["status"], error=record.get("error"),
            run_at_ms=delivery.created_at_ms, delivery_id=delivery.id,
        )
        store.complete_delivery(delivery)
    except Exception as exc:
        # Preserve the terminal receipt. The next claim retries only settlement.
        store.retry_delivery(delivery, str(exc) or type(exc).__name__)
        logger.exception("Trigger: result committed but settlement failed for {}", delivery.id)


class _TerminalDeliveryError(RuntimeError):
    pass


async def _deliver_delivery(
    store: LocalTriggerStore,
    delivery: TriggerDelivery,
    *,
    submit_turn: Callable[[InboundMessage], Awaitable[OutboundMessage | None]],
    is_channel_enabled: Callable[[str], bool],
) -> tuple[LocalTrigger, str]:
    trigger = store.get(delivery.trigger_id)
    if trigger is None:
        raise _TerminalDeliveryError("trigger not found")
    if not trigger.enabled:
        raise _TerminalDeliveryError("trigger is disabled")
    if not is_channel_enabled(trigger.channel):
        raise _TerminalDeliveryError(f"target channel is not enabled: {trigger.channel}")

    store.write_delivery_run_record(delivery, trigger=trigger, status="processing")
    msg = InboundMessage(
        channel=trigger.channel,
        sender_id=trigger.sender_id,
        chat_id=trigger.chat_id,
        content=delivery.content,
        metadata=_delivery_metadata(trigger, delivery),
        session_key_override=trigger.session_key,
    )
    response = await submit_turn(msg)
    return trigger, response.content if response else ""


def _write_delivery_run_record(
    store: LocalTriggerStore,
    delivery: TriggerDelivery,
    *,
    status: str,
    trigger: LocalTrigger | None = None,
    error: str | None = None,
    response: str | None = None,
) -> None:
    try:
        store.write_delivery_run_record(
            delivery,
            trigger=trigger,
            status=status,
            error=error,
            response=response,
        )
    except Exception:
        logger.exception(
            "Trigger: failed to write run record for delivery {}",
            delivery.id,
        )


def _delivery_metadata(trigger: LocalTrigger, delivery: TriggerDelivery) -> dict[str, Any]:
    metadata = automation_origin_metadata(trigger.origin_metadata)
    metadata["_runtime_input_source"] = "local_trigger"
    metadata[LOCAL_TRIGGER_META] = {
        "trigger_id": trigger.id,
        "trigger_name": trigger.name,
        "delivery_id": delivery.id,
        "created_at_ms": delivery.created_at_ms,
        "persist_content": _history_content(trigger, delivery),
    }
    if trigger.channel == "websocket":
        metadata.pop(WEBUI_TURN_METADATA_KEY, None)
        metadata[WEBUI_TURN_METADATA_KEY] = f"trigger:{trigger.id}:{uuid.uuid4().hex}"
        source: dict[str, str] = {"kind": "local_trigger"}
        if trigger.name:
            source["label"] = trigger.name
        metadata[WEBUI_MESSAGE_SOURCE_METADATA_KEY] = source
    return metadata


def _history_content(trigger: LocalTrigger, delivery: TriggerDelivery) -> str:
    label = trigger.name.strip() if trigger.name else trigger.id
    return f"Local trigger received: {label}\n\n{delivery.content}"
