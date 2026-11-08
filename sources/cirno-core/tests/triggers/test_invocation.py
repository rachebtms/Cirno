"""The command shown in chat and Automations must enqueue a real delivery."""

import os
import shlex
import subprocess

from cirno_core.triggers.invocation import invocation
from cirno_core.triggers.local_store import LocalTriggerStore


def test_generated_invocation_runs_against_the_exact_instance(tmp_path):
    store = LocalTriggerStore(tmp_path / "instance with spaces/state/triggers")
    trigger = store.create(name="Review", channel="websocket", chat_id="research", session_key="websocket:research")
    content = '完成实验；do not interpret $(touch unexpected) "quotes"'
    command = invocation(store.root, trigger.id, content)
    result = subprocess.run(command if os.name == "nt" else shlex.split(command), capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "Queued delivery" in result.stdout
    files = list(store.inbox_dir.glob("*.json"))
    assert len(files) == 1
    import json
    assert json.loads(files[0].read_text())["delivery"]["content"] == content
