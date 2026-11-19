"""Stopping review settles accepted local evidence and durable decision notices."""

import asyncio
import threading
from types import SimpleNamespace

import pytest
from cirno_core.agent.approval.service import OperationApproval
from cirno_core.agent.tools.context import RequestContext
from cirno_core.bus.events import INBOUND_META_TURN_ID
from cirno_core.bus.queue import MessageBus
from cirno_core.notifications.inbox import NotificationInbox
from cirno_core.security.approval.store import ApprovalStore
from cirno_core.session.manager import SessionManager


@pytest.fixture
async def review(tmp_path, monkeypatch):
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    session = await sessions.state.import_messages("websocket:fixture", [
        {"role": "user", "content": "Fixture authorized work", INBOUND_META_TURN_ID: "human"},
    ])
    await sessions.state.update_metadata(session.key, {"goal_state": {
        "goal_id": "fixture-goal", "objective": "Fixture", "status": "active", "continuation_count": 0,
    }})
    settings = SimpleNamespace(enabled=False, model_override="default", timeout_seconds=1)
    monkeypatch.setattr("cirno_core.agent.approval.service.load_config", lambda *_args: SimpleNamespace(
        agents=SimpleNamespace(defaults=SimpleNamespace(approval=settings)),
    ))
    evidence = {"tool": "fixture", "arguments": {}, "scripts": [], "workspace": str(tmp_path), "resolved_paths": []}
    monkeypatch.setattr("cirno_core.agent.approval.service.operation_evidence", lambda *_args, **_kwargs: evidence)
    service = OperationApproval(sessions, MessageBus(), store=ApprovalStore(tmp_path / "approvals.sqlite3"), inbox=NotificationInbox(tmp_path))
    request = RequestContext("websocket", "fixture", session_key=session.key, session_generation=session.generation,
                             turn_id="human", workspace=tmp_path)
    try:
        yield service, request, settings, evidence
    finally:
        await sessions.state.aclose()


@pytest.mark.parametrize("phase", ["evidence", "record", "notice"])
@pytest.mark.parametrize("stop_goal", [False, True])
async def test_review_cancellation_settles_local_work_and_keeps_accepted_pending_notice(review, monkeypatch, phase, stop_goal):
    service, request, _settings, evidence = review
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()
    finished = threading.Event()
    calls = []

    def gated(call):
        def run(*args, **kwargs):
            calls.append(True)
            loop.call_soon_threadsafe(entered.set)
            try:
                assert release.wait(2), "Fixture did not release accepted review work"
                return call(*args, **kwargs)
            finally:
                finished.set()
        return run

    if phase == "evidence":
        monkeypatch.setattr("cirno_core.agent.approval.service.operation_evidence", gated(lambda *_args, **_kwargs: evidence))
    elif phase == "record":
        monkeypatch.setattr(service.store, "record", gated(service.store.record))
    else:
        monkeypatch.setattr(service.inbox, "record", gated(service.inbox.record))
    task = asyncio.create_task(service.authorize(SimpleNamespace(name="fixture"), {}, request, "Fixture boundary"))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        if stop_goal:
            await service.sessions.state.update_metadata(request.session_key, {"goal_state": {
                "goal_id": "fixture-goal", "objective": "Fixture", "status": "stopped", "continuation_count": 0,
            }})
        done, _ = await asyncio.wait({task}, timeout=0.01)
        assert not done, "Review stopped while accepted local work was still running"
    finally:
        release.set()
        await asyncio.to_thread(finished.wait, 1)
        await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    assert len(calls) == 1
    notices = service.inbox.list()["items"]
    assert len(notices) == (0 if phase == "evidence" else 1)
    if notices:
        assert service.store.get(notices[0]["data"]["approval_id"])["status"] == "pending"
    header = await service.sessions.state.read_header(request.session_key)
    assert header.metadata["goal_state"]["status"] == ("stopped" if stop_goal else "active" if phase == "evidence" else "waiting")
    assert service._locks == {}


async def test_stopping_the_model_review_cancels_it_without_saving_a_decision(review, monkeypatch):
    service, request, settings, _evidence = review
    settings.enabled = True
    entered = asyncio.Event()

    async def model(*_args, **_kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("cirno_core.agent.approval.service.review_operation", model)
    task = asyncio.create_task(service.authorize(SimpleNamespace(name="fixture"), {}, request, "Fixture boundary"))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert service.inbox.list()["items"] == []
    assert service._locks == {}


@pytest.mark.parametrize("decision", ["human", "deny"])
@pytest.mark.parametrize("repair", ["retry", "restart"])
async def test_failed_review_publication_recovers_without_another_model_call(review, monkeypatch, decision, repair):
    service, request, settings, _ = review
    settings.enabled = True
    reviews = []

    async def model(*_args, **_kwargs):
        reviews.append(True)
        return decision, "Fixture decision"

    monkeypatch.setattr("cirno_core.agent.approval.service.review_operation", model)
    original = service.inbox.record
    monkeypatch.setattr(service.inbox, "record", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("fixture notice failure")))
    tool = SimpleNamespace(name="fixture")
    with pytest.raises(OSError, match="fixture notice failure"):
        await service.authorize(tool, {}, request, "Fixture boundary")
    assert service.inbox.list()["items"] == []
    monkeypatch.setattr(service.inbox, "record", original)
    if repair == "restart":
        service = OperationApproval(service.sessions, service.bus, store=service.store, inbox=service.inbox)
        await service.recover()
    else:
        with pytest.raises(PermissionError, match="pending|denied"):
            await service.authorize(tool, {}, request, "Fixture boundary")
    notices = service.inbox.list()["items"]
    assert len(notices) == 1
    assert notices[0]["status"] == ("pending" if decision == "human" else "denied")
    assert notices[0]["data"]["boundary"] == "Fixture boundary"
    assert reviews == [True]
    header = await service.sessions.state.read_header(request.session_key)
    assert header.metadata["goal_state"]["status"] == ("waiting" if decision == "human" else "active")


async def test_owner_decision_cannot_be_overwritten_by_late_pending_bookkeeping(review, monkeypatch):
    service, request, *_ = review
    entered, release = asyncio.Event(), asyncio.Event()
    original = service.sessions.state.mutate_metadata

    async def delayed(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(service.sessions.state, "mutate_metadata", delayed)
    task = asyncio.create_task(service.authorize(SimpleNamespace(name="fixture"), {}, request, "Fixture boundary"))
    owner = None
    try:
        await asyncio.wait_for(entered.wait(), 1)
        # A second service is what the authenticated HTTP decision endpoint uses.
        owner_service = OperationApproval(service.sessions, service.bus, store=service.store, inbox=service.inbox)
        with service.store.connect() as db:
            identifier = db.execute("SELECT id FROM approvals").fetchone()[0]
        owner = asyncio.create_task(owner_service.decide(identifier, True))
        done, _ = await asyncio.wait({owner}, timeout=0.03)
        assert not done, "Owner settlement raced the original pending Goal update"
    finally:
        release.set()
        await asyncio.gather(task, *([owner] if owner else []), return_exceptions=True)
    assert owner is not None and owner.result()["status"] == "approved"
    header = await service.sessions.state.read_header(request.session_key)
    assert header.metadata["goal_state"]["status"] == "active"
    assert "approval_id" not in header.metadata["goal_state"]
    assert service.inbox.get("approval:" + identifier)["status"] == "approved"


async def test_consumed_grant_with_unfinished_wake_is_recovered_as_approved(review, monkeypatch):
    from cirno_core.session.recovery.pending import pending_followups

    service, request, *_ = review
    with pytest.raises(PermissionError):
        await service.authorize(SimpleNamespace(name="fixture"), {}, request, "Fixture boundary")
    identifier = service.inbox.list()["items"][0]["data"]["approval_id"]
    service.store.decide(identifier, approved=True, generation=request.session_generation)
    assert service.store.consume(identifier)
    await service.recover()
    notice = service.inbox.get("approval:" + identifier)
    assert notice["status"] == "approved"
    pending = pending_followups(await service.sessions.state.get(request.session_key))
    assert len(pending) == 1
    inbound = pending[0]
    assert "approved one use of" in inbound.content
    assert service.store.get(identifier)["status"] == "used"


@pytest.mark.parametrize("phase", ["publication", "decision"])
async def test_approval_recovery_does_not_capture_a_replacement_goal(review, monkeypatch, phase):
    from cirno_core.session.recovery.pending import pending_followups

    service, request, *_ = review
    original = service.inbox.record
    if phase == "publication":
        monkeypatch.setattr(service.inbox, "record", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("fixture")))
    with pytest.raises(OSError if phase == "publication" else PermissionError):
        await service.authorize(SimpleNamespace(name="fixture"), {}, request, "Fixture boundary")
    monkeypatch.setattr(service.inbox, "record", original)
    await service.sessions.state.update_metadata(request.session_key, {"goal_state": {
        "goal_id": "replacement", "objective": "New work", "status": "active", "continuation_count": 0,
    }})
    if phase == "decision":
        identifier = service.inbox.list()["items"][0]["data"]["approval_id"]
        service.store.decide(identifier, approved=True, generation=request.session_generation)
    await service.recover()
    session = await service.sessions.state.get(request.session_key)
    assert session.metadata["goal_state"]["status"] == "active"
    assert "approval_id" not in session.metadata["goal_state"]
    assert not pending_followups(session)


@pytest.mark.parametrize("entry", ["decide", "recover"])
async def test_cancelled_owner_settlement_drains_the_notice_and_followup(review, monkeypatch, entry):
    from cirno_core.session.recovery.pending import pending_followups

    service, request, *_ = review
    with pytest.raises(PermissionError):
        await service.authorize(SimpleNamespace(name="fixture"), {}, request, "Fixture boundary")
    identifier = service.inbox.list()["items"][0]["data"]["approval_id"]
    if entry == "recover":
        service.store.decide(identifier, approved=True, generation=request.session_generation)
    loop = asyncio.get_running_loop()
    entered, release = asyncio.Event(), threading.Event()
    original = service.inbox.record

    def blocked(*args, **kwargs):
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(2)
        return original(*args, **kwargs)

    monkeypatch.setattr(service.inbox, "record", blocked)
    task = asyncio.create_task(service.decide(identifier, True) if entry == "decide" else service.recover())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.01)
        assert not done, "An accepted local settlement was abandoned on cancellation"
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    assert service.inbox.get("approval:" + identifier)["status"] == "approved"
    assert not service.store.pending_wakes()
    assert len(pending_followups(await service.sessions.state.get(request.session_key))) == 1


@pytest.mark.parametrize("source", ["deleted", "replaced", "stopped"])
async def test_unpublished_review_recovery_respects_its_source(review, monkeypatch, source):
    service, request, *_ = review
    original = service.inbox.record
    monkeypatch.setattr(service.inbox, "record", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("fixture")))
    with pytest.raises(OSError):
        await service.authorize(SimpleNamespace(name="fixture"), {}, request, "Fixture boundary")
    monkeypatch.setattr(service.inbox, "record", original)
    if source == "stopped":
        header = await service.sessions.state.read_header(request.session_key)
        await service.sessions.state.update_metadata(request.session_key, {"goal_state": {
            **header.metadata["goal_state"], "status": "stopped",
        }})
    else:
        await service.sessions.state.delete(request.session_key)
        if source == "replaced":
            await service.sessions.state.import_messages(request.session_key, [{"role": "user", "content": "Replacement"}])
    await service.recover()
    assert not service.store.pending_reviews()
    assert service.bus.inbound_size == 0
    if source == "stopped":
        assert service.inbox.list()["items"][0]["status"] == "pending"
        header = await service.sessions.state.read_header(request.session_key)
        assert header.metadata["goal_state"]["status"] == "stopped"
    else:
        assert service.inbox.list()["items"] == []
        header = await service.sessions.state.read_header(request.session_key)
        assert (header is None) == (source == "deleted")


@pytest.mark.parametrize("fail_upgrade", [False, True])
def test_legacy_approval_store_replays_unpublished_pending_without_changing_identity(tmp_path, fail_upgrade):
    import sqlite3

    path = tmp_path / "approvals.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE approvals (
            id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, session_key TEXT NOT NULL,
            generation TEXT NOT NULL, turn_id TEXT NOT NULL, operation TEXT NOT NULL,
            status TEXT NOT NULL, reason TEXT NOT NULL, created_at REAL NOT NULL,
            decided_at REAL, wake_pending INTEGER NOT NULL DEFAULT 0
        )""")
        db.execute("INSERT INTO approvals VALUES ('original','fingerprint','websocket:fixture','generation','turn','{}','pending','reason',123,NULL,0)")
        if fail_upgrade:
            db.execute("CREATE TRIGGER fail_upgrade BEFORE UPDATE ON approvals BEGIN SELECT RAISE(ABORT,'fixture upgrade failure'); END")
    store = ApprovalStore(path)
    if fail_upgrade:
        with pytest.raises(sqlite3.IntegrityError, match="fixture upgrade failure"):
            store.pending_reviews()
        with sqlite3.connect(path) as db:
            assert "review_pending" not in {row[1] for row in db.execute("PRAGMA table_info(approvals)")}
            db.execute("DROP TRIGGER fail_upgrade")
    items = store.pending_reviews()
    assert len(items) == 1
    assert items[0]["id"] == "original" and items[0]["created_at"] == 123
    assert items[0]["boundary"] == "" and items[0]["goal_binding"] is None
    store.review_settled("original")
    assert not store.pending_reviews()


async def test_late_operation_review_does_not_recreate_its_deleted_conversation(review):
    service, request, *_ = review
    await service.sessions.state.delete(request.session_key)
    with pytest.raises(PermissionError, match="replaced conversation"):
        await service.authorize(SimpleNamespace(name="fixture"), {}, request, "Fixture boundary")
    assert await service.sessions.state.read_header(request.session_key) is None
    assert service.inbox.list()["items"] == []
