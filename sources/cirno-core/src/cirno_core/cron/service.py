"""Cron service for scheduling agent tasks."""

import asyncio
import json
import time
import uuid
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Callable, Coroutine, Literal

from cirno_core.cron.binding import CronBinding, CronBindingError, binding_revision
from cirno_core.cron.repository import encode_store, load_jobs
from cirno_core.cron.scheduling import next_run, resume_next_run, validate_schedule
from cirno_core.cron.session_turns import is_bound_cron_job
from cirno_core.cron.types import (
    CronJob,
    CronJobState,
    CronPayload,
    CronRunRecord,
    CronRunResult,
    CronSchedule,
    CronStore,
)
from cirno_core.runtime.admission import RuntimeAdmission
from cirno_core.runtime.context import RUNTIME_CONTEXT_INPUT_META
from cirno_core.storage.records import RecordStoreError
from cirno_core.utils.atomic_file import atomic_write_text
from cirno_core.utils.run_records import (
    write_run_record as write_automation_run_record,
)
from filelock import FileLock
from loguru import logger


class CronJobSkippedError(Exception):
    """Raised by cron callbacks when a job was intentionally skipped."""


def _now_ms() -> int:
    return int(time.time() * 1000)



def _persistable_origin_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return a detached JSON-safe routing snapshot for a cron payload."""
    return json.loads(json.dumps(
        {key: value for key, value in metadata.items() if key != RUNTIME_CONTEXT_INPUT_META},
        ensure_ascii=False, allow_nan=False,
    ))


def _normalize_agent_turn_job(job: CronJob) -> bool:
    """Snapshot current routing metadata for persistence."""
    metadata = _persistable_origin_metadata(job.payload.origin_metadata)
    changed = metadata != job.payload.origin_metadata
    job.payload.origin_metadata = metadata
    return changed


class CronService:
    """Service for managing and executing scheduled jobs."""

    _MAX_RUN_HISTORY = 20
    _UNBOUND_AGENT_JOB_REASON = (
        "agent cron payload is missing bound session delivery context; "
        "recreate it from a chat session"
    )

    def __init__(
        self,
        store_path: Path,
        on_job: Callable[[CronJob], Coroutine[Any, Any, str | CronRunResult | None]] | None = None,
        max_sleep_ms: int = 300_000,  # 5 minutes
        *,
        admission: RuntimeAdmission | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ):
        self.admission = admission if admission is not None else RuntimeAdmission()
        self.store_path = store_path
        self._action_path = store_path.parent / "action.jsonl"
        self._run_records_dir = store_path.parent / "runs"
        self._lock = FileLock(str(self._action_path.parent) + ".lock")
        self.on_job = on_job
        self.on_error = on_error
        self._store: CronStore | None = None
        self._timer_task: asyncio.Task[None] | None = None
        self._running = False
        self._active_executions = 0
        self._store_dirty = False
        self.max_sleep_ms = max_sleep_ms

    def _should_persist_store(self) -> bool:
        """Return whether this instance currently owns the live store."""
        return self._running or self._active_executions > 0

    def _is_unbound_agent_job(self, job: CronJob) -> bool:
        return job.payload.kind == "agent_turn" and not is_bound_cron_job(job)

    def _enforce_agent_binding(self, job: CronJob) -> bool:
        """Disable user cron jobs that cannot be routed to a concrete session."""
        if not self._is_unbound_agent_job(job):
            return False
        if (
            not job.enabled
            and job.state.next_run_at_ms is None
            and job.state.last_status == "error"
            and job.state.last_error
        ):
            return False

        job.enabled = False
        job.state.next_run_at_ms = None
        job.state.last_status = "error"
        job.state.last_error = self._UNBOUND_AGENT_JOB_REASON
        job.updated_at_ms = max(job.updated_at_ms, _now_ms())
        logger.warning(
            "Cron: disabled unbound agent job '{}' ({}): {}",
            job.name,
            job.id,
            self._UNBOUND_AGENT_JOB_REASON,
        )
        return True

    def _enforce_store_agent_bindings(self) -> bool:
        if not self._store:
            return False
        changed = False
        for job in self._store.jobs:
            changed = self._enforce_agent_binding(job) or changed
        return changed


    def _merge_action(self) -> None:
        if not self._action_path.exists():
            return

        jobs_map = {job.id: job for job in self._store.jobs}  # pyright: ignore[reportOptionalMemberAccess]

        def _update(params: dict[str, Any]) -> None:
            j = CronJob.from_dict(params)
            _normalize_agent_turn_job(j)
            current = jobs_map.get(j.id)
            if current and j.payload.binding_version < current.payload.binding_version:
                logger.warning("Cron: ignored stale update for moved job {}", j.id)
                return
            jobs_map[j.id] = j

        def _del(params: dict[str, Any]) -> None:
            job_id = params.get("job_id")
            if isinstance(job_id, str) and job_id:
                jobs_map.pop(job_id, None)

        with self._lock:
            with open(self._action_path, "r", encoding="utf-8") as f:
                changed = False
                for number, line in enumerate(f, 1):
                    try:
                        action = json.loads(line)
                        operation = action["action"]
                        params = action["params"]
                        if operation == "del":
                            if not isinstance(params.get("job_id"), str) or not params["job_id"]:
                                raise ValueError("delete action requires job_id")
                            _del(params)
                        elif operation in {"add", "update"}:
                            _update(params)
                        else:
                            raise ValueError(f"unknown action {operation!r}")
                        changed = True
                    except (ValueError, KeyError, TypeError, AttributeError) as error:
                        raise RecordStoreError(f"Invalid automation action at {self._action_path}:{number}: {error}; action log is unchanged") from error
            self._store.jobs = list(jobs_map.values())  # pyright: ignore[reportOptionalMemberAccess]
            if self._should_persist_store() and changed:
                # Keep accepted actions recoverable until the merged snapshot is durable.
                self._save_store()
                self._action_path.write_text("", encoding="utf-8")
        return

    def _load_store(self, *, reload_during_execution: bool = False) -> CronStore:
        """Reload the shared catalog except while an execution or unsaved commit owns it."""
        if self._store is not None and (self._store_dirty or (self._active_executions > 0 and not reload_during_execution)):
            return self._store
        jobs, version = load_jobs(self.store_path)
        for job in jobs:
            _normalize_agent_turn_job(job)
        self._store = CronStore(version=version, jobs=jobs)
        self._merge_action()
        if self._enforce_store_agent_bindings() and self._should_persist_store():
            self._save_store()
        return self._store

    def _save_store(self) -> None:
        """Save jobs to disk."""
        if not self._store:
            return

        # Set this before serialization/write so every exceptional exit keeps
        # the in-memory snapshot authoritative until a later save succeeds.
        self._store_dirty = True
        self._write_store(self._store)
        self._store_dirty = False

    def _write_store(self, store: CronStore) -> None:
        """Persist a snapshot without publishing it as live state."""
        self._atomic_write(self.store_path, encode_store(store))

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        """Durably replace the job store without exposing a partial write."""
        atomic_write_text(path, content)

    def write_run_record(self, run_id: str, record: dict[str, Any]) -> None:
        """Write an internal audit record for one cron execution."""
        write_automation_run_record(self._run_records_dir, run_id, record)

    async def start(self) -> None:
        """Start the cron service."""
        self._running = True
        try:
            self._load_store()
            self._recompute_next_runs()
            self._save_store()
            self._arm_timer()
        except BaseException:
            self.stop()
            raise
        logger.info("Cron service started with {} jobs", len(self._store.jobs if self._store else []))

    def stop(self) -> None:
        """Stop the cron service."""
        self._running = False
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None

    def _recompute_next_runs(self) -> None:
        """Recompute next run times for all enabled jobs."""
        if not self._store:
            return
        now = _now_ms()
        for job in self._store.jobs:
            if self._enforce_agent_binding(job):
                continue
            if job.enabled:
                job.state.next_run_at_ms = resume_next_run(
                    job.schedule, job.state.next_run_at_ms, now
                )

    def _get_next_wake_ms(self) -> int | None:
        """Get the earliest next run time across all jobs."""
        if not self._store:
            return None
        times = [j.state.next_run_at_ms for j in self._store.jobs
                 if j.enabled and j.state.next_run_at_ms]
        return min(times) if times else None

    def _arm_timer(self, *, retry: bool = False) -> None:
        """Schedule the next timer tick."""
        # The timer task also owns the agent callback. Store edits during a
        # callback must not cancel it or start another tick for the same due
        # job. The final execution rearms after persisting its result.
        if self._active_executions:
            return
        if self._timer_task:
            self._timer_task.cancel()

        if not self._running:
            return

        next_wake = self._get_next_wake_ms()
        if retry or next_wake is None:
            delay_ms = self.max_sleep_ms
        else:
            delay_ms = min(self.max_sleep_ms, max(0, next_wake - _now_ms()))
        delay_s = delay_ms / 1000

        async def tick():
            await asyncio.sleep(delay_s)
            if self._running:
                await self._on_timer()

        self._timer_task = asyncio.create_task(tick())

    async def _on_timer(self) -> None:
        """Handle timer tick - run due jobs."""
        # Do not spin on an overdue timestamp or consume jobs while paused.
        # stop() cancels this waiter; an aborted maintenance wakes it normally.
        await self.admission.wait_until_open()
        with self.admission.activity():
            await self._run_timer()

    async def _run_timer(self) -> None:
        reload_store = self._active_executions == 0
        retry = False
        self._active_executions += 1
        try:
            # A prior tick may have completed external side effects but failed
            # to persist their advanced schedule.  Persist that exact snapshot
            # before reloading or executing anything else; otherwise the older
            # disk state can replay the same job.
            if self._store_dirty:
                self._save_store()
                return

            store = self._load_store(reload_during_execution=reload_store)
            now = _now_ms()
            due_jobs = [
                j for j in store.jobs
                if j.enabled and j.state.next_run_at_ms and now >= j.state.next_run_at_ms
            ]

            for candidate in due_jobs:
                # Earlier callbacks may delete, disable, or reschedule later jobs.
                job = self.get_job(candidate.id)
                if (
                    job is None
                    or not job.enabled
                    or not job.state.next_run_at_ms
                    or job.state.next_run_at_ms > _now_ms()
                ):
                    continue
                await self._execute_job(job)

            self._save_store()
        except Exception as error:
            retry = True
            logger.exception("Cron: tick failed ({}); retrying in {} ms", self.store_path, self.max_sleep_ms)
            if self.on_error is not None:
                await asyncio.to_thread(self.on_error, error)
        finally:
            self._active_executions -= 1
            if retry:
                self._arm_timer(retry=True)
            else:
                self._arm_timer()

    async def _execute_job(self, job: CronJob) -> None:
        """Execute a single job."""
        schedule = job.schedule
        start_ms = _now_ms()
        logger.info("Cron: executing job '{}' ({})", job.name, job.id)
        result: str | CronRunResult | None = None

        try:
            if self.on_job:
                result = await self.on_job(job)

            job.state.last_status = "ok"
            job.state.last_error = None
            logger.info("Cron: job '{}' completed", job.name)

        except CronJobSkippedError as e:
            job.state.last_status = "skipped"
            job.state.last_error = str(e) or None
            logger.warning("Cron: job '{}' skipped: {}", job.name, job.state.last_error or "")
        except asyncio.CancelledError as e:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            job.state.last_status = "error"
            job.state.last_error = str(e) or e.__class__.__name__
            logger.exception("Cron: job '{}' was cancelled", job.name)
        except Exception as e:
            job.state.last_status = "error"
            job.state.last_error = str(e)
            logger.exception("Cron: job '{}' failed", job.name)

        end_ms = _now_ms()
        job.state.last_run_at_ms = start_ms
        job.updated_at_ms = end_ms

        job.state.run_history.append(CronRunRecord(
            run_at_ms=start_ms,
            status=job.state.last_status,
            duration_ms=end_ms - start_ms,
            error=job.state.last_error,
            run_id=result.run_id if isinstance(result, CronRunResult) else None,
            session_key=job.payload.session_key,
        ))
        job.state.run_history = job.state.run_history[-self._MAX_RUN_HISTORY:]

        # Completion belongs to the schedule that started this run.
        if job.schedule is not schedule:
            return

        # Handle one-shot jobs
        if job.schedule.kind == "at":
            if job.delete_after_run:
                store = self._load_store()
                store.jobs = [item for item in store.jobs if item.id != job.id]
            else:
                job.enabled = False
                job.state.next_run_at_ms = None
        else:
            # Compute next run
            job.state.next_run_at_ms = next_run(job.schedule, _now_ms())

    def _append_action(
        self,
        action: Literal["add", "del", "update"],
        params: dict[str, Any],
    ) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with open(self._action_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"action": action, "params": params}, ensure_ascii=False) + "\n")


    # ========== Public API ==========

    def change_binding(
        self, job_id: str, *, revision: str, binding: CronBinding, message: str,
    ) -> CronJob:
        """Commit a reviewed move before it becomes visible to the scheduler.

        This is a live-owner operation. Reject while the scheduler owns any
        execution snapshot, including a turn waiting in a session inbox.
        No await separates validation, persistence, and publication.
        """
        if not self._running or self._active_executions or self._store_dirty:
            raise CronBindingError("busy", "automation scheduler is busy; try again when tasks finish")
        with self._lock:
            store = self._load_store()
            job = next((j for j in store.jobs if j.id == job_id), None)
            if job is None or not is_bound_cron_job(job):
                raise CronBindingError("unavailable", "automation has no movable chat")
            if binding_revision(job) != revision:
                raise CronBindingError("conflict", "automation changed; reopen it before changing the chat")
            if not message.strip():
                raise CronBindingError("empty", "automation message must not be empty")
            candidate = deepcopy(store)
            moved = next(j for j in candidate.jobs if j.id == job_id)
            for run in moved.state.run_history:
                if run.session_key is None:
                    run.session_key = job.payload.session_key
            moved.payload.session_key = binding.session_key
            moved.payload.origin_channel = binding.channel
            moved.payload.origin_chat_id = binding.chat_id
            moved.payload.origin_metadata = _persistable_origin_metadata(binding.metadata)
            moved.payload.binding_version += 1
            moved.payload.message = message
            moved.updated_at_ms = max(_now_ms(), job.updated_at_ms + 1)
            try:
                self._write_store(candidate)
            except OSError:
                # Directory fsync can fail after replace. Reconcile that exact
                # commit instead of claiming that the old binding survived.
                loaded = load_jobs(self.store_path)
                if loaded[0] != candidate.jobs:
                    raise
                logger.warning("Cron: binding saved, but directory sync failed for {}", job_id)
            self._store = candidate
            self._arm_timer()
            return moved

    def list_jobs(self, include_disabled: bool = False) -> list[CronJob]:
        """List all jobs."""
        store = self._load_store()
        jobs = store.jobs if include_disabled else [j for j in store.jobs if j.enabled]
        return sorted(jobs, key=lambda j: j.state.next_run_at_ms or float('inf'))

    def list_bound_cron_jobs_for_session(
        self,
        session_key: str,
        *,
        include_disabled: bool = True,
    ) -> list[CronJob]:
        """Return user-created bound cron jobs owned by *session_key*."""
        return [
            job
            for job in self.list_jobs(include_disabled=include_disabled)
            if is_bound_cron_job(job)
            and job.payload.session_key == session_key
        ]

    def add_job(
        self,
        name: str,
        schedule: CronSchedule,
        message: str,
        delete_after_run: bool = False,
        session_key: str | None = None,
        origin_channel: str | None = None,
        origin_chat_id: str | None = None,
        origin_metadata: dict[str, Any] | None = None,
    ) -> CronJob:
        """Add a new job."""
        validate_schedule(schedule)
        now = _now_ms()

        job = CronJob(
            id=str(uuid.uuid4())[:8],
            name=name,
            enabled=True,
            schedule=schedule,
            payload=CronPayload(
                kind="agent_turn",
                message=message,
                session_key=session_key,
                origin_channel=origin_channel,
                origin_chat_id=origin_chat_id,
                origin_metadata=origin_metadata or {},
            ),
            state=CronJobState(next_run_at_ms=next_run(schedule, now)),
            created_at_ms=now,
            updated_at_ms=now,
            delete_after_run=delete_after_run,
        )
        _normalize_agent_turn_job(job)
        self._enforce_agent_binding(job)
        if self._should_persist_store():
            store = self._load_store()
            store.jobs.append(job)
            self._save_store()
            self._arm_timer()
        else:
            self._append_action("add", asdict(job))

        logger.info("Cron: added job '{}' ({})", name, job.id)
        return job

    def register_system_job(self, job: CronJob) -> CronJob:
        """Register an internal system job (idempotent on restart)."""
        store = self._load_store()
        now = _now_ms()
        existing = next((j for j in store.jobs if j.id == job.id), None)
        persisted_ms = (
            existing.state.next_run_at_ms
            if existing is not None and existing.enabled and existing.schedule == job.schedule
            else None
        )
        job.state = CronJobState(next_run_at_ms=resume_next_run(job.schedule, persisted_ms, now))
        job.created_at_ms = now
        job.updated_at_ms = now
        store.jobs = [j for j in store.jobs if j.id != job.id]
        store.jobs.append(job)
        self._save_store()
        self._arm_timer()
        logger.info("Cron: registered system job '{}' ({})", job.name, job.id)
        return job

    def remove_system_job(self, job_id: str) -> bool:
        """Remove a protected system job during startup reconciliation."""
        store = self._load_store()
        before = len(store.jobs)
        store.jobs = [j for j in store.jobs if j.id != job_id]
        removed = len(store.jobs) < before
        if removed:
            self._save_store()
            self._arm_timer()
            logger.info("Cron: removed system job {}", job_id)
        return removed

    def remove_job(self, job_id: str) -> Literal["removed", "protected", "not_found"]:
        """Remove a job by ID, unless it is a protected system job."""
        store = self._load_store()
        job = next((j for j in store.jobs if j.id == job_id), None)
        if job is None:
            return "not_found"
        if job.payload.kind == "system_event":
            logger.info("Cron: refused to remove protected system job {}", job_id)
            return "protected"

        before = len(store.jobs)
        store.jobs = [j for j in store.jobs if j.id != job_id]
        removed = len(store.jobs) < before

        if removed:
            if self._should_persist_store():
                self._save_store()
                self._arm_timer()
            else:
                self._append_action("del", {"job_id": job_id})
            logger.info("Cron: removed job {}", job_id)
            return "removed"

        return "not_found"

    def enable_job(self, job_id: str, enabled: bool = True) -> CronJob | None:
        """Enable or disable a job."""
        store = self._load_store()
        for job in store.jobs:
            if job.id == job_id:
                job.enabled = enabled
                job.updated_at_ms = _now_ms()
                self._enforce_agent_binding(job)
                if job.enabled:
                    job.state.next_run_at_ms = next_run(job.schedule, _now_ms())
                else:
                    job.state.next_run_at_ms = None
                if self._should_persist_store():
                    self._save_store()
                    self._arm_timer()
                else:
                    self._append_action("update", asdict(job))
                return job
        return None

    def update_job(
        self,
        job_id: str,
        *,
        name: str | None = None,
        schedule: CronSchedule | None = None,
        message: str | None = None,
        delete_after_run: bool | None = None,
    ) -> CronJob | Literal["not_found", "protected"]:
        """Update mutable fields of an existing job. System jobs cannot be updated.

        For ``channel`` and ``to``, pass an explicit value (including ``None``)
        to update; omit (sentinel ``...``) to leave unchanged.
        Preserve the next occurrence unless the schedule actually changes.
        """
        store = self._load_store()
        job = next((j for j in store.jobs if j.id == job_id), None)
        if job is None:
            return "not_found"
        if job.payload.kind == "system_event":
            return "protected"

        schedule_changed = schedule is not None and schedule != job.schedule
        if schedule is not None:
            validate_schedule(schedule)
            if schedule_changed:
                job.schedule = replace(schedule)
        if name is not None:
            job.name = name
        if message is not None:
            job.payload.message = message
        if delete_after_run is not None:
            job.delete_after_run = delete_after_run
        _normalize_agent_turn_job(job)
        self._enforce_agent_binding(job)

        job.updated_at_ms = _now_ms()
        if not job.enabled:
            job.state.next_run_at_ms = None
        elif schedule_changed:
            job.state.next_run_at_ms = next_run(job.schedule, _now_ms())

        if self._should_persist_store():
            self._save_store()
            self._arm_timer()
        else:
            self._append_action("update", asdict(job))

        logger.info("Cron: updated job '{}' ({})", job.name, job.id)
        return job

    async def run_job(self, job_id: str, force: bool = False) -> bool:
        """Manually run a job without disturbing the service's running state."""
        with self.admission.activity():
            return await self._run_job(job_id, force)

    async def _run_job(self, job_id: str, force: bool) -> bool:
        reload_store = self._active_executions == 0
        self._active_executions += 1
        try:
            # A manual run is another side-effecting entrypoint.  Do not start
            # it while the result of a previous timer execution is still only
            # in memory.
            if self._store_dirty:
                self._save_store()
            store = self._load_store(reload_during_execution=reload_store)
            for job in store.jobs:
                if job.id == job_id:
                    if self._is_unbound_agent_job(job):
                        self._enforce_agent_binding(job)
                        self._save_store()
                        return False
                    if not force and not job.enabled:
                        return False
                    await self._execute_job(job)
                    self._save_store()
                    return True
            return False
        finally:
            self._active_executions -= 1
            if self._running and self._active_executions == 0:
                self._arm_timer()

    def get_job(self, job_id: str) -> CronJob | None:
        """Get a job by ID."""
        store = self._load_store()
        return next((j for j in store.jobs if j.id == job_id), None)

    def status(self) -> dict[str, object]:
        """Get service status."""
        store = self._load_store()
        return {
            "enabled": self._running,
            "jobs": len(store.jobs),
            "next_wake_at_ms": self._get_next_wake_ms(),
        }
