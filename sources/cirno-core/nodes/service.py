"""Remote execution and durable jobs using OpenSSH only."""

from __future__ import annotations

import asyncio
import os
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from cirno.storage.instance import InstanceData
from pydantic import BaseModel, Field


class Node(BaseModel):
    id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    name: str = Field(min_length=1, max_length=120)
    host: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9.:%_-]*$")
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
    auth_method: Literal["key", "password"] = "key"
    password: str = Field(default="", repr=False)
    identity_file: str = ""
    working_directory: str = "."
    host_key: str = ""


class Nodes:
    def __init__(self, data: InstanceData | None = None):
        self.data = data or InstanceData()

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
            known_hosts = self.data.home / "nodes" / (str(node.id) + ".known_hosts")
            known_hosts.parent.mkdir(parents=True, exist_ok=True)
            known_hosts.write_text(node.host_key.strip() + "\n", encoding="utf-8")
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
        return [self.public_node(record) for record in self.data.list("nodes")]

    @staticmethod
    def public_node(record: dict) -> dict:
        return {
            **{key: value for key, value in record.items() if key != "password"},
            "auth_method": record.get("auth_method", "key"),
            "has_password": bool(record.get("password")),
        }

    def save_node(self, values: dict) -> dict:
        incoming = dict(values)
        if incoming.get("id") and not incoming.get("password"):
            incoming["password"] = self.data.get("nodes", incoming["id"]).get("password", "")
        node = Node.model_validate(incoming)
        if node.auth_method == "password" and not node.password:
            raise ValueError("A password is required for password authentication")
        if node.auth_method == "key":
            node.password = ""
        return self.public_node(self.data.save("nodes", node.model_dump()))

    async def _run(
        self,
        args: list[str],
        timeout: int = 120,
        *,
        password: str | None = None,
        include_stderr: bool = False,
    ) -> str:
        environment = None
        if password is not None:
            helper = self.data.home / "nodes" / "askpass"
            helper.parent.mkdir(parents=True, exist_ok=True)
            helper.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$CIRNO_NODE_PASSWORD\"\n", encoding="utf-8"
            )
            helper.chmod(0o700)
            environment = {
                **os.environ,
                "SSH_ASKPASS": str(helper),
                "SSH_ASKPASS_REQUIRE": "force",
                "DISPLAY": "cirno:0",
                "CIRNO_NODE_PASSWORD": password,
            }
        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=environment
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
            if process.returncode is None:
                process.kill()
                await process.wait()
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
        return Node.model_validate(self.data.get("nodes", node_id))

    async def execute(self, node_id: str, command: str, *, timeout=120, include_stderr=True) -> str:
        node = self.node(node_id)
        script = f"cd {shlex.quote(node.working_directory)} && {command}"
        return await self._run(
            [
                *self.arguments(node),
                "--",
                f"{node.username}@{node.host}",
                "sh -lc " + shlex.quote(script),
            ],
            timeout,
            password=node.password if node.auth_method == "password" else None,
            include_stderr=include_stderr,
        )

    async def transfer(
        self, node_id: str, local_path: str, remote_path: str, *, download=False
    ) -> str:
        node = self.node(node_id)
        local = str(Path(local_path).expanduser().resolve())
        remote = f"{node.username}@{node.host}:{remote_path}"
        paths = [remote, local] if download else [local, remote]
        await self._run(
            [*self.arguments(node, transfer=True), "--", *paths],
            password=node.password if node.auth_method == "password" else None,
        )
        return "File transferred."

    async def start_job(self, node_id: str, command: str) -> dict:
        job = self.data.save(
            "node_jobs",
            {
                "node_id": node_id,
                "command": command,
                "state": "submitting",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        job_id = job["id"]
        directory = f'"$HOME/.cirno/jobs/{job_id}"'
        # mkdir is the submission boundary; a retry cannot silently duplicate this job.
        wrapper = (
            "sh -c "
            + shlex.quote(command)
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
            pid = int((await self.execute(node_id, script, include_stderr=False)).strip())
            if pid <= 0:
                raise ValueError("SSH returned an invalid job PID")
        except (Exception, asyncio.CancelledError) as exc:
            self.data.save("node_jobs", {**job, "state": "submission_unknown", "error": str(exc) or type(exc).__name__})
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise RuntimeError(
                f"Job {job_id} submission unconfirmed; inspect it before submitting again: {exc}"
            ) from exc
        return self.data.save("node_jobs", {**job, "pid": pid, "state": "running"})

    async def inspect_job(self, job_id: str, *, stop=False) -> dict:
        job = self.data.get("node_jobs", job_id)
        directory = f'"$HOME/.cirno/jobs/{job_id}"'
        stop_script = ""
        if stop:
            stop_script = (
                f"if [ ! -f {directory}/exit ]; then pid=$(cat {directory}/pid); "
                f'ps -p "$pid" -o args= | grep -F {shlex.quote(job_id)} >/dev/null && kill -TERM -"$pid" && touch {directory}/stop-requested; fi; '
            )
        result = await self.execute(
            job["node_id"],
            stop_script + f'if [ -f {directory}/exit ]; then printf "EXIT:"; cat {directory}/exit; '
            f'elif [ -f {directory}/pid ] && kill -0 "$(cat {directory}/pid)" 2>/dev/null; then printf RUNNING; '
            f'elif [ -f {directory}/stop-requested ]; then printf STOPPED; else printf UNKNOWN; fi; printf "\\n"; tail -c 60000 {directory}/output.log',
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
        return self.data.save(
            "node_jobs",
            {
                **job,
                "state": state,
                "output": output,
                "stop_requested": stop or job.get("stop_requested", False),
            },
        )
