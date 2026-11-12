"""Remote execution and durable jobs using OpenSSH only."""

from __future__ import annotations

import asyncio
import os
import shlex
import time
from pathlib import Path

from filelock import FileLock
from pydantic import Field

from cirno_core.credentials.service import Credentials
from cirno_core.credentials.ssh import SSHConnection
from cirno_core.credentials.ssh_session import SSHSessionSettings
from cirno_core.nodes.shell import remote_shell
from cirno_core.nodes.jobs import NodeJobs
from cirno_core.nodes.commands import CommandResult, SSHCommandTimeout, SSHProcessError, command_envelope, command_result
from cirno_core.nodes.policy import read_policy
from cirno_core.storage.instance import InstanceData
from cirno_core.utils.atomic_file import atomic_write_text
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
            "-o", "ConnectionAttempts=3",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=3",
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
        return [{"id": record["id"], "name": record["label"], "agent_visible": record["agent_visible"],
                 **(ssh.agent_metadata() if self.credentials.actor == "agent" else ssh.public())}
                for record, ssh in self.credentials.ssh_records() if ssh.node_enabled]

    def catalog(self) -> dict:
        nodes = self.list_nodes()
        allowed = {node["id"] for node in nodes}
        jobs = self.data.list("node_jobs")
        if self.credentials.actor == "agent":
            jobs = [{**{key: job[key] for key in ("id", "node_id", "state", "created_at", "pid", "stop_requested", "checked_at", "finished_at", "exit_code") if key in job},
                     "status_check_failed": bool(job.get("check_error"))}
                    for job in jobs if job["node_id"] in allowed]
        return {"nodes": nodes, "jobs": jobs, "job_settings": read_policy(self.data).model_dump()}

    @staticmethod
    def public_node(record: dict) -> dict:
        return Node.model_validate(record).agent_metadata()

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
        result = (await self._run_result(args, timeout, password=password)).checked()
        return result.output if include_stderr else result.stdout

    async def _run_result(
        self, args: list[str], timeout: int = 120, *, password: str | None = None,
    ) -> CommandResult:
        environment = await asyncio.to_thread(self.environment, password) if password is not None else None
        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=environment,
            start_new_session=os.name == "posix",
        )

        output_buffer, error_buffer = bytearray(), bytearray()

        async def tail(stream, buffer, limit):
            while chunk := await stream.read(16384):
                buffer.extend(chunk)
                if len(buffer) > limit:
                    del buffer[:-limit]

        try:
            async with asyncio.timeout(timeout):
                await asyncio.gather(
                    tail(process.stdout, output_buffer, 64000), tail(process.stderr, error_buffer, 16000)
                )
                await process.wait()
        except TimeoutError as error:
            await kill_and_drain(process, process_group=os.name == "posix")
            raise SSHCommandTimeout(CommandResult(
                output_buffer.decode(errors="replace"), error_buffer.decode(errors="replace"), process.returncode,
                f"SSH command timed out after {timeout:g} seconds.",
            )) from error
        except BaseException:
            await kill_and_drain(process, process_group=os.name == "posix")
            raise
        return CommandResult(output_buffer.decode(errors="replace"), error_buffer.decode(errors="replace"), process.returncode)

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

    async def read_status(self, node_id: str, command: str, *, timeout=120) -> str:
        """Reconnect once for an internal read-only status query, within one deadline."""
        deadline = time.monotonic() + timeout
        async with asyncio.timeout(timeout):
            try:
                return await self.execute(node_id, command, timeout=timeout, initialize=False, include_stderr=False)
            except SSHProcessError as error:
                if not error.reconnectable or deadline - time.monotonic() <= 0.5:
                    raise
                await asyncio.sleep(0.5)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("SSH status query deadline exceeded during reconnect delay") from error
                return await self.execute(node_id, command, timeout=remaining, initialize=False, include_stderr=False)

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

    async def execute_command(self, node_id: str, command: str, *, timeout=120) -> CommandResult:
        node = await asyncio.to_thread(self.node, node_id)
        script, marker = command_envelope(remote_shell(node, command))
        try:
            transport = await self._run_result(
                [*(await asyncio.to_thread(self.arguments, node)), "--", f"{node.username}@{node.host}", script],
                timeout, password=node.password if node.auth_method == "password" else None,
            )
        except SSHCommandTimeout as error:
            transport = error.result
        return command_result(transport, marker)

    async def start_job(self, node_id: str, command: str) -> dict:
        return await NodeJobs(self).start_job(node_id, command)

    async def inspect_job(self, job_id: str, *, stop=False) -> dict:
        return await NodeJobs(self).inspect_job(job_id, stop=stop)
