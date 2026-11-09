"""Stream exact conversation evidence to immutable, content-addressed files."""

from __future__ import annotations

import hashlib
import json
from io import StringIO
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from cirno_memory.paging import source_page

if TYPE_CHECKING:
    from cirno_memory.repository import MemoryRepository


@dataclass(frozen=True)
class EvidenceFile:
    identity: str
    path: Path
    message_count: int
    preview: str


def write_evidence(
    directory: Path,
    session_key: str,
    messages: Iterable[Mapping[str, Any]],
    *,
    preserve_system: bool,
) -> EvidenceFile:
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / (uuid4().hex + ".tmp")
    digest = hashlib.sha256(session_key.encode())
    recent: deque[str] = deque(maxlen=8)
    count = 0
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            for message in messages:
                if not preserve_system and message.get("role") in {"system", "developer"}:
                    continue
                line = json.dumps(message, ensure_ascii=False, sort_keys=True, default=str) + "\n"
                stream.write(line)
                count += 1
                digest.update(line.encode())
                recent.append(str(message.get("content", ""))[:1200])
        identity = "source-" + digest.hexdigest()[:40]
        path = directory / f"{identity}.jsonl"
        temporary.replace(path)
        return EvidenceFile(identity, path, count, "\n".join(recent))
    finally:
        temporary.unlink(missing_ok=True)


def read_evidence(
    repo: MemoryRepository,
    identity: str,
    *,
    start_line: int = 1,
    limit: int = 20,
    char_offset: int = 0,
    revision: int | None = None,
    **access: Any,
) -> dict[str, Any]:
    """Resolve a pinned evidence record and stream a bounded source page."""
    record = repo.read(identity, revision=revision, **access)
    metadata = {"memory_id": identity, "revision": record["revision"], "source": record["source"]}

    def text_page(content: str) -> dict[str, Any]:
        page = source_page(StringIO(content), start_line=start_line, limit=limit, char_offset=char_offset)
        return {**page, "content": "".join(row["text"] for row in page["lines"])}

    reference = str(record["source"]).split("#", 1)[0]
    if record["source"].startswith("memory:"):
        original = repo.read(record["source"][7:], revision=record.get("based_on_revision"), **access)
        return {**metadata, **text_page(original["content"]),
                "source_refs": [{"memory_id": original["id"], "revision": original["revision"],
                                 "source": original["source"]}, *original["source_refs"]]}
    evidence_ref = next((ref for ref in record.get("source_refs", []) if ref.get("memory_id")), None)
    if evidence_ref and evidence_ref["memory_id"] != identity and record["layer"] != "source":
        evidence = repo.read(evidence_ref["memory_id"], revision=evidence_ref.get("revision"), **access)
        if evidence["layer"] == "source":
            return read_evidence(repo, evidence["id"], revision=evidence["revision"],
                                 start_line=start_line, limit=limit, char_offset=char_offset, **access)
    if record["source"].startswith("memory/history.jsonl#cursor-"):
        return {**metadata, "source": record["path"], **text_page(record["content"]),
                "source_refs": record["source_refs"],
                "note": "This is a compacted event, not independent verification; follow original source references for exact claims."}
    if record["layer"] != "source":
        captures = repo.search(identity, layer="source", limit=3, **access)["memories"]
        return {**metadata,
                "source_refs": record["source_refs"] + [{"memory_id": row["id"], "revision": row["revision"],
                                                        "source": row["source"], "start_line": row.get("start_line", 1)} for row in captures],
                "note": "Captured conversation evidence can be read with memory.source using the returned memory IDs. External references require file/web/Node verification; a recorded claim is not external verification."}
    path = Path(reference)
    path = (path if path.is_absolute() else repo.home / path).resolve()
    if path.parent != repo.root / "sources" or path.stem != record["id"] or not path.is_file():
        return {**metadata, "source_refs": record["source_refs"],
                "note": "Use the file/web/Node tool to inspect this external source under its own access rules."}
    with path.open(encoding="utf-8") as stream:
        return {**metadata, **source_page(stream, start_line=start_line, limit=limit, char_offset=char_offset)}
