"""Process-local recording ownership shared by the runtime and authenticated workbench."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from cirno_core.config.paths import get_data_dir
from cirno_core.observability.recording import Recording
from cirno_core.session.display_history import HistoryFact
from loguru import logger


class TraceRecordings:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._recordings: dict[str, Recording] = {}
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def _refresh_active(self) -> None:
        self._active = any(record.running for record in self._recordings.values())

    @staticmethod
    def _failed(recording: Recording, error: OSError | sqlite3.Error | UnicodeError) -> None:
        recording.running, recording.reason = False, "storage_error"
        logger.error("Trace recording {} stopped: {}", recording.id, error)

    def create(self, identifier: str) -> dict[str, Any]:
        UUID(identifier)
        with self._lock:
            if identifier not in self._recordings:
                if len(self._recordings) >= 8:
                    raise ValueError(
                        "Close a trace tab before opening another recording (limit: 8)"
                    )
                self._recordings[identifier] = Recording(identifier)
            self._refresh_active()
            return self._recordings[identifier].info()

    def operation(self, identifier: str, operation: str, values: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if operation == "close":
                recording = self._recordings.pop(identifier, None)
                if recording:
                    recording.close()
                self._refresh_active()
                return {"ok": True}
            recording = self._recordings[identifier]
            if operation == "clear":
                replacement = Recording(identifier)
                replacement.running = recording.running
                recording.close()
                recording = self._recordings[identifier] = replacement
            elif operation in {"start", "pause"}:
                if operation == "start" and recording.reason == "capacity":
                    raise ValueError("Recording is full; clear it before continuing")
                recording.running = operation == "start"
                if recording.running:
                    recording.reason = None
            elif operation == "events":
                return recording.page(
                    before=values.get("before"),
                    kind=values.get("kinds"),
                    session=values.get("session_key"),
                )
            elif operation == "detail":
                if values.get("epoch") != recording.epoch:
                    raise ValueError("Recording was cleared; select an event again")
                return recording.detail(int(values["event_id"]), int(values.get("offset", 0)))
            else:
                raise ValueError("Unknown trace operation")
            self._refresh_active()
            return recording.info()

    def facts(self, session: str, facts: Sequence[HistoryFact]) -> None:
        with self._lock:
            for recording in self._recordings.values():
                try:
                    for fact in facts:
                        if recording.running:
                            recording.fact(session, fact)
                except (OSError, sqlite3.Error, UnicodeError) as error:
                    self._failed(recording, error)
            self._refresh_active()

    def begin(
        self, session: str, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> list[tuple[str, str, str, int]]:
        handles = []
        with self._lock:
            for recording in self._recordings.values():
                if recording.running:
                    try:
                        request_id = recording.requests.start(recording.id, messages, tools)
                        event_id = recording.append(
                            session, "request", model, "running", {"request_id": request_id}
                        )
                        handles.append((recording.id, recording.epoch, request_id, event_id))
                    except (OSError, sqlite3.Error, UnicodeError) as error:
                        self._failed(recording, error)
            self._refresh_active()
        return handles

    def finish(
        self, handles: list[tuple[str, str, str, int]], response: dict[str, Any], status: str
    ) -> None:
        with self._lock:
            for identifier, epoch, request_id, event_id in handles:
                recording = self._recordings.get(identifier)
                if recording is not None and recording.epoch == epoch:
                    try:
                        recording.requests.finish(request_id, response, status)
                        with recording.open() as db:
                            db.execute("UPDATE events SET status=? WHERE id=?", (status, event_id))
                        recording.check_capacity()
                    except (OSError, sqlite3.Error, UnicodeError) as error:
                        self._failed(recording, error)
            self._refresh_active()

    def export(self, identifier: str, epoch: str, destination) -> None:
        import tempfile
        from pathlib import Path
        from cirno_core.observability.recording_export import snapshot_recording, write_recording_zip

        with tempfile.TemporaryDirectory(prefix="cirno-trace-export-") as folder:
            snapshot = Path(folder) / "snapshot.sqlite3"
            with self._lock:
                recording = self._recordings[identifier]
                if epoch != recording.epoch:
                    raise ValueError("Recording was cleared; export the current recording again")
                info = snapshot_recording(recording, snapshot)
            # Compression does not block live capture, pause, clear or tab closure.
            write_recording_zip(snapshot, info, destination)

    def close_all(self) -> None:
        with self._lock:
            for recording in self._recordings.values():
                recording.close()
            self._recordings.clear()
            self._refresh_active()


_instances: dict[str, TraceRecordings] = {}
_instances_lock = threading.Lock()


def current_recordings() -> TraceRecordings:
    key = str(get_data_dir().resolve())
    with _instances_lock:
        if key not in _instances:
            _instances[key] = TraceRecordings()
        return _instances[key]
