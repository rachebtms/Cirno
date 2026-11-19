"""Storage settlement must not replay already-completed trigger instructions."""

import json
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.automation_turns import AutomationTurnError
from cirno_core.bus.events import OutboundMessage
from cirno_core.storage.records import RecordStoreError
from cirno_core.triggers.local_runner import _run_delivery
from cirno_core.triggers.local_store import LocalTriggerStore


def setup_delivery(tmp_path):
    store = LocalTriggerStore(tmp_path / "triggers")
    trigger = store.create(
        name="Report", channel="websocket", chat_id="report", session_key="websocket:report"
    )
    store.enqueue(trigger.id, "Perform the accepted work")
    return store, trigger, store.claim_deliveries()[0]


def test_history_settlement_distinguishes_deliveries_with_the_same_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr("cirno_core.triggers.local_store._now_ms", lambda: 1_900_000_000_000)
    store, trigger, first = setup_delivery(tmp_path)
    second = store.enqueue(trigger.id, "A different accepted instruction")
    assert first.created_at_ms == second.created_at_ms
    for delivery in (first, second, first):
        store.record_delivery(
            trigger.id,
            status="ok",
            run_at_ms=delivery.created_at_ms,
            delivery_id=delivery.id,
        )
    records = LocalTriggerStore(store.root).get(trigger.id).run_history
    assert [record.delivery_id for record in records] == [first.id, second.id]


def test_history_keeps_an_explicit_zero_creation_timestamp(tmp_path):
    store, trigger, delivery = setup_delivery(tmp_path)
    store.record_delivery(trigger.id, status="ok", run_at_ms=0, delivery_id=delivery.id)
    saved = LocalTriggerStore(store.root).get(trigger.id)
    assert saved.last_run_at_ms == 0
    assert saved.run_history[0].run_at_ms == 0


def test_retried_delivery_updates_its_history_instead_of_creating_conflicting_runs(tmp_path):
    store, trigger, delivery = setup_delivery(tmp_path)
    for status, error in (("error", "Temporary transport failure"), ("ok", None)):
        store.record_delivery(
            trigger.id,
            status=status,
            error=error,
            run_at_ms=delivery.created_at_ms,
            delivery_id=delivery.id,
        )
    saved = LocalTriggerStore(store.root).get(trigger.id)
    assert len(saved.run_history) == 1
    assert saved.run_history[0].status == "ok"
    assert saved.run_history[0].error is None


@pytest.mark.parametrize("failure", ["history", "cleanup"])
@pytest.mark.parametrize("status", ["ok", "error"])
async def test_completed_delivery_retries_only_storage_settlement(
    tmp_path, monkeypatch, failure, status
):
    store, trigger, delivery = setup_delivery(tmp_path)
    submit = AsyncMock(
        return_value=OutboundMessage(channel="websocket", chat_id="report", content="Result ready")
    )
    if status == "error":
        submit.side_effect = AutomationTurnError("Agent execution failed")
    method = "record_delivery" if failure == "history" else "complete_delivery"
    original = getattr(store, method)
    attempts = 0

    def fail_once(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("Injected settlement failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(store, method, fail_once)
    await _run_delivery(store, delivery, submit_turn=submit, is_channel_enabled=lambda _: True)
    for retry in store.claim_deliveries():
        await _run_delivery(store, retry, submit_turn=submit, is_channel_enabled=lambda _: True)
    assert submit.await_count == 1
    saved = store.get(trigger.id)
    assert saved.last_status == status
    assert len(saved.run_history) == 1
    record = json.loads((store.runs_dir / f"{delivery.id}.json").read_text())
    assert record["status"] == status
    assert record.get("response") == ("Result ready" if status == "ok" else None)
    assert not list(store.processing_dir.iterdir())
    assert not list(store.inbox_dir.iterdir())


async def test_restart_with_terminal_receipt_finishes_without_resubmitting(tmp_path):
    store, trigger, delivery = setup_delivery(tmp_path)
    store.write_delivery_run_record(
        delivery, trigger=trigger, status="ok", response="Committed result"
    )
    restarted = LocalTriggerStore(store.root)
    restarted.recover_processing_deliveries()
    submit = AsyncMock(return_value=None)
    for retry in restarted.claim_deliveries():
        await _run_delivery(restarted, retry, submit_turn=submit, is_channel_enabled=lambda _: True)
    submit.assert_not_awaited()
    assert restarted.get(trigger.id).last_status == "ok"


async def test_inbox_copy_with_unconfirmed_processing_receipt_does_not_execute(tmp_path):
    store, trigger, delivery = setup_delivery(tmp_path)
    store.write_delivery_run_record(delivery, trigger=trigger, status="processing")
    store.retry_delivery(delivery, "Queue move completed before the audit update")
    submit = AsyncMock(return_value=None)
    for retry in store.claim_deliveries():
        await _run_delivery(store, retry, submit_turn=submit, is_channel_enabled=lambda _: True)
    submit.assert_not_awaited()
    assert list(store.failed_dir.glob("*.json"))


def test_restart_does_not_blindly_replay_a_processing_outcome(tmp_path):
    store, trigger, delivery = setup_delivery(tmp_path)
    store.write_delivery_run_record(delivery, trigger=trigger, status="processing")
    restarted = LocalTriggerStore(store.root)
    restarted.recover_processing_deliveries()
    assert restarted.claim_deliveries() == []
    failed = list(restarted.failed_dir.glob("*.json"))
    assert len(failed) == 1
    assert "unconfirmed" in failed[0].read_text()
    assert "unconfirmed" in restarted.get(trigger.id).last_error


@pytest.mark.parametrize("after_replace", [False, True])
async def test_result_write_failure_never_replays_completed_instructions(
    tmp_path, monkeypatch, after_replace
):
    store, trigger, delivery = setup_delivery(tmp_path)
    submit = AsyncMock(return_value=None)
    write = store.write_delivery_run_record

    def fail_result(*args, **kwargs):
        if kwargs["status"] == "ok":
            if after_replace:
                write(*args, **kwargs)
            raise OSError("Injected receipt failure")
        return write(*args, **kwargs)

    monkeypatch.setattr(store, "write_delivery_run_record", fail_result)
    await _run_delivery(store, delivery, submit_turn=submit, is_channel_enabled=lambda _: True)
    assert submit.await_count == 1
    assert store.claim_deliveries() == []
    assert store.get(trigger.id).last_status == ("ok" if after_replace else "error")
    assert bool(list(store.failed_dir.glob("*.json"))) is not after_replace
    if not after_replace:
        assert "inspect the session" in store.get(trigger.id).last_error


@pytest.mark.parametrize("bad", ["{", "wrong_identity"])
async def test_unreadable_receipt_is_preserved_without_executing_or_overwriting(tmp_path, bad):
    store, _, delivery = setup_delivery(tmp_path)
    path = store.runs_dir / f"{delivery.id}.json"
    if bad == "wrong_identity":
        record = json.loads(path.read_text())
        record["delivery_id"] = "another-delivery"
        bad = json.dumps(record)
    path.write_text(bad)
    submit = AsyncMock(return_value=None)
    with pytest.raises(RecordStoreError):
        await _run_delivery(store, delivery, submit_turn=submit, is_channel_enabled=lambda _: True)
    submit.assert_not_awaited()
    assert path.read_text() == bad
    assert delivery.path.exists()
