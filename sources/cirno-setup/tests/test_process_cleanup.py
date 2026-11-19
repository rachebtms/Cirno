"""Installer deadlines also stop subprocesses launched by a package manager."""

import os
import subprocess
import sys
import time

import pytest
from cirno_setup.context import Context
from cirno_setup.policy import Policy


@pytest.mark.skipif(os.name != 'posix', reason='Container setup uses POSIX process groups')
@pytest.mark.parametrize('check', [False, True])
def test_timeout_does_not_leave_an_install_child_writing_after_failure(tmp_path, check):
    context = Context(tmp_path, tmp_path, Policy(timeout_seconds=0.3))
    completed = tmp_path / 'child-effect'
    child = f'import time; from pathlib import Path; time.sleep(0.5); Path({str(completed)!r}).touch()'
    parent = f'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",{child!r}]); print("spawned",flush=True); time.sleep(3)'
    command = [sys.executable, '-c', parent]
    if check:
        assert context.inspect(command).returncode != 0
    else:
        with pytest.raises(subprocess.TimeoutExpired):
            context.run(command, capture=True)
    time.sleep(0.55)  # Let the tiny child finish even against the unfixed implementation.
    assert not completed.exists(), 'Timed-out setup left a child performing installation effects'


@pytest.mark.skipif(os.name != 'posix', reason='Container setup uses POSIX process groups')
def test_timeout_stops_pipe_holding_child_after_its_parent_has_already_exited(tmp_path):
    context = Context(tmp_path, tmp_path, Policy(timeout_seconds=0.3))
    completed = tmp_path / 'orphan-effect'
    child = f'import time; from pathlib import Path; time.sleep(0.5); Path({str(completed)!r}).touch()'
    parent = f'import subprocess,sys; subprocess.Popen([sys.executable,"-c",{child!r}]); print("spawned",flush=True)'
    with pytest.raises(subprocess.TimeoutExpired) as error:
        context.run([sys.executable, '-c', parent], capture=True)
    assert 'spawned' in error.value.output
    time.sleep(0.55)
    assert not completed.exists()


@pytest.mark.skipif(os.name != 'posix', reason='Container setup uses POSIX process groups')
def test_user_interrupt_cleans_up_and_remains_an_interrupt(monkeypatch):
    import signal
    from unittest.mock import MagicMock

    from cirno_setup.process import run_command

    process = MagicMock(pid=12345)
    process.communicate.side_effect = [KeyboardInterrupt(), ('partial', 'diagnostic')]
    owner = MagicMock()
    owner.__enter__.return_value = process
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: owner)
    kill = MagicMock()
    monkeypatch.setattr(os, 'killpg', kill)
    with pytest.raises(KeyboardInterrupt):
        run_command(['fixture'], env={}, timeout=None, capture_output=True)
    kill.assert_called_once_with(process.pid, signal.SIGKILL)
    assert process.communicate.call_count == 2


@pytest.mark.skipif(os.name != "posix", reason="Container setup uses POSIX process groups")
@pytest.mark.parametrize("check", [False, True])
@pytest.mark.parametrize("returncode", [0, 7])
def test_command_exit_also_settles_its_failed_process_group(monkeypatch, check, returncode):
    import signal
    from unittest.mock import MagicMock

    from cirno_setup.process import run_command

    process = MagicMock(pid=12345, returncode=returncode)
    process.communicate.return_value = ("installer output", "installer diagnostic")
    owner = MagicMock()
    owner.__enter__.return_value = process
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: owner)
    kill = MagicMock()
    monkeypatch.setattr(os, "killpg", kill)
    if check and returncode:
        with pytest.raises(subprocess.CalledProcessError) as error:
            run_command(["fixture-install"], env={}, timeout=None, check=True, capture_output=True)
        assert error.value.returncode == 7
        assert error.value.output == "installer output"
        assert error.value.stderr == "installer diagnostic"
    else:
        result = run_command(["fixture-install"], env={}, timeout=None, check=check, capture_output=True)
        assert result.returncode == returncode
        assert result.stdout == "installer output"
    if returncode:
        kill.assert_called_once_with(process.pid, signal.SIGKILL)
    else:
        kill.assert_not_called()


@pytest.mark.skipif(os.name != "posix", reason="Container setup uses POSIX process groups")
def test_missing_failed_process_group_preserves_the_original_exit_error(monkeypatch):
    from unittest.mock import MagicMock

    from cirno_setup.process import run_command

    process = MagicMock(pid=12345, returncode=9)
    process.communicate.return_value = ("partial output", "original failure")
    owner = MagicMock()
    owner.__enter__.return_value = process
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: owner)
    monkeypatch.setattr(os, "killpg", MagicMock(side_effect=ProcessLookupError))
    with pytest.raises(subprocess.CalledProcessError) as error:
        run_command(["fixture-install"], env={}, timeout=None, check=True, capture_output=True)
    assert error.value.returncode == 9 and error.value.stderr == "original failure"
