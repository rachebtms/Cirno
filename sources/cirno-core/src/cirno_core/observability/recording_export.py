"""Portable, deduplicated ZIP representation of a recording snapshot."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def snapshot_recording(recording, destination: Path) -> dict:
    with recording.open() as source, sqlite3.connect(destination) as target:
        source.backup(target)
    return {**recording.info(), "exported_ms": int(time.time() * 1000), "format_version": 1}


def write_recording_zip(snapshot: Path, info: dict, destination: Path) -> None:
    with sqlite3.connect(snapshot) as db, ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        db.row_factory = sqlite3.Row
        archive.writestr("manifest.json", json.dumps(info, ensure_ascii=False, indent=2))
        archive.writestr("README.txt", (
            "Cirno trace recording, format 1\n"
            "events.jsonl contains every captured event in recording order.\n"
            "requests.jsonl contains API requests: inputs is the ordered list of message blob hashes; "
            "tools and response are blob hashes (response may be null while running).\n"
            "blobs/<hash>.json contains each original JSON value once. Reuse these references "
            "to reconstruct requests without duplicating long conversation prefixes.\n"
            "The export is a snapshot; recording can continue after it is taken.\n"
        ))
        with archive.open("events.jsonl", "w") as output:
            for row in db.execute("SELECT * FROM events ORDER BY id"):
                event = dict(row)
                event["session_key"] = event.pop("session")
                event["body"] = json.loads(event["body"])
                output.write((json.dumps(event, ensure_ascii=False) + "\n").encode())
        # A recording without API requests need not have these tables yet.
        has_requests = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='requests'").fetchone()
        with archive.open("requests.jsonl", "w") as output:
            if has_requests:
                for row in db.execute("SELECT * FROM requests ORDER BY rowid"):
                    request = dict(row)
                    request["inputs"] = json.loads(request["inputs"])
                    output.write((json.dumps(request, ensure_ascii=False) + "\n").encode())
        if has_requests:
            for digest, body in db.execute("SELECT digest,body FROM blobs ORDER BY digest"):
                archive.writestr(f"blobs/{digest}.json", body)
