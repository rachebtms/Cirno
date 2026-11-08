"""The released empty initial cursor is normalized only by offline migration."""

import json
from pathlib import Path

from cirno_core.memory.journal import MemoryJournal
from cirno_server.maintenance.migrations.registry import migrate_instance


def test_released_empty_dream_cursor_is_staged_and_original_retained(released):
    instance, _, config = released
    cursor = instance / "home/memory/.dream_cursor"
    cursor.parent.mkdir(parents=True, exist_ok=True)
    cursor.write_bytes(b"")

    assert migrate_instance(config)

    assert cursor.read_bytes() == b"0"
    migration = instance / "state/migrations/0.1.6-to-0.2.0"
    plan = json.loads((migration / "plan.json").read_text())
    replacement = next(item for item in plan["installs"] if item["target"] == str(cursor))
    assert Path(replacement["original"]).read_bytes() == b""
    assert MemoryJournal(instance / "home").get_last_dream_cursor() == 0
    assert not migrate_instance(config)
