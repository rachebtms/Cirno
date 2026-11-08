"""Finish interrupted offline operations before configuration/runtime initialization."""

from __future__ import annotations

import os
from pathlib import Path

from cirno_server.lifecycle.runtime import ServerRuntime
from cirno_server.lifecycle.instance import ServerRuntimePaths


def require_stopped_instance(config_path: Path) -> None:
    root = config_path.parent / "state"
    for path in (root / "run").glob("gateway*.json"):
        runtime = ServerRuntime(paths=ServerRuntimePaths(
            run_dir=path.parent, logs_dir=root / "logs", state_path=path,
            log_path=root / "logs" / (path.stem + ".log"),
        ))
        status = runtime.status()
        if status.running and status.pid != os.getpid():
            raise ValueError(f"Stop Cirno process {status.pid} before migrating or restoring this instance")


def finish_pending_maintenance(config_path: Path) -> bool:
    from cirno_server.backup.archive import Backups
    from cirno_server.maintenance.migrations.registry import resume_migrations

    backups = Backups(config_path)
    pending = config_path.parent / "state" / "migrations"
    unfinished = any(not (path.parent / "completed").exists() for path in pending.glob("*/plan.json"))
    restore_pending = (backups.store / "restore-plan.json").exists()
    if not unfinished and not restore_pending:
        return False
    require_stopped_instance(config_path)
    resume_migrations(config_path)
    return backups.apply_pending()
