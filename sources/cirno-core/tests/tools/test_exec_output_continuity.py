"""Wait targets must come from contiguous retained output, including after cancellation."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from cirno_core.processes.sessions import ExecSessionManager
from cirno_core.processes.sessions.contracts import SessionPoll
from cirno_core.processes.sessions.observer import observe_session
from cirno_core.processes.sessions.session import ExecSession

from sources.development.testing.processes import cancel_session_tasks, fake_session_process


def setup():
    process, _ = fake_session_process()
    session = ExecSession(session_id="fixture", process=process, command="fake", cwd=".", timeout=None)
    manager = ExecSessionManager()
    manager._sessions["fixture"] = session
    return manager, session


async def observe(manager, target="READY", timeout=0):
    return await observe_session(manager, session_id="fixture", input=None, close_stdin=False,
                                 wait_for=target, until_exit=False, timeout_ms=timeout)


@pytest.mark.parametrize("stream", ["_stdout", "_stderr"])
async def test_truncated_stream_does_not_manufacture_a_wait_target(stream):
    manager, session = setup()
    # stderr's visible label takes eight characters of the response head.
    padding = 24997 if stream == "_stdout" else 24989
    middle = "" if stream == "_stdout" else "X" * 8
    original = "A" * padding + "REA" + middle + "[omitted]" + "DY" + "B" * 24998
    assert "READY" not in original
    getattr(session, stream).append(original)
    try:
        result = await observe(manager)
        assert not result.matched
        assert result.poll.truncated_chars > 0
    finally:
        await cancel_session_tasks(session)


@pytest.mark.parametrize("target_at", ["head", "tail"])
async def test_a_real_target_in_retained_output_still_matches(target_at):
    manager, session = setup()
    session._stdout.append("READY" + "A" * 60000 if target_at == "head" else "A" * 60000 + "READY")
    try:
        assert (await observe(manager)).matched
    finally:
        await cancel_session_tasks(session)


async def test_target_can_span_two_untruncated_polls():
    polls = iter([SessionPoll("REA", False, None), SessionPoll("DY", True, 0)])
    manager = type("Manager", (), {"write": AsyncMock(side_effect=lambda **kwargs: next(polls))})()
    assert (await observe(manager, timeout=1000)).matched


async def test_cancelled_aggregate_retains_its_output_gap_for_the_next_wait():
    manager, session = setup()
    original = "A" * 4997 + "REA" + "X" * 10000 + "DY" + "B" * 4998
    assert "READY" not in original
    session._stdout.append(original)
    poll = session.poll
    entered = asyncio.Event()
    first = True

    async def waiting(_wait, maximum, **kwargs):
        nonlocal first
        if first:
            first = False
            return await poll(0, maximum, **kwargs)
        entered.set()
        await asyncio.Event().wait()

    session.poll = waiting
    task = asyncio.create_task(observe(manager, target="never", timeout=1000))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        session.poll = poll
        result = await observe(manager)
        assert not result.matched
        assert result.poll.truncated_chars == 10000
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await cancel_session_tasks(session)


@pytest.mark.parametrize("first,expected", [
    (SessionPoll("XREA", False, None, output_gaps=(1,)), True),
    (SessionPoll("REA", False, None, output_gaps=(3,)), False),
])
async def test_only_the_contiguous_tail_can_continue_into_the_next_poll(first, expected):
    polls = iter([first, SessionPoll("DY", True, 0)])
    manager = type("Manager", (), {"write": AsyncMock(side_effect=lambda **kwargs: next(polls))})()
    assert (await observe(manager, timeout=1000)).matched is expected


async def test_response_clipping_alone_does_not_join_two_unrelated_output_regions():
    manager, session = setup()
    text = "A" * 24997 + "REA" + "X" * 10009 + "DY" + "B" * 4989
    assert len(text) == 40000 and "READY" not in text
    session._stdout.append(text)
    session._stderr.append("Z" * 20000)
    try:
        assert not (await observe(manager)).matched
    finally:
        await cancel_session_tasks(session)


def test_repeated_buffer_trimming_preserves_only_visible_gap_offsets():
    from cirno_core.processes.sessions.buffer import BoundedOutputBuffer

    buffer = BoundedOutputBuffer(10)
    buffer.append("012345", gaps=(2,))
    buffer.append("6789ABCDEF", gaps=(1,))
    buffer.append("GH", gaps=(1,))
    assert buffer.drain_with_gaps() == ("01234DEFGH", 8, (2, 5, 9))
    buffer.append("new")
    assert buffer.drain_with_gaps() == ("new", 0, ())


@pytest.mark.parametrize("limit,text,dropped,gaps", [
    (0, "", 6, (0,)), (1, "F", 5, (0,)), (4, "ABEF", 2, (2,)), (6, "ABCDEF", 0, ()),
])
def test_small_output_budgets_keep_exact_text_and_discontinuities(limit, text, dropped, gaps):
    from cirno_core.processes.sessions.buffer import BoundedOutputBuffer, truncate_output_with_gaps

    buffer = BoundedOutputBuffer(limit)
    buffer.append("ABC")
    buffer.append("DEF")
    assert buffer.drain_with_gaps() == (text, dropped, gaps)
    assert truncate_output_with_gaps("ABCDEF", limit) == (text, dropped, gaps)
