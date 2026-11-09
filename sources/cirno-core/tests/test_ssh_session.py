"""SSH startup runs in the command's shell without interpolation or lost exports."""
import asyncio
import shlex

import pytest
from pydantic import ValidationError
from cirno_core.credentials.ssh_session import SSHSessionSettings
from cirno_core.credentials.service import Credentials
from cirno_core.nodes.shell import remote_shell
from cirno_core.storage.instance import InstanceData


async def run(command):
    process = await asyncio.create_subprocess_exec("/bin/sh", "-c", command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()
    return process.returncode, stdout.decode(), stderr.decode()


async def test_remote_command_keeps_directory_exports_functions_and_literal_values(tmp_path):
    directory = tmp_path / "research project"; directory.mkdir()
    script = directory / "initialize env.sh"
    script.write_text('export FROM_INIT="ready"\nselected_card() { printf "%s" "$CUDA_VISIBLE_DEVICES"; }\nprintf "initialization output\\n"\n')
    settings = SSHSessionSettings(working_directory=str(directory), init_script=script.name, environment={"CUDA_VISIBLE_DEVICES": "2", "LITERAL": "$(touch should-not-exist); 'x'\nsecond line"})
    code = 'printf "%s\\n" "$PWD" "$FROM_INIT" "$LITERAL"; selected_card'
    status, stdout, stderr = await run(remote_shell(settings, code))
    assert status == 0
    assert stdout == f"{directory}\nready\n$(touch should-not-exist); 'x'\nsecond line\n2"
    assert "initialization output" in stderr and not (directory / "should-not-exist").exists()


async def test_failed_startup_prevents_command_execution(tmp_path):
    sentinel = tmp_path / "ran"
    script = tmp_path / "failed.sh"; script.write_text("return 23\n")
    status, _, _ = await run(remote_shell(SSHSessionSettings(working_directory=str(tmp_path), init_script=str(script)), "touch " + shlex.quote(str(sentinel))))
    assert status == 23 and not sentinel.exists()
    status, _, _ = await run(remote_shell(SSHSessionSettings(working_directory=str(tmp_path / "missing")), "touch " + shlex.quote(str(sentinel))))
    assert status != 0 and not sentinel.exists()


def test_node_startup_survives_credential_edits_and_enrollment(tmp_path):
    credentials = Credentials(InstanceData(tmp_path))
    record = credentials.save(label="GPU", kind="ssh", ssh={"host": "localhost", "username": "owner", "init_script": "~/activate.sh", "environment": {"CUDA_VISIBLE_DEVICES": "3"}})
    assert credentials.ssh(record["id"]).node_enabled is False
    credentials.enroll(record["id"], enabled=True, working_directory="~/research")
    credentials.save(id=record["id"], label="GPU renamed", kind="ssh", ssh={"port": 2222})
    saved = credentials.ssh(record["id"])
    assert saved.working_directory == "~/research" and saved.init_script == "~/activate.sh"
    assert saved.environment == {"CUDA_VISIBLE_DEVICES": "3"} and saved.port == 2222
    assert saved.node_enabled is True
    for variables in ({"CUDA-DEVICE": "1"}, {"CUDA_VISIBLE_DEVICES": "bad\0value"}):
        with pytest.raises(ValidationError):
            SSHSessionSettings(environment=variables)


async def test_background_job_initializes_once_and_inspection_does_not_repeat_it(tmp_path, monkeypatch):
    import shutil
    from cirno_core.nodes.service import Nodes
    if shutil.which("setsid") is None:
        pytest.skip("Persistent Node jobs require setsid on the remote Linux host")
    remote_home = tmp_path / "remote"; remote_home.mkdir()
    script = tmp_path / "activate.sh"
    marker = tmp_path / "initialized"
    script.write_text(f"echo init >> {shlex.quote(str(marker))}\nexport ACTIVATED=ready\nprintf 'startup output\\n'\n")
    nodes = Nodes(InstanceData(tmp_path / "state"))
    saved = nodes.credentials.save(label="GPU", kind="ssh", ssh={"host": "localhost", "username": "owner", "init_script": str(script), "environment": {"CUDA_VISIBLE_DEVICES": "3"}}, node_enabled=True, working_directory=str(tmp_path))
    async def local_remote(args, timeout=120, **kwargs):
        # Substitute the test host's isolated HOME at the SSH transport boundary.
        status, stdout, stderr = await run(args[-1].replace("$HOME", str(remote_home)))
        assert status == 0, stderr
        return stdout + (stderr if kwargs.get("include_stderr") else "")
    monkeypatch.setattr(nodes, "_run", local_remote)
    job = await nodes.start_job(saved["id"], 'printf "%s/%s/%s\\n" "$PWD" "$ACTIVATED" "$CUDA_VISIBLE_DEVICES"')
    async with asyncio.timeout(5):
        while True:
            current = await nodes.inspect_job(job["id"])
            if current["state"] != "running": break
            await asyncio.sleep(.01)
    assert current["state"] == "completed"
    assert f"{tmp_path}/ready/3" in current["output"] and "startup output" in current["output"]
    await nodes.inspect_job(job["id"])
    assert marker.read_text() == "init\n"
