from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from cirno_core.agent.tools.exec_session import ExecSessionTool
from cirno_core.agent.tools.shell import ExecTool
from cirno_core.processes.sessions import ExecSessionManager
from cirno_core.processes.sessions.buffer import BoundedOutputBuffer, truncate_output
from cirno_core.processes.sessions.contracts import MAX_OUTPUT_CHARS, SessionPoll
from cirno_core.processes.sessions.session import ExecSession

from sources.development.testing.processes import (
    cancel_session_tasks,
    extract_session_id,
    fake_session_process,
    python_command,
)


def test_bounded_output_buffer_keeps_head_tail_and_exact_drop_count():
    buffer = BoundedOutputBuffer(10)

    buffer.append("012345")
    buffer.append("6789ABCDEF")

    assert buffer.retained_chars == 10
    assert buffer.drain() == ("01234BCDEF", 6)
    assert buffer.retained_chars == 0


async def test_exec_session_preserves_utf8_across_stdout_and_stderr_chunks():
    stdout = asyncio.StreamReader()
    stderr = asyncio.StreamReader()
    stdout_bytes = b"a" * 4095 + "你好🙂".encode() + b"\xe2\x82"
    stderr_bytes = b"b" * 4094 + "🙂é".encode() + b"\xff"
    stdout.feed_data(stdout_bytes[:4096])
    stderr.feed_data(stderr_bytes[:4096])
    process, exited = fake_session_process(stdout=stdout, stderr=stderr)
    session = ExecSession(
        session_id="utf8-output",
        process=process,
        command="test",
        cwd=".",
        timeout=None,
    )

    try:
        await asyncio.sleep(0)
        stdout.feed_data(stdout_bytes[4096:])
        stderr.feed_data(stderr_bytes[4096:])
        stdout.feed_eof()
        stderr.feed_eof()
        process.returncode = 0
        exited.set()
        await asyncio.wait_for(session._completion_task, timeout=2)

        assert session._stdout.drain() == ("a" * 4095 + "你好🙂\ufffd", 0)
        assert session._stderr.drain() == ("b" * 4094 + "🙂é\ufffd", 0)
    finally:
        await cancel_session_tasks(session)


def test_exec_session_bounds_unpolled_stdout_and_stderr(tmp_path):
    async def run() -> tuple[int, int, str, int]:
        manager = ExecSessionManager()
        tool = ExecTool(working_dir=str(tmp_path), timeout=5, session_manager=manager)
        command = python_command(
            "import sys,time; time.sleep(0.05); "
            "sys.stdout.write('OUT_HEAD' + 'o' * 200000 + 'OUT_TAIL'); "
            "sys.stderr.write('ERR_HEAD' + 'e' * 200000 + 'ERR_TAIL')"
        )

        initial = await tool.execute(
            command=command,
            yield_time_ms=0,
            max_output_chars=1000,
        )
        sid = extract_session_id(initial)
        session = manager._sessions[sid]
        await asyncio.wait_for(session._completion_task, timeout=15)
        assert session.finish_reason == "exit"
        assert session.finished_at is not None
        retained_stdout = session._stdout.retained_chars
        retained_stderr = session._stderr.retained_chars
        poll = await manager.write(
            session_id=sid,
            chars=None,
            close_stdin=False,
            terminate=False,
            yield_time_ms=0,
            max_output_chars=1000,
        )
        return retained_stdout, retained_stderr, poll.output, poll.truncated_chars

    retained_stdout, retained_stderr, output, truncated_chars = asyncio.run(run())

    assert retained_stdout == 50000
    assert retained_stderr == 50000
    assert output.startswith("OUT_HEAD")
    assert output.endswith("ERR_TAIL")
    assert truncated_chars > 390000


def test_exec_session_wait_for_keeps_aggregate_within_output_budget():
    async def run() -> str:
        manager = SimpleNamespace(
            write=AsyncMock(side_effect=[
                SessionPoll(output="HEAD" + "a" * 5996, done=False, exit_code=None),
                SessionPoll(output="b" * 6000, done=False, exit_code=None),
                SessionPoll(output="c" * 5994 + "TARGET", done=False, exit_code=None),
            ])
        )
        tool = ExecSessionTool(manager=manager)
        return await tool.execute(
            session_id="session",
            input=None,
            close_stdin=False,
            wait_for="TARGET",
            until_exit=False,
            timeout_ms=1000,
        )

    result = asyncio.run(run())

    assert result.startswith("HEAD")
    assert "Wait target not observed" not in result
    assert "(8,000 chars truncated from output)" in result
    assert len(result.partition("\n")[0]) == 10_000


def test_exec_session_wait_for_searches_before_response_truncation():
    async def run() -> tuple[str, list[int]]:
        output = "A" * 15000 + "TARGET" + "B" * 15000
        observed_limits: list[int] = []

        async def write(
            *,
            session_id: str,
            chars: str | None,
            close_stdin: bool,
            terminate: bool,
            yield_time_ms: int,
            max_output_chars: int,
            owner_session_key: str | None,
        ) -> SessionPoll:
            del session_id, chars, close_stdin, terminate, yield_time_ms, owner_session_key
            observed_limits.append(max_output_chars)
            visible, truncated = truncate_output(output, max_output_chars)
            return SessionPoll(
                output=visible,
                done=True,
                exit_code=0,
                truncated_chars=truncated,
            )

        manager = SimpleNamespace(write=AsyncMock(side_effect=write))
        tool = ExecSessionTool(manager=manager)
        result = await tool.execute(
            session_id="session",
            input=None,
            close_stdin=False,
            wait_for="TARGET",
            until_exit=False,
            timeout_ms=1000,
        )
        return result, observed_limits

    result, observed_limits = asyncio.run(run())

    assert observed_limits == [MAX_OUTPUT_CHARS]
    assert "Wait target not observed" not in result
    assert "(20,006 chars truncated from output)" in result
    assert len(result.partition("\n")[0]) == 10_000
