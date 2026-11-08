"""Continuation controls settle once across maintenance, cancellation and races."""

import asyncio
from datetime import datetime

import pytest
from cirno_core.bus.queue import MessageBus
from cirno_core.runtime.admission import RuntimeBusyError, RuntimeMaintenanceError
from cirno_core.session.manager import SessionManager
from cirno_core.session.recovery.contracts import RECOVERY_METADATA_KEY, RecoveryActionError
from cirno_core.session.recovery.coordinator import RecoveryCoordinator
from cirno_core.session.recovery.delivery import RecoveryDelivery


@pytest.fixture
async def recovery(tmp_path):
    sessions = SessionManager(tmp_path)
    bus = MessageBus()
    owner = RecoveryCoordinator(sessions, bus)
    session = await sessions.state.get("websocket:worker")
    session.add_message("user", "Continue the authorized research from the saved results.")
    session.metadata["webui"] = True
    await sessions.state.finish_turn(session)
    await owner.turn_completed(session.key, failure_kind="model")
    state = (await sessions.state.read_metadata(session.key))["metadata"][RECOVERY_METADATA_KEY]
    while not bus.outbound.empty():
        bus.outbound.get_nowait()
    try:
        yield owner, sessions, bus, {"chat_id": "worker", "recovery_id": state["recovery_id"]}
    finally:
        await sessions.state.aclose()


async def test_maintenance_rejects_continue_before_changing_recovery_state(recovery):
    owner, sessions, bus, payload = recovery
    before = await sessions.state.read_metadata("websocket:worker")
    with bus.admission.pause_if_idle(lambda: False):
        with pytest.raises(RuntimeMaintenanceError):
            await owner.handle_action("continue", payload)
    after = await sessions.state.read_metadata("websocket:worker")
    assert after == before
    assert bus.inbound.empty()
    assert bus.outbound.empty()


async def test_cancelled_control_finishes_queue_handoff_before_returning(recovery, monkeypatch):
    owner, sessions, bus, payload = recovery
    entered = asyncio.Event()
    release = asyncio.Event()
    publish = owner._delivery.publish

    async def slow_publish(_self, *args, **kwargs):
        entered.set()
        await release.wait()
        await publish(*args, **kwargs)

    monkeypatch.setattr(RecoveryDelivery, "publish", slow_publish)
    task = asyncio.create_task(owner.handle_action("continue", payload))
    try:
        await asyncio.wait_for(entered.wait(), timeout=3)
        with pytest.raises(RuntimeBusyError):
            with bus.admission.pause_if_idle(lambda: False):
                pytest.fail("maintenance accepted an unfinished continuation handoff")
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "accepted continuation must finish its state/queue handoff"
    finally:
        release.set()
        results = await asyncio.gather(task, return_exceptions=True)
    assert isinstance(results[0], asyncio.CancelledError)
    assert bus.inbound_size == 1
    state = (await sessions.state.read_metadata("websocket:worker"))["metadata"][
        RECOVERY_METADATA_KEY
    ]
    assert state["status"] == "resuming"
    assert bus.inbound.get_nowait().metadata["_webui_recovery_id"] == payload["recovery_id"]


async def test_simultaneous_continue_actions_enqueue_exactly_once(recovery, monkeypatch):
    owner, _, bus, payload = recovery

    class SameClock:
        @staticmethod
        def now():
            return datetime(2026, 11, 8, 12)

    monkeypatch.setattr("cirno_core.session.recovery.state.datetime", SameClock)
    results = await asyncio.gather(
        owner.handle_action("continue", payload),
        owner.handle_action("continue", payload),
        return_exceptions=True,
    )
    success = [value for value in results if isinstance(value, dict)]
    errors = [value for value in results if isinstance(value, BaseException)]
    assert len(success) == 1
    assert len(errors) == 1 and isinstance(errors[0], RecoveryActionError)
    assert errors[0].status == 409
    assert bus.inbound_size == 1


@pytest.mark.parametrize("log_content", [True, False])
async def test_restart_failure_respects_content_logging_policy(recovery, monkeypatch, log_content):
    from dataclasses import replace

    from cirno_core.session.recovery.restart import RecoveryRestart
    from loguru import logger

    owner, sessions, bus, _ = recovery
    session = await sessions.state.read_header("websocket:worker")
    await sessions.state.set_policy(session.key, replace(session.policy, log_content=log_content))
    captured = []
    marker = "private-recovery-detail"

    async def fail(_self, _session, _chat_id):
        raise RuntimeError(marker)

    monkeypatch.setattr(RecoveryRestart, "recover", fail)
    handler = logger.add(lambda message: captured.append(str(message)))
    try:
        await owner.scan()
    finally:
        logger.remove(handler)
    assert (marker in "".join(captured)) is log_content
    state = (await sessions.state.read_metadata(session.key))["metadata"][RECOVERY_METADATA_KEY]
    assert state["status"] == "failed"
    assert bus.inbound.empty()


async def test_continue_reactivates_saved_goal_without_losing_progress_or_budget(recovery):
    owner, sessions, bus, payload = recovery
    saved_goal = {
        "goal_id": "research-goal",
        "status": "waiting",
        "objective": "Complete the authorized study",
        "recap": "Experiment A completed",
        "wake_at": "2026-12-01",
        "continuation_limit": 10,
    }
    await sessions.state.update_metadata(
        "websocket:worker",
        {
            "goal_state": saved_goal,
            "_sustained_goal_continuation_rounds": 4,
        },
    )

    await owner.handle_action("continue", payload)

    metadata = (await sessions.state.read_metadata("websocket:worker"))["metadata"]
    expected = {key: value for key, value in saved_goal.items() if key != "wake_at"}
    expected["status"] = "active"
    assert metadata["goal_state"] == expected
    assert metadata["_sustained_goal_continuation_rounds"] == 4
    assert bus.inbound_size == 1
