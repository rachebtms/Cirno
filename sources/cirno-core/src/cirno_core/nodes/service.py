"""Remote execution and durable jobs using OpenSSH only."""

from __future__ import annotations

import asyncio
import os
import shlex
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from filelock import FileLock
from pydantic import Field

from cirno_core.credentials.service import Credentials
from cirno_core.credentials.ssh import SSHConnection
from cirno_core.credentials.ssh_session import SSHSessionSettings
from cirno_core.nodes.shell import remote_shell
from cirno_core.storage.instance import InstanceData
from cirno_core.utils.atomic_file import atomic_write_text
from cirno_core.utils.cancellation import shield_and_drain
from cirno_core.utils.subprocess import kill_and_drain


class Node(SSHConnection, SSHSessionSettings):
    id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    name: str = Field(min_length=1, max_length=120)


class Nodes:
    def __init__(self, data: InstanceData | None = None, *, actor: str = "owner"):
        self.data = data or InstanceData()
        self.credentials = Credentials(self.data, actor=actor)

    def arguments(self, node: Node, *, transfer=False) -> list[str]:
        args = [
            "scp" if transfer else "ssh",
            "-o",
            "BatchMode=no" if node.auth_method == "password" else "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            "-o",
            "StrictHostKeyChecking=yes",
            "-P" if transfer else "-p",
            str(node.port),
        ]
        if node.host_key:
            known_hosts = self.data.state_dir / "nodes" / (str(node.id) + ".known_hosts")
            known_hosts.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(known_hosts, node.host_key.strip() + "\n")
            args += ["-o", "UserKnownHostsFile=" + str(known_hosts)]
        if node.auth_method == "password":
            args += [
                "-o",
                "PreferredAuthentications=password,keyboard-interactive",
                "-o",
                "PubkeyAuthentication=no",
                "-o",
                "NumberOfPasswordPrompts=1",
            ]
        if node.identity_file and node.auth_method == "key":
            args += ["-i", str(Path(node.identity_file).expanduser())]
        return args

    def list_nodes(self) -> list[dict]:
        return [{"id": record["id"], "name": record["label"], "agent_visible": record["agent_visible"], **ssh.public()}
                for record, ssh in self.credentials.ssh_records() if ssh.node_enabled]

    def catalog(self) -> dict:
        nodes = self.list_nodes()
        allowed = {node["id"] for node in nodes}
        jobs = self.data.list("node_jobs")
        return {"nodes": nodes, "jobs": jobs if self.credentials.actor == "owner"
                else [job for job in jobs if job["node_id"] in allowed]}

    @staticmethod
    def public_node(record: dict) -> dict:
        return {**{key: value for key, value in record.items() if key != "password"},
                "has_password": bool(record.get("password"))}

    def save_node(self, values: dict) -> dict:
        if set(values) - {"id", "credential_id", "working_directory", "init_script", "environment"}:
            raise ValueError("Manage SSH connection details in Credentials")
        if values.get("id") and values.get("credential_id") and values["id"] != values["credential_id"]:
            raise ValueError("A Node must keep its SSH credential identity")
        identifier = values.get("id") or values["credential_id"]
        self.credentials.enroll(identifier, enabled=True, working_directory=values.get("working_directory"),
                                init_script=values.get("init_script"), environment=values.get("environment"))
        return next(node for node in self.list_nodes() if node["id"] == identifier)

    def remove_node(self, identifier: str) -> None:
        self.credentials.enroll(identifier, enabled=False)

    def environment(self, password: str | None) -> dict[str, str] | None:
        environment = None
        if password is not None:
            helper = self.data.state_dir / "nodes" / "askpass"
            helper.parent.mkdir(parents=True, exist_ok=True)
            script = "#!/bin/sh\nprintf '%s\\n' \"$CIRNO_NODE_PASSWORD\"\n"
            with FileLock(helper.with_suffix(".lock"), timeout=10, mode=0o600):
                try:
                    current = helper.read_text(encoding="utf-8")
                except FileNotFoundError:
                    current = None
                if current != script:
                    atomic_write_text(helper, script)
                helper.chmod(0o700)
            environment = {
                **os.environ,
                "SSH_ASKPASS": str(helper),
                "SSH_ASKPASS_REQUIRE": "force",
                "DISPLAY": "cirno:0",
                "CIRNO_NODE_PASSWORD": password,
            }
        return environment

    async def _run(
        self,
        args: list[str],
        timeout: int = 120,
        *,
        password: str | None = None,
        include_stderr: bool = False,
    ) -> str:
        environment = await asyncio.to_thread(self.environment, password) if password is not None else None
        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=environment,
            start_new_session=os.name == "posix",
        )

        async def tail(stream, limit):
            buffer = bytearray()
            while chunk := await stream.read(16384):
                buffer.extend(chunk)
                if len(buffer) > limit:
                    del buffer[:-limit]
            return bytes(buffer)

        try:
            async with asyncio.timeout(timeout):
                out, error = await asyncio.gather(
                    tail(process.stdout, 64000), tail(process.stderr, 16000)
                )
                await process.wait()
        except BaseException:
            await kill_and_drain(process, process_group=os.name == "posix")
            raise
        if process.returncode:
            raise RuntimeError(
                error.decode(errors="replace") or f"OpenSSH exited with {process.returncode}"
            )
        return out.decode(errors="replace") + (
            ("\n" if out else "") + error.decode(errors="replace")
            if include_stderr and error
            else ""
        )

    async def scan_host_key(self, host: str, port: int = 22) -> dict:
        # A scan is untrusted until the user compares and saves the fingerprint.
        node = Node(name="scan", host=host, port=port, username="scan")
        key = await self._run(["ssh-keyscan", "-T", "10", "-p", str(node.port), node.host], 15)
        if not key.strip():
            raise RuntimeError("The server returned no SSH host key")
        process = await asyncio.create_subprocess_exec(
            "ssh-keygen",
            "-lf",
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
        )
        out, error = await process.communicate(key.encode())
        if process.returncode:
            raise RuntimeError(error.decode(errors="replace"))
        return {"host_key": key, "fingerprints": out.decode()}

    def node(self, node_id: str) -> Node:
        record, ssh = self.credentials.connection(node_id)
        if not ssh.node_enabled:
            raise ValueError("This SSH credential is not enabled as an SSH Node")
        return Node(id=node_id, name=record["label"],
                    **ssh.model_dump(exclude={"node_enabled"}))

    async def execute(self, node_id: str, command: str, *, timeout=120, include_stderr=True, initialize=True) -> str:
        node = await asyncio.to_thread(self.node, node_id)
        script = remote_shell(node, command) if initialize else "sh -lc " + shlex.quote(command)
        return await self._run(
            [
                *(await asyncio.to_thread(self.arguments, node)),
                "--",
                f"{node.username}@{node.host}",
                script,
            ],
            timeout,
            password=node.password if node.auth_method == "password" else None,
            include_stderr=include_stderr,
        )

    async def transfer(
        self, node_id: str, local_path: str, remote_path: str, *, download=False
    ) -> str:
        node = await asyncio.to_thread(self.node, node_id)
        local = await asyncio.to_thread(lambda: str(Path(local_path).expanduser().resolve()))
        host = f"[{node.host}]" if ":" in node.host else node.host
        remote = f"{node.username}@{host}:{remote_path}"
        paths = [remote, local] if download else [local, remote]
        await self._run(
            [*(await asyncio.to_thread(self.arguments, node, transfer=True)), "--", *paths],
            password=node.password if node.auth_method == "password" else None,
        )
        return "File transferred."

    async def start_job(self, node_id: str, command: str) -> dict:
        node = await asyncio.to_thread(self.node, node_id)
        job = {
            "id": uuid4().hex,
            "node_id": node_id,
            "command": command,
            "state": "submitting",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        job_id = job["id"]
        directory = f'"$HOME/.cirno/jobs/{job_id}"'
        # mkdir is the submission boundary; a retry cannot silently duplicate this job.
        wrapper = (
            remote_shell(node, command)
            + '; result=$?; printf "%s" "$result" > '
            + directory
            + "/exit"
        )
        script = (
            f'command -v setsid >/dev/null || exit 69; mkdir -p "$HOME/.cirno/jobs"; '
            f"mkdir {directory} || exit 70; "
            f"nohup setsid sh -c {shlex.quote(wrapper)}"
            f" >{directory}/output.log 2>&1 </dev/null & pid=$!; "
            f'printf "%s" "$pid" >{directory}/pid; printf "%s" "$pid"'
        )

        try:
            await self._save_job(job)
        except asyncio.CancelledError as exc:
            await self._save_job({**job, "state": "submission_unknown", "error": str(exc) or type(exc).__name__})
            raise

        try:
            pid = int((await self.execute(node_id, script, include_stderr=False, initialize=False)).strip())
            if pid <= 0:
                raise ValueError("SSH returned an invalid job PID")
        except (Exception, asyncio.CancelledError) as exc:
            await self._save_job({**job, "state": "submission_unknown", "error": str(exc) or type(exc).__name__})
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise RuntimeError(
                f"Job {job_id} submission unconfirmed; inspect it before submitting again: {exc}"
            ) from exc
        return await self._save_job({**job, "pid": pid, "state": "running"})

    async def _save_job(self, job: dict) -> dict:
        return await shield_and_drain(asyncio.to_thread(self.data.save, "node_jobs", job))

    async def inspect_job(self, job_id: str, *, stop=False) -> dict:
        job = await asyncio.to_thread(self.data.get, "node_jobs", job_id)
        directory = f'"$HOME/.cirno/jobs/{job_id}"'
        alive = (
            f'[ -f {directory}/pid ] && pid=$(cat {directory}/pid) && '
            f'kill -0 "$pid" 2>/dev/null && ps -ww -p "$pid" -o args= | grep -F {shlex.quote(job_id)} >/dev/null'
        )
        stop_script = ""
        if stop:
            stop_script = (
                f'if [ ! -f {directory}/exit ] && {alive}; then '
                f'kill -TERM -"$pid" && touch {directory}/stop-requested; fi; '
            )
        result = await self.execute(
            job["node_id"],
            stop_script + f'if [ -f {directory}/exit ]; then printf "EXIT:"; cat {directory}/exit; '
            f'elif {alive}; then printf RUNNING; '
            f'elif [ -f {directory}/stop-requested ]; then printf STOPPED; else printf UNKNOWN; fi; printf "\\n"; tail -c 60000 {directory}/output.log',
            initialize=False,
        )
        status, _, output = result.partition("\n")
        state = (
            "completed"
            if status == "EXIT:0"
            else "failed"
            if status.startswith("EXIT:")
            else "running"
            if status == "RUNNING"
            else "stopped"
            if status == "STOPPED"
            else "unknown"
        )
        return await self._save_job(
            {
                **job,
                "state": state,
                "output": output,
                "stop_requested": stop or job.get("stop_requested", False),
            },
        )
