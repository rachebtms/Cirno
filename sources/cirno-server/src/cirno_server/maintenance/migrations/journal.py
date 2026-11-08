"""Normalize the released Git initializer's empty Dream cursor offline."""

from pathlib import Path

from cirno_core.utils.atomic_file import atomic_write_text
from cirno_server.maintenance.migrations.plan import MigrationPlan


def stage_initial_dream_cursor(instance: Path, plan: MigrationPlan) -> bool:
    cursor = instance / "home" / "memory" / ".dream_cursor"
    if not cursor.exists() or cursor.read_text(encoding="utf-8").strip():
        return False
    staged = plan.root / "staged" / "initial-dream-cursor"
    atomic_write_text(staged, "0")
    plan.install(staged, cursor)
    return True
