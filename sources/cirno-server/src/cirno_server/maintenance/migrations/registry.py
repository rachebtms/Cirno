"""Run registered offline migrations once and resume interrupted replacements."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from cirno_core import __version__
from cirno_core.config.loader import load_config
from cirno_server.maintenance.migrations.notices import publish_completed
from cirno_server.maintenance.migrations.plan import MigrationPlan
from cirno_server.maintenance.migrations.patch import ConfigVersionUpgrade
from cirno_server.maintenance.migrations.v016 import Import016
from filelock import FileLock
from loguru import logger


class Migration(Protocol):
    source_version: str
    target_version: str

    def prepare(self, config_path: Path, data: dict, root: Path) -> MigrationPlan: ...


MIGRATIONS: dict[str, Migration] = {
    step.source_version: step
    for step in (Import016(), ConfigVersionUpgrade("0.2.0", "0.2.1"), ConfigVersionUpgrade("0.2.1", "0.2.2"),
                 ConfigVersionUpgrade("0.2.2", "0.2.3"), ConfigVersionUpgrade("0.2.3", "0.2.4"), ConfigVersionUpgrade("0.2.4", "0.2.5"),
                 ConfigVersionUpgrade("0.2.5", "0.2.6"), ConfigVersionUpgrade("0.2.6", "0.2.7"), ConfigVersionUpgrade("0.2.7", "0.2.8"), ConfigVersionUpgrade("0.2.8", "0.2.9"), ConfigVersionUpgrade("0.2.9", "0.2.10"), ConfigVersionUpgrade("0.2.10", "0.2.11"), ConfigVersionUpgrade("0.2.11", "0.2.12"), ConfigVersionUpgrade("0.2.12", "0.2.13"), ConfigVersionUpgrade("0.2.13", "0.2.14"), ConfigVersionUpgrade("0.2.14", "0.2.15"), ConfigVersionUpgrade("0.2.15", "0.2.16"))
}


def resume_migrations(config_path: Path) -> bool:
    directory = config_path.parent / "state" / "migrations"
    if not directory.exists():
        return False
    changed = False
    with FileLock(str(directory / ".lock"), timeout=30):
        for pending in sorted(directory.glob("*/plan.json")):
            if not (pending.parent / "completed").exists():
                from cirno_server.maintenance.startup import require_stopped_instance
                require_stopped_instance(config_path)
                logger.info("Resuming Cirno migration: {}", pending.parent)
                MigrationPlan.load(pending.parent).apply()
                changed = True
            publish_completed(pending.parent, config_path.parent / "state")
    return changed


def migrate_instance(config_path: Path) -> bool:
    """Run under the migration lease, before configuration consumers or runtime writers."""
    config_path = config_path.resolve()
    changed = resume_migrations(config_path)
    if not config_path.exists():
        return changed
    load_config(config_path)
    data = json.loads(config_path.read_text())
    current = data.get("lastRunVersion") or data.get("last_run_version")
    if current == __version__:
        return migrate_current_layout(config_path.parent) or changed
    from cirno_server.maintenance.startup import require_stopped_instance
    require_stopped_instance(config_path)
    directory = config_path.parent / "state" / "migrations"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with FileLock(str(directory / ".lock"), timeout=30):
        # Another launcher may have completed migration while this one waited.
        data = json.loads(config_path.read_text())
        current = data.get("lastRunVersion") or data.get("last_run_version") or "0.1.6"
        while current != __version__:
            step = MIGRATIONS.get(current)
            if step is None:
                raise ValueError(f"No Cirno migration from {current} to {__version__}; instance was not started")
            root = directory / f"{step.source_version}-to-{step.target_version}"
            if (root / "completed").exists():
                root = root.with_name(root.name + "-" + uuid4().hex[:8])
            logger.info("Migrating Cirno {} to {}; originals: {}", current, step.target_version, root / "originals")
            plan = step.prepare(config_path, data, root)
            plan.apply()
            publish_completed(root, config_path.parent / "state")
            current, changed = step.target_version, True
            data = json.loads(config_path.read_text())
    return migrate_current_layout(config_path.parent) or changed


def migrate_current_layout(instance: Path) -> bool:
    from cirno_server.maintenance.migrations.cirno_identity import migrate_cirno_identity
    from cirno_server.maintenance.migrations.ssh_credentials import migrate_ssh_credentials
    changed = False
    for migrate in (migrate_cirno_identity, migrate_ssh_credentials):
        changed = migrate(instance) or changed
    return changed
