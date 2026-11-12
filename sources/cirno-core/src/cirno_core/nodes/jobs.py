"""Durable remote job submission and status reconciliation."""

from __future__ import annotations

import asyncio
import shlex
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from cirno_core.nodes.shell import remote_shell
from cirno_core.nodes.policy import TERMINAL_JOB_STATES
from cirno_core.utils.cancellation import shield_and_drain

if TYPE_CHECKING:
    from cirno_core.nodes.service import Nodes


def status_command(job_id: str, *, stop=False, output=True) -> str:
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
    return (
        stop_script + f'cirno_job_running=0; if {alive}; then cirno_job_running=1; fi; '
        f'if [ -f {directory}/exit ]; then printf "EXIT:"; cat {directory}/exit; '
        'elif [ "$cirno_job_running" = 1 ]; then printf RUNNING; '
        f'elif [ -f {directory}/stop-requested ]; then printf STOPPED; else printf UNKNOWN; fi; '
        f'printf "\\n"; ' + (f'if [ -f {directory}/output.log ]; then tail -c 60000 {directory}/output.log; fi' if output else '')
    )


class NodeJobs:
    def __init__(self, nodes: Nodes):
        self.nodes = nodes

    async def start_job(self, node_id: str, command: str) -> dict:
        node = await asyncio.to_thread(self.nodes.node, node_id)
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
            f'printf "%s" "$$" >{directory}/pid.tmp && mv {directory}/pid.tmp {directory}/pid || exit $?; '
            + remote_shell(node, command)
            + f'; result=$?; printf "%s" "$result" >{directory}/exit.tmp && mv {directory}/exit.tmp {directory}/exit'
        )
        script = (
            f'command -v setsid >/dev/null || exit 69; mkdir -p "$HOME/.cirno/jobs"; '
            f"mkdir {directory} || exit 70; "
            f"nohup setsid sh -c {shlex.quote(wrapper)}"
            f" >{directory}/output.log 2>&1 </dev/null & pid=$!; "
            'printf "%s" "$pid"'
        )

        try:
            await self._save_job(job)
        except asyncio.CancelledError as exc:
            await self._save_job({**job, "state": "submission_unknown", "error": str(exc) or type(exc).__name__})
            raise

        try:
            pid = int((await self.nodes.execute(node_id, script, include_stderr=False, initialize=False)).strip())
            if pid <= 0:
                raise ValueError("SSH returned an invalid job PID")
        except (Exception, asyncio.CancelledError) as exc:
            job = await self._save_job({
                **job, "state": "submission_unknown", "submission_error": str(exc) or type(exc).__name__,
                "resubmit_safe": False, "next_action": {"tool": "nodes.status", "job_id": job_id},
            })
            if isinstance(exc, asyncio.CancelledError):
                raise
            # Only inspect the already-admitted ID. Replaying the launch command
            # would create another job while the original might still be running.
            try:
                return await self.inspect_job(job_id)
            except (RuntimeError, OSError, TimeoutError) as verification_error:
                return await self._save_job({**job, "verification_error": str(verification_error)})
        return await self._save_job({**job, "pid": pid, "state": "running"})

    async def _save_job(self, job: dict) -> dict:
        if job["state"] == "submitting":
            return await shield_and_drain(asyncio.to_thread(self.nodes.data.save, "node_jobs", job))

        def update(current):
            # Submission acknowledgements own launch metadata, not a status
            # snapshot that may already have been superseded by a monitor read.
            observations = {"check_error", "check_started_at", "checked_at", "output", "exit_code", "finished_at"}
            merged = {**current, **{key: value for key, value in job.items() if key not in observations}}
            if current["state"] in TERMINAL_JOB_STATES and job["state"] not in TERMINAL_JOB_STATES:
                merged["state"] = current["state"]
                merged.pop("next_action", None)
            return merged
        return await shield_and_drain(asyncio.to_thread(self.nodes.data.update, "node_jobs", job["id"], update))

    async def inspect_job(self, job_id: str, *, stop=False) -> dict:
        job = await asyncio.to_thread(self.nodes.data.get, "node_jobs", job_id)
        started = datetime.now(timezone.utc)
        result = (
            await self.nodes.execute(job["node_id"], status_command(job_id, stop=True), initialize=False)
            if stop else await self.nodes.read_status(job["node_id"], status_command(job_id))
        )
        status, _, output = result.partition("\n")
        return await self._observe(job, status, started, output=output, stop=stop)

    async def inspect_jobs(self, jobs: list[dict], started: datetime) -> list[dict]:
        """Read a bounded group on one Node through one SSH connection."""
        if not jobs:
            return []
        script = "\n".join(f"printf '%s ' {shlex.quote(job['id'])}; " + status_command(job["id"], output=False) for job in jobs)
        result = await self.nodes.read_status(jobs[0]["node_id"], script)
        rows = {}
        for line in result.splitlines():
            identifier, separator, status = line.partition(" ")
            if not separator or identifier in rows:
                raise RuntimeError("Invalid remote job status response")
            rows[identifier] = status
        if set(rows) != {job["id"] for job in jobs}:
            raise RuntimeError("Incomplete remote job status response")
        return [await self._observe(job, rows[job["id"]], started) for job in jobs]

    async def record_check_error(self, jobs: list[dict], started: datetime, error: Exception) -> None:
        for job in jobs:
            def update(current):
                if current["state"] in TERMINAL_JOB_STATES or current.get("check_started_at", "") > started.isoformat():
                    return current
                return {**current, "check_started_at": started.isoformat(), "check_error": str(error) or type(error).__name__}
            await asyncio.to_thread(self.nodes.data.update, "node_jobs", job["id"], update)

    async def _observe(self, job: dict, status: str, started: datetime, *, output: str | None = None, stop=False) -> dict:
        unknown = "submission_unknown" if job["state"] in {"submitting", "submission_unknown"} else "unknown"
        state = {"RUNNING": "running", "STOPPED": "stopped"}.get(status, unknown)
        exit_code = int(status[5:]) if status.startswith("EXIT:") and status[5:].isdigit() else None
        if exit_code is not None:
            state = "completed" if exit_code == 0 else "failed"
        observed = datetime.now(timezone.utc).isoformat()

        def update(current):
            if current.get("check_started_at", "") > started.isoformat():
                return current
            if current["state"] in TERMINAL_JOB_STATES and state not in TERMINAL_JOB_STATES:
                return current
            current = {key: value for key, value in current.items() if key != "check_error"}
            if state not in {"unknown", "submission_unknown"}:
                current = {key: value for key, value in current.items() if key not in {"error", "verification_error", "next_action"}}
            elif current.get("submission_error"):
                current["next_action"] = {"tool": "nodes.status", "job_id": job["id"]}
                current["resubmit_safe"] = False
            return {
                **current, "state": state, "check_started_at": started.isoformat(), "checked_at": observed,
                **({"finished_at": current.get("finished_at") or observed} if state in TERMINAL_JOB_STATES else {}),
                **({"output": output} if output is not None else {}),
                **({"exit_code": exit_code} if exit_code is not None else {}),
                "stop_requested": stop or current.get("stop_requested", False),
            }
        return await shield_and_drain(asyncio.to_thread(self.nodes.data.update, "node_jobs", job["id"], update))
