"""Queue a named local trigger from another process using its generated command."""

import argparse
import sys
from pathlib import Path

from cirno_core.storage.records import RecordStoreError
from cirno_core.triggers.local_store import LocalTriggerStore, TriggerStoreError


def main() -> int:
    parser = argparse.ArgumentParser(description="Queue a Cirno local trigger delivery.")
    parser.add_argument("--store", type=Path, required=True, help="Instance trigger directory, supplied by Cirno")
    parser.add_argument("trigger_id")
    parser.add_argument("message")
    arguments = parser.parse_args()
    try:
        delivery = LocalTriggerStore(arguments.store).enqueue(arguments.trigger_id, arguments.message)
    except (TriggerStoreError, RecordStoreError, ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")
    print(f"Queued delivery {delivery.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
