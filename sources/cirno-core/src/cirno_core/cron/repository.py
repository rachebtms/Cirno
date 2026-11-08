"""The scheduler's persisted catalog format; writes are owned by CronService."""

import json
from pathlib import Path

from cirno_core.cron.types import CronJob, CronStore
from cirno_core.storage.records import read_records


def load_jobs(path: Path) -> tuple[list[CronJob], int]:
    return read_records(path, "jobs", CronJob.from_store_dict), 1


def encode_store(store: CronStore) -> str:
    data = {
        "version": store.version,
        "jobs": [
            {
                "id": j.id,
                "name": j.name,
                "enabled": j.enabled,
                "schedule": {
                    "kind": j.schedule.kind,
                    "atMs": j.schedule.at_ms,
                    "everyMs": j.schedule.every_ms,
                    "expr": j.schedule.expr,
                    "tz": j.schedule.tz,
                },
                "payload": {
                    "kind": j.payload.kind,
                    "message": j.payload.message,
                    "sessionKey": j.payload.session_key,
                    "originChannel": j.payload.origin_channel,
                    "originChatId": j.payload.origin_chat_id,
                    "originMetadata": j.payload.origin_metadata,
                    "bindingVersion": j.payload.binding_version,
                },
                "state": {
                    "nextRunAtMs": j.state.next_run_at_ms,
                    "lastRunAtMs": j.state.last_run_at_ms,
                    "lastStatus": j.state.last_status,
                    "lastError": j.state.last_error,
                    "runHistory": [
                        {
                            "runAtMs": r.run_at_ms,
                            "status": r.status,
                            "durationMs": r.duration_ms,
                            "error": r.error,
                            "runId": r.run_id,
                            "sessionKey": r.session_key,
                        }
                        for r in j.state.run_history
                    ],
                },
                "createdAtMs": j.created_at_ms,
                "updatedAtMs": j.updated_at_ms,
                "deleteAfterRun": j.delete_after_run,
            }
            for j in store.jobs
        ]
    }
    return json.dumps(data, indent=2, ensure_ascii=False)
