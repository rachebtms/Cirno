"""Disk-backed, source-grounded memory. SQLite owns metadata; FTS is rebuildable.

No model or in-memory document corpus is loaded on the default search path.
All instances use short transactions and a bounded SQLite page cache.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cirno_memory.paging import source_chunks
from cirno_memory.checkpoints import checkpoint_id
from cirno_memory.errors import MemoryRevisionConflict
from cirno_memory.scopes import scope_identity, visible, visibility_filter

LAYERS = {"event", "knowledge", "task", "source", "profile"}
KINDS = {"observation", "hypothesis", "fact", "lesson", "checkpoint", "source"}
RELATIONS = {"supports", "conflicts", "supersedes", "related", "derived_from"}
_ID = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")
_WORDS = re.compile(r"[\u3400-\u9fff]+|[^\W_]+", re.UNICODE)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def time_conditions(since=None, until=None, time_field="observed_at", time_zone="UTC"):
    if time_field not in {"observed_at", "created_at", "updated_at"}:
        raise ValueError("time_field must be observed_at, created_at or updated_at")
    column = "m.updated_at" if time_field == "updated_at" else f"json_extract(m.body,'$.{time_field}')"
    clauses, args = [], []
    try:
        zone = ZoneInfo(time_zone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Unknown time_zone") from exc
    for value, lower in ((since, True), (until, False)):
        if not value:
            continue
        bound = datetime.fromisoformat(value.replace("Z", "+00:00"))
        day_end = not lower and len(value) == 10
        if day_end:
            bound += timedelta(days=1)
        if bound.tzinfo is None:
            bound = bound.replace(tzinfo=zone)
        operator = ">=" if lower else "<" if day_end else "<="
        clauses.append(f"julianday({column}){operator}julianday(?)")
        args.append(bound.isoformat())
    return clauses, args


def search_tokens(text: str) -> str:
    """Same deterministic preprocessing for documents and queries, including CJK bigrams."""
    tokens = []
    for match in _WORDS.finditer(text.casefold()):
        word = match.group()
        if "\u3400" <= word[0] <= "\u9fff":
            tokens.extend(word)
            tokens.extend(word[i:i + 2] for i in range(len(word) - 1))
        else:
            tokens.append(word)
    return " ".join(tokens)


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temp.write_text(content, encoding="utf-8")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


class MemoryRepository:
    def __init__(self, home: Path):
        self.home = home.resolve()
        self.root = self.home / "memory"
        self.root.mkdir(parents=True, exist_ok=True)
        from cirno_memory import storage as memory_storage
        memory_storage.initialize(self.root)
        self.path = self.root / "catalog.sqlite3"

    def connect(self, *, vectors=False):
        from cirno_memory.storage import connect
        return connect(self.root, vectors=vectors)

    def _body_path(self, record: dict) -> Path:
        path = (self.home / record["path"]).resolve()
        if not path.is_relative_to(self.home):
            raise ValueError("Memory body is outside Home")
        return path

    visible = staticmethod(visible)

    def body_content(self, record: dict) -> str:
        content = self._body_path(record).read_text(encoding="utf-8")
        if _hash(content) != record["content_hash"]:
            raise ValueError(f"Memory {record['id']} revision {record['revision']} body differs from its saved hash")
        return content

    def read(self, memory_id: str, *, session_key=None, project_id=None, maintenance=False, revision=None) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT body FROM memories WHERE id=?", (memory_id,)).fetchone()
            if row is None:
                raise KeyError("Memory not found")
            record = json.loads(row[0])
            if not maintenance and not self.visible(record, session_key, project_id):
                raise PermissionError("Memory is outside the current user/project/conversation scope")
            if revision is not None:
                row = db.execute("SELECT body,path FROM revisions WHERE memory_id=? AND revision=?", (memory_id, revision)).fetchone()
                if row is None:
                    raise KeyError("Memory revision not found")
                record = {**json.loads(row[0]), "path": row[1]}
            record["content"] = self.body_content(record)
            record["links"] = [dict(r) for r in db.execute(
                "SELECT source,target,relation,evidence FROM links WHERE source=? OR target=? LIMIT 50", (memory_id, memory_id)
            )]
            # Never disclose another scope's identifiers through a cross-scope edge.
            if not maintenance:
                record["links"] = [link for link in record["links"] if all(
                    self._visible_id(db, identity, session_key, project_id) for identity in (link["source"], link["target"])
                )]
            return record

    def _visible_id(self, db, identity, session, project):
        row = db.execute("SELECT body FROM memories WHERE id=?", (identity,)).fetchone()
        return bool(row and self.visible(json.loads(row[0]), session, project))

    def save(self, content: str, *, source: str, session_key: str, project_id=None,
             scope="session", kind=None, layer=None, title="", tags=None,
             source_refs=None, memory_id=None, expected_revision=None, enqueue=True,
             status=None, observed_at=None, based_on=None, maintenance=False,
             turn_id=None, message_id=None, created_at=None, expected_parent_revision=None) -> dict:
        if not content.strip() or not source.strip():
            raise ValueError("content and source are required; do not invent evidence")
        if len(content) > 64_000 or len(source) > 4000:
            raise ValueError("Memory content exceeds 64000 characters or source exceeds 4000; split the record")
        if scope not in {"user", "project", "session"} or (layer is not None and layer not in LAYERS) or (kind is not None and kind not in KINDS):
            raise ValueError("Invalid scope, layer or kind")
        if scope == "project" and not project_id:
            raise ValueError("This conversation has no project")
        if status is not None and status not in {"active", "superseded", "archived"}:
            raise ValueError("Invalid memory status")
        if observed_at:
            datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        supplied_tags = tags
        tags = sorted(set(str(tag).strip().casefold() for tag in tags or [] if str(tag).strip()))
        if len(tags) > 20 or any(len(tag) > 80 for tag in tags):
            raise ValueError("Use at most 20 tags of at most 80 characters")
        memory_id = memory_id or uuid4().hex
        if not _ID.fullmatch(memory_id):
            raise ValueError("Invalid memory ID")
        if based_on == memory_id:
            raise ValueError("Create a separate knowledge record when deriving from this same memory")
        digest = _hash(content)
        access_session, access_project = session_key, project_id
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT body FROM memories WHERE id=?", (memory_id,)).fetchone()
            old = json.loads(existing[0]) if existing else None
            if old:
                if not maintenance and not self.visible(old, access_session, access_project):
                    raise PermissionError("Memory is outside the current scope")
                if expected_revision is None or expected_revision != old["revision"]:
                    raise MemoryRevisionConflict(
                        {
                            "id": old["id"], "revision": old["revision"],
                            "source": old["source"], "content": self.body_content(old),
                        },
                        expected_revision,
                    )
                scope, project_id, session_key = old["scope"], old.get("project_id"), old.get("session_key")
            status = status or (old or {}).get("status", "active")
            supplied_parent = based_on
            if based_on is None and old:
                based_on = old.get("based_on")
            parent_revision = (old or {}).get("based_on_revision")
            parent_observed_at = None
            layer = layer or (old or {}).get("layer", "event")
            kind = kind or (old or {}).get("kind", "observation")
            if old:
                tags = tags if supplied_tags is not None else old.get("tags", [])
                source_refs = source_refs if source_refs is not None else old.get("source_refs", [])
                title = title or old.get("title", "")
            if based_on:
                parent = db.execute("SELECT body FROM memories WHERE id=?", (based_on,)).fetchone()
                if not parent:
                    raise KeyError("Evidence memory not found")
                parent = json.loads(parent[0])
                if expected_parent_revision is not None and parent["revision"] != expected_parent_revision:
                    raise ValueError("Evidence changed; read its current revision before deriving knowledge")
                parent_observed_at = parent.get("observed_at")
                if not maintenance and not self.visible(parent, access_session, access_project):
                    raise PermissionError("Evidence is outside the current scope")
                if old and scope_identity(old) != scope_identity(parent):
                    raise ValueError("An update cannot change an existing memory's evidence scope; create a separate scoped record")
                if supplied_parent is not None or parent_revision is None:
                    parent_revision = parent["revision"]
                # Derived knowledge inherits visibility, never silently promotes a project fact to a user fact.
                scope, project_id = parent["scope"], parent.get("project_id")
                session_key = old.get("session_key") if old else parent.get("session_key")
            version = (old["revision"] if old else 0) + 1
            relative = f"memory/entries/{memory_id}.md"
            record = dict(id=memory_id, title=title.strip()[:160] or content.strip().splitlines()[0][:120],
                          source=source, scope=scope, kind=kind, layer=layer, status=status,
                          project_id=project_id, session_key=session_key, tags=tags,
                          source_refs=source_refs or [], based_on=based_on, based_on_revision=parent_revision,
                          created_at=old["created_at"] if old else (created_at or now()), updated_at=now(),
                          observed_at=observed_at or (old or {}).get("observed_at") or parent_observed_at,
                          revision=version, content_hash=digest, path=relative,
                          turn_id=turn_id, message_id=message_id)
            # Immutable revision is durable before the metadata transaction commits.
            revision_path = f"memory/revisions/{memory_id}/{version}.md"
            _atomic(self.home / revision_path, content)
            db.execute("INSERT INTO revisions VALUES(?,?,?,?)", (memory_id, version, json.dumps(record, ensure_ascii=False), revision_path))
            # The record points at the immutable version, so an interrupted mirror write cannot corrupt committed content.
            record["path"] = revision_path
            self._put_record(db, record, content)
            if enqueue and layer not in {"task", "source", "profile"}:
                db.execute("""INSERT INTO dream_queue(memory_id,revision,queued_at) VALUES(?,?,?)
                    ON CONFLICT(memory_id) DO UPDATE SET revision=excluded.revision,
                    queued_at=excluded.queued_at,error=NULL,retry_after=0,attempts=0""", (memory_id, version, time.time()))
            elif layer in {"task", "source", "profile"}:
                db.execute("DELETE FROM dream_queue WHERE memory_id=?", (memory_id,))
            else:
                # A non-enqueuing update must not leave an older queued revision
                # impossible to acknowledge. Preserve its lease for this run.
                db.execute("UPDATE dream_queue SET revision=?,error=NULL,retry_after=0,attempts=0 WHERE memory_id=?", (version, memory_id))
            if based_on:
                db.execute("INSERT OR IGNORE INTO links VALUES(?,?,?,?)", (memory_id, based_on, "derived_from", source))
            _atomic(self.home / relative, content)
        return record

    def _put_record(self, db, record, content):
        db.execute("""INSERT OR REPLACE INTO memories VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (
            record["id"], json.dumps(record, ensure_ascii=False), record["path"], record["scope"],
            record.get("project_id"), record.get("session_key"), record["layer"], record["status"],
            record["revision"], record["content_hash"], record["updated_at"],
        ))
        old_ids = [r[0] for r in db.execute("SELECT id FROM chunks WHERE memory_id=?", (record["id"],))]
        db.executemany("DELETE FROM memory_fts WHERE rowid=?", [(i,) for i in old_ids])
        db.execute("DELETE FROM chunks WHERE memory_id=?", (record["id"],))
        source_path = (self.home / str(record.get("source", ""))).resolve()
        if record["layer"] == "source" and source_path.parent == self.root / "sources" and source_path.stem == record["id"] and source_path.is_file():
            # Index every original byte, not only the short directory preview. Stream per line/chunk.
            with source_path.open(encoding="utf-8") as stream:
                for number, chunk in source_chunks(stream):
                    self._chunk(db, record, chunk, number, number)
            return
        lines = content.splitlines() or [content]
        # Line-aware bounded chunks; very long lines are split without losing source line numbers.
        batch, count, start = [], 0, 1
        for number, line in enumerate(lines, 1):
            for offset in range(0, max(1, len(line)), 1200):
                part = line[offset:offset + 1200]
                if count + len(part) > 1400 and batch:
                    self._chunk(db, record, "\n".join(batch), start, number)
                    batch, count, start = [], 0, number
                batch.append(part)
                count += len(part) + 1
        if batch:
            self._chunk(db, record, "\n".join(batch), start, len(lines))

    @staticmethod
    def _chunk(db, record, content, start, end):
        row = db.execute("INSERT INTO chunks(memory_id,start_line,end_line,text) VALUES(?,?,?,?)", (record["id"], start, end, content))
        db.execute("INSERT INTO memory_fts(rowid,title,tokens) VALUES(?,?,?)", (
            row.lastrowid, search_tokens(record["title"] + " " + " ".join(record["tags"])), search_tokens(content),
        ))

    def search(self, query="", *, session_key=None, project_id=None, maintenance=False,
               scope=None, layer=None, tags=None, include_history=False, limit=10, offset=0,
               since=None, until=None, time_field="observed_at", time_zone="UTC", purpose="all", expand_links=0) -> dict:
        limit = max(1, min(int(limit), 30))
        clauses, args = [], []
        if purpose not in {"knowledge", "evidence", "all"}:
            raise ValueError("purpose must be knowledge, evidence or all")
        if not layer or layer == "all":
            if purpose == "knowledge":
                clauses.append("m.layer IN ('knowledge','task','profile')")
            elif purpose == "evidence":
                clauses.append("m.layer IN ('source','event')")
        if not maintenance:
            visibility, access_args = visibility_filter(session_key, project_id)
            clauses.append(visibility)
            args.extend(access_args)
        for column, value in (("scope", scope), ("layer", layer)):
            if value and value != "all":
                clauses.append(f"m.{column}=?")
                args.append(value)
        if not include_history:
            clauses.append("m.status='active'")
        dates, date_args = time_conditions(since, until, time_field, time_zone)
        clauses.extend(dates)
        args.extend(date_args)
        for tag in tags or []:
            clauses.append("EXISTS(SELECT 1 FROM json_each(m.body,'$.tags') WHERE value=?)")
            args.append(str(tag).strip().casefold())
        condition = " AND ".join(clauses) or "1"
        with self.connect() as db:
            tokens = list(dict.fromkeys(search_tokens(query[:2000]).split()))[:80]
            if tokens:
                # User text is always quoted; MATCH syntax cannot alter the query.
                match = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
                # Rank chunks once, then paginate unique records, never arbitrary chunk offsets.
                rows = db.execute(f"""WITH ranked AS (
                    SELECT m.id,m.body,c.text,c.start_line,c.end_line,bm25(memory_fts,4.0,1.0) AS rank
                    FROM memory_fts JOIN chunks c ON c.id=memory_fts.rowid JOIN memories m ON m.id=c.memory_id
                    WHERE memory_fts MATCH ? AND {condition}
                ), best AS (
                    SELECT *,row_number() OVER(PARTITION BY id ORDER BY rank,start_line) AS position FROM ranked
                ) SELECT * FROM best WHERE position=1 ORDER BY (id=?) DESC,rank,id LIMIT ? OFFSET ?""",
                    [match, *args, query, limit + 1, max(0, int(offset))]).fetchall()
            else:
                rows = db.execute(f"SELECT m.body,'' AS text,0 AS start_line,0 AS end_line,0 AS rank FROM memories m WHERE {condition} ORDER BY m.updated_at DESC,m.id LIMIT ? OFFSET ?", [*args, limit + 1, max(0, int(offset))]).fetchall()
            results = []
            for row in rows:
                record = json.loads(row["body"])
                results.append({**record, "snippet": row["text"], "start_line": row["start_line"],
                                "end_line": row["end_line"], "score": -row["rank"]})
            if query and _ID.fullmatch(query) and not offset:
                exact = db.execute(f"SELECT m.body FROM memories m WHERE m.id=? AND {condition}", [query, *args]).fetchone()
                if exact and not any(r["id"] == query for r in results):
                    record = json.loads(exact[0])
                    selected = [{**record, "snippet": self.body_content(record)[:1400], "match": "id"}]
                    if expand_links:
                        self.expand_links(selected, limit=expand_links, session_key=session_key, project_id=project_id, maintenance=maintenance)
                    return {"memories": selected, "has_more": False, "next_offset": 1, "engine": "bm25", "time_zone": time_zone}
            selected = results[:limit]
            if expand_links:
                self.expand_links(selected, limit=expand_links, session_key=session_key, project_id=project_id, maintenance=maintenance)
            return {"memories": selected, "has_more": len(results) > limit,
                    "next_offset": max(0, int(offset)) + min(limit, len(results)), "engine": "bm25", "time_zone": time_zone}

    def expand_links(self, records, *, limit=3, session_key=None, project_id=None, maintenance=False):
        """One hop, at most ten neighbors across the entire result, scope checked."""
        remaining = max(0, min(int(limit), 10))
        seen = {record["id"] for record in records}
        with self.connect() as db:
            for record in records:
                record["neighbors"] = []
                for link in db.execute("SELECT * FROM links WHERE source=? OR target=? ORDER BY CASE relation WHEN 'supersedes' THEN 0 WHEN 'conflicts' THEN 1 ELSE 2 END LIMIT 50", (record["id"], record["id"])):
                    if not remaining:
                        break
                    identity = link["target"] if link["source"] == record["id"] else link["source"]
                    if identity in seen:
                        continue
                    row = db.execute("SELECT body FROM memories WHERE id=?", (identity,)).fetchone()
                    if not row:
                        continue
                    other = json.loads(row[0])
                    if not maintenance and not self.visible(other, session_key, project_id):
                        continue
                    seen.add(identity)
                    remaining -= 1
                    record["neighbors"].append({"id": identity, "title": other["title"], "status": other["status"],
                                                "revision": other["revision"], "relation": link["relation"],
                                                "source": link["source"], "target": link["target"], "evidence": link["evidence"][:300]})

    def list_tags(self, *, session_key=None, project_id=None, maintenance=False, prefix="", limit=30, offset=0):
        condition, args = "m.status='active'", []
        if not maintenance:
            visibility, args = visibility_filter(session_key, project_id)
            condition += " AND " + visibility
        with self.connect() as db:
            rows = db.execute(f"""SELECT tag.value AS name,count(DISTINCT m.id) AS count
                FROM memories m,json_each(m.body,'$.tags') tag WHERE {condition}
                AND substr(tag.value,1,length(?))=? GROUP BY tag.value ORDER BY count DESC,name LIMIT ? OFFSET ?""",
                [*args, prefix.casefold(), prefix.casefold(), min(max(int(limit), 1), 50) + 1, max(0, int(offset))]).fetchall()
        cap = min(max(int(limit), 1), 50)
        return {"tags": [dict(row) for row in rows[:cap]], "has_more": len(rows) > cap, "next_offset": max(0, int(offset)) + min(cap, len(rows))}

    def link(self, source_id, target_id, relation, evidence, *, session_key=None, project_id=None, maintenance=False, expected_target_revision=None):
        if relation not in RELATIONS or not str(evidence).strip() or source_id == target_id:
            raise ValueError("Use a supported relation, two different records and an evidence explanation")
        source = self.read(source_id, session_key=session_key, project_id=project_id, maintenance=maintenance)
        target = self.read(target_id, session_key=session_key, project_id=project_id, maintenance=maintenance)
        if expected_target_revision is not None and target["revision"] != expected_target_revision:
            raise ValueError("Linked evidence changed during consolidation")
        if scope_identity(source) != scope_identity(target):
            raise ValueError("Linked memories must have the same visibility scope")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for record in (source, target):
                current = db.execute("SELECT revision FROM memories WHERE id=?", (record["id"],)).fetchone()
                if current is None or current[0] != record["revision"]:
                    raise ValueError("Linked memory changed; read it before linking evidence")
            db.execute("INSERT OR REPLACE INTO links VALUES(?,?,?,?)", (source_id, target_id, relation, evidence))
            if relation == "supersedes":
                target.pop("content")
                target.pop("links")
                target["status"] = "superseded"
                changed = db.execute("UPDATE memories SET status='superseded',body=? WHERE id=? AND revision=?", (json.dumps(target, ensure_ascii=False), target_id, target["revision"])).rowcount
                if not changed:
                    raise ValueError("Target memory changed; read it before linking a correction")
        return {"source": source_id, "target": target_id, "relation": relation, "evidence": evidence}

    def history(self, identity, **access):
        self.read(identity, **access)
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT body FROM revisions WHERE memory_id=? ORDER BY revision DESC LIMIT 50", (identity,))]

    def checkpoint(self, session_key, content, source, *, project_id=None, expected_revision=None):
        identity = checkpoint_id(self, session_key, project_id)
        return self.save(content, source=source, session_key=session_key, project_id=project_id,
                         scope="project" if project_id else "session", kind="checkpoint", layer="task",
                         title="Task checkpoint", memory_id=identity, expected_revision=expected_revision, enqueue=False)

    def task_context(self, session_key, project_id=None, max_chars=6000, *, include_automatic=True):
        identity = checkpoint_id(self, session_key, project_id)
        try:
            record = self.read(identity, session_key=session_key, project_id=project_id)
        except KeyError:
            return ""
        if not include_automatic and record["source"].startswith("automatic:"):
            return ""
        return f"[Saved task checkpoint {identity}, revision {record['revision']}; source: {record['source']}]\n{record['content'][:max_chars]}"

    def record_compaction(self, session_key, summary, source, project_id=None):
        identity = checkpoint_id(self, session_key, project_id)
        try:
            previous = self.read(identity, maintenance=True)
        except KeyError:
            previous = None
        # Do not overwrite an execution model's explicit milestone checkpoint with a lossy summary.
        if previous and not previous["source"].startswith("automatic:"):
            return
        return self.checkpoint(session_key, summary[:16000], "automatic:" + source,
                               project_id=project_id, expected_revision=previous["revision"] if previous else None)

    def ingest_history(
        self,
        cursor: int | str,
        content: str,
        session_key: str | None = None,
        source_refs: list[dict[str, Any]] | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any] | None:
        if len(content) > 64000:
            for part in range(0, len(content), 60000):
                self.ingest_history(f"{cursor}-part-{part // 60000}", content[part:part + 60000], session_key, source_refs, timestamp)
            return
        identity = "history-" + str(cursor)
        with self.connect() as db:
            if db.execute("SELECT 1 FROM memories WHERE id=?", (identity,)).fetchone():
                return
        # Archived input carries its owning project at the time it was produced when available.
        project = next((ref.get("project_id") for ref in source_refs or [] if ref.get("project_id")), None)
        return self.save(content or "(empty archive)", source=f"memory/history.jsonl#cursor-{cursor}",
                         memory_id=identity, session_key=session_key or "legacy", project_id=project,
                         scope="project" if project else "session", layer="event", source_refs=source_refs,
                         created_at=timestamp, observed_at=timestamp)

    def archive_messages(self, messages, session_key, project_id=None, *, preserve_system=False):
        """Stream an immutable evidence copy before lossy compaction; keep exact messages on disk."""
        from cirno_memory.evidence import write_evidence

        evidence = write_evidence(self.root / "sources", session_key, messages,
                                  preserve_system=preserve_system, project_id=project_id)
        identity, path = evidence.identity, evidence.path
        try:
            saved = self.read(identity, maintenance=True)
            return {**saved, "evidence_path": str(path), "message_count": evidence.message_count}
        except KeyError:
            pass
        content = f"Archived conversation evidence: {path.relative_to(self.home)}\n"
        # The original remains complete; the directory record is intentionally small.
        content += evidence.preview
        saved = self.save(content, source=str(path.relative_to(self.home)), session_key=session_key,
                         project_id=project_id, scope="project" if project_id else "session", layer="source",
                         kind="source", memory_id=identity, enqueue=False)
        return {**saved, "evidence_path": str(path), "message_count": evidence.message_count}

    def consolidation_inputs(self, session_key, project_id=None, *, limit=8, max_chars=8000, include_user=False):
        """Complete pending records in exactly the owning consolidation scope."""
        clause, owner = ("m.scope='project' AND m.project_id=?", project_id) if project_id else ("m.scope='session' AND m.session_key=?", session_key)
        if include_user and project_id is None:
            clause = "(" + clause + " OR m.scope='user')"
        with self.connect() as db:
            rows = db.execute(f"SELECT m.body FROM dream_queue q JOIN memories m ON m.id=q.memory_id WHERE {clause} AND m.status='active' AND q.lease_until<=? ORDER BY q.queued_at LIMIT ?", (owner, time.time(), limit)).fetchall()
        records, size = [], 0
        for row in rows:
            record = json.loads(row[0])
            content = self.body_content(record)
            if size + len(content) > max_chars:
                continue
            records.append({**record, "content": content})
            size += len(content)
        return records

    def settle_consolidation(self, token, inputs, targets, *, session_key, project_id=None):
        """Consume only unchanged inputs explicitly reviewed by the single pass."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for record in inputs:
                row = db.execute("SELECT revision,lease_until FROM dream_queue WHERE memory_id=?", (record["id"],)).fetchone()
                if row is None or row["revision"] != record["revision"] or row["lease_until"] > time.time():
                    continue
                # Body edits outside the catalog must not acknowledge stale evidence.
                current = self.read(record["id"], session_key=session_key, project_id=project_id)
                if current["content_hash"] != record["content_hash"]:
                    continue
                ids = list(dict.fromkeys(targets.get(record["id"], [])))
                db.execute("INSERT OR REPLACE INTO dream_receipts VALUES(?,?,?,?,?,?,?)", (
                    token, record["id"], record["revision"], "created" if ids else "skipped",
                    json.dumps(ids), record["review_reason"], now()))
                db.execute("DELETE FROM dream_queue WHERE memory_id=? AND revision=?", (record["id"], record["revision"]))

    def pending(self, *, limit=20, max_chars=12000, lease_seconds=600):
        token = uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = time.time()
            if db.execute("SELECT 1 FROM dream_queue WHERE lease_until>? LIMIT 1", (current,)).fetchone():
                return None
            rows = db.execute("""SELECT m.body FROM dream_queue q JOIN memories m ON m.id=q.memory_id
                WHERE q.retry_after<=? AND q.attempts<3 AND m.status='active' ORDER BY q.queued_at LIMIT ?""", (current, limit)).fetchall()
            records, length, owner = [], 0, None
            for row in rows:
                record = json.loads(row[0])
                record_owner = scope_identity(record)
                if owner is not None and record_owner != owner:
                    continue
                owner = record_owner
                content = self.body_content(record)
                if records and length + len(content) > max_chars:
                    break
                # Large records remain readable in full through the memory tool.
                record["content"] = content[:max_chars]
                length += len(record["content"])
                records.append(record)
                db.execute("UPDATE dream_queue SET lease=?,lease_until=?,claimed_revision=revision,attempts=attempts+1 WHERE memory_id=?", (token, current + lease_seconds, record["id"]))
            return (token, records) if records else None

    def renew(self, token, lease_seconds=600):
        with self.connect() as db:
            return db.execute("UPDATE dream_queue SET lease_until=? WHERE lease=?", (time.time() + lease_seconds, token)).rowcount

    def confirm(self, token, memory_id, input_revision, outcome, targets=None, reason="", **access):
        """Acknowledge one claimed input only after checking its durable result."""
        if outcome not in {"created", "merged", "skipped", "failed"} or not reason.strip():
            raise ValueError("Choose created/merged/skipped/failed and explain the disposition")
        targets = list(dict.fromkeys(targets or []))
        if len(targets) > 10 or outcome in {"created", "merged"} and not targets:
            raise ValueError("created/merged requires 1–10 target knowledge IDs")
        if targets and outcome in {"skipped", "failed"}:
            raise ValueError("skipped/failed must explain the input without target IDs")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT claimed_revision,lease_until FROM dream_queue WHERE memory_id=? AND lease=?", (memory_id, token)).fetchone()
            if not row or row["lease_until"] < time.time() or row["claimed_revision"] != input_revision:
                raise ValueError("Input is not leased by this Dream batch at that revision")
            original = self.read(memory_id, **access)
            if original["revision"] != input_revision:
                raise ValueError("Input changed during Dream; leave it queued for another pass")
            if _hash(original["content"]) != original["content_hash"]:
                raise ValueError("Input body differs from its saved revision")
            validated = []
            for identity in targets:
                target = self.read(identity, **access)
                if target["layer"] != "knowledge" or target["status"] != "active" or identity == memory_id:
                    raise ValueError("Target must be a separate active knowledge record")
                if _hash(target["content"]) != target["content_hash"]:
                    raise ValueError("Target body differs from the saved revision")
                grounded = target.get("based_on") == memory_id and target.get("based_on_revision") == input_revision
                grounded = grounded or db.execute("SELECT 1 FROM links WHERE source=? AND target=? AND relation IN ('supports','derived_from')", (identity, memory_id)).fetchone()
                if not grounded:
                    raise ValueError("Target must cite this input through based_on or an evidence link")
                validated.append({"id": identity, "revision": target["revision"], "content_hash": target["content_hash"]})
            db.execute("INSERT OR REPLACE INTO dream_receipts VALUES(?,?,?,?,?,?,?)", (
                token, memory_id, input_revision, outcome, json.dumps(validated), reason[:2000], now()))
        return {"memory_id": memory_id, "input_revision": input_revision, "outcome": outcome, "targets": validated}

    def finish(self, token, *, error=None, preempted=False):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if preempted:
                retained = db.execute("SELECT count(*) FROM dream_queue WHERE lease=?", (token,)).fetchone()[0]
                db.execute("UPDATE dream_queue SET lease=NULL,lease_until=0,attempts=max(0,attempts-1),retry_after=0 WHERE lease=?", (token,))
                return {"retained": retained, "preempted": True}
            counts = dict(created=0, merged=0, skipped=0, failed=0, retained=0)
            rows = db.execute("SELECT * FROM dream_queue WHERE lease=?", (token,)).fetchall()
            for row in rows:
                identity = row["memory_id"]
                current = db.execute("SELECT revision FROM memories WHERE id=?", (identity,)).fetchone()
                if not current or current[0] != row["claimed_revision"] or row["revision"] != row["claimed_revision"]:
                    db.execute("UPDATE dream_queue SET lease=NULL,lease_until=0 WHERE memory_id=?", (identity,))
                    counts["retained"] += 1
                    continue
                receipt = db.execute("SELECT * FROM dream_receipts WHERE token=? AND memory_id=? AND input_revision=?", (token, identity, row["claimed_revision"])).fetchone()
                failure = str(error) if error else "Dream ended without per-input confirmation"
                valid = receipt is not None and receipt["outcome"] != "failed"
                if valid:
                    for target in json.loads(receipt["targets"]):
                        revision = db.execute("SELECT path,body FROM revisions WHERE memory_id=? AND revision=?", (target["id"], target["revision"])).fetchone()
                        if not revision or not (self.home / revision["path"]).is_file() or json.loads(revision["body"])["content_hash"] != target["content_hash"] or _hash((self.home / revision["path"]).read_text(encoding="utf-8")) != target["content_hash"]:
                            valid = False
                            failure = "Confirmed target revision is missing or changed"
                            break
                if valid:
                    db.execute("DELETE FROM dream_queue WHERE memory_id=? AND lease=?", (identity, token))
                    counts[receipt["outcome"]] += 1
                else:
                    if receipt and receipt["outcome"] == "failed":
                        failure = receipt["reason"]
                    counts["failed"] += 1
                    counts["retained"] += 1
                    db.execute("UPDATE dream_queue SET lease=NULL,lease_until=0,error=?,retry_after=? WHERE memory_id=?", (failure[:1000], time.time() + 60, identity))
            report = {"at": now(), "error": str(error) if error else ("Unconfirmed or failed inputs remain queued" if counts["retained"] else None), **counts}
            db.execute("INSERT OR REPLACE INTO dream_state VALUES('last_dream',?)", (json.dumps(report),))
            return counts

    def receipts(self, *, limit=20):
        with self.connect() as db:
            return {"receipts": [dict(row) for row in db.execute("SELECT memory_id,input_revision,outcome,targets,reason,created_at FROM dream_receipts ORDER BY rowid DESC LIMIT ?", (min(50, max(1, int(limit))),))]}

    def retry_failed(self):
        with self.connect() as db:
            return {"retried": db.execute("UPDATE dream_queue SET attempts=0,error=NULL,retry_after=0 WHERE (error IS NOT NULL OR attempts>=3) AND memory_id IN (SELECT id FROM memories WHERE status='active') AND lease_until<=?", (time.time(),)).rowcount}

    def status(self, *, session_key=None, project_id=None, maintenance=True):
        visibility, args = "1", []
        if not maintenance:
            visibility, args = visibility_filter(session_key, project_id)
        active = f"m.status='active' AND {visibility}"
        failed = f"{active} AND (error IS NOT NULL OR attempts>=3)"
        with self.connect() as db:
            counts = {row[0]: row[1] for row in db.execute(f"SELECT layer,count(*) FROM memories m WHERE {visibility} GROUP BY layer", args)}
            last = db.execute("SELECT value FROM dream_state WHERE key='last_dream'").fetchone() if maintenance else None
            return {"counts": counts,
                    "pending": db.execute(f"SELECT count(*) FROM dream_queue q JOIN memories m ON m.id=q.memory_id WHERE {active}", args).fetchone()[0],
                    "failed": db.execute(f"SELECT count(*) FROM dream_queue q JOIN memories m ON m.id=q.memory_id WHERE {failed}", args).fetchone()[0],
                    "last_dream": json.loads(last[0]) if last else None,
                    "failures": [dict(row) for row in db.execute(f"SELECT q.memory_id,q.revision,q.attempts,q.error FROM dream_queue q JOIN memories m ON m.id=q.memory_id WHERE {failed} ORDER BY queued_at LIMIT 10", args)],
                    "engine": "sqlite-fts5-bm25",
                    "index_bytes": (self.root / "search.sqlite3").stat().st_size,
                    "databases": {path.name: path.stat().st_size for path in (self.root / f"{name}.sqlite3" for name in ("catalog", "search", "dream", "vectors")) if path.exists()}, "embedding_loaded": False}


    def reconcile(self, *, rebuild=False, limit=100):
        """Bounded cursor scan for manual edits; no permanent filesystem watcher or corpus cache."""
        with self.connect() as db:
            cursor_key = "rebuild_cursor" if rebuild else "scan_cursor"
            cursor = db.execute("SELECT value FROM maintenance WHERE key=?", (cursor_key,)).fetchone()
            after = cursor[0] if cursor else ""
            rows = db.execute("SELECT body FROM memories WHERE id>? ORDER BY id LIMIT ?", (after, limit)).fetchall()
        changed, missing = 0, []
        for row in rows:
            record = json.loads(row[0])
            if record["layer"] == "profile":
                if rebuild:
                    with self.connect() as db:
                        db.execute("BEGIN IMMEDIATE")
                        if db.execute("SELECT revision FROM memories WHERE id=?", (record["id"],)).fetchone()[0] == record["revision"]:
                            self._put_record(db, record, self.body_content(record))
                            changed += 1
                continue
            # Editable mirror is the public Home file; revisions are immutable evidence.
            mirror = self.root / "entries" / (record["id"] + ".md")
            if not mirror.is_file():
                missing.append(record["id"])
                record["status"] = "archived"
                with self.connect() as db:
                    db.execute("UPDATE memories SET status='archived',body=? WHERE id=? AND revision=?", (json.dumps(record, ensure_ascii=False), record["id"], record["revision"]))
                continue
            content = mirror.read_text(encoding="utf-8")
            if _hash(content) != record["content_hash"]:
                self.save(content, source=record["source"], session_key=record["session_key"],
                          project_id=record.get("project_id"), scope=record["scope"], kind=record["kind"],
                          layer=record["layer"], title=record["title"], tags=record["tags"], source_refs=record["source_refs"],
                          memory_id=record["id"], expected_revision=record["revision"], maintenance=True)
                changed += 1
            elif rebuild:
                with self.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    if db.execute("SELECT revision FROM memories WHERE id=?", (record["id"],)).fetchone()[0] == record["revision"]:
                        self._put_record(db, record, content)
                        changed += 1
        with self.connect() as db:
            db.execute("DELETE FROM dream_queue WHERE lease_until<=? AND memory_id IN (SELECT id FROM memories WHERE status!='active' OR layer IN ('task','source','profile'))", (time.time(),))
            db.execute("INSERT OR REPLACE INTO maintenance VALUES(?,?)", (cursor_key, json.loads(rows[-1][0])["id"] if len(rows) == limit else ""))
        return {"indexed": changed, "missing": missing, "scanned": len(rows), "has_more": len(rows) == limit}

    def sync_profiles(self):
        from filelock import FileLock

        # Memory tools, settings requests and idle maintenance share these
        # deterministic IDs. Keep their read-before-save sequence atomic.
        with FileLock(self.root / ".profiles.lock", timeout=10):
            self._sync_profiles()

    def _sync_profiles(self):
        # Large manually edited profiles are streamed into bounded index records.
        for relative in ("SOUL.md", "WORKER.md", "USER.md", "memory/MEMORY.md"):
            path = self.home / relative
            prefix = "profile-" + _hash(relative)[:16]
            seen = set()
            if path.is_file():
                with path.open(encoding="utf-8") as stream:
                    part = 0
                    while content := stream.read(60000):
                        identity = prefix if part == 0 else f"{prefix}-part-{part}"
                        part += 1
                        if not content.strip():
                            continue
                        seen.add(identity)
                        with self.connect() as db:
                            row = db.execute("SELECT revision,content_hash,status FROM memories WHERE id=?", (identity,)).fetchone()
                        if row and row[1] == _hash(content) and row[2] == "active":
                            continue
                        self.save(content, source=relative, session_key="profile", scope="user", layer="profile",
                                  kind="fact", title=relative + (f" [{part}]" if part > 1 else ""), memory_id=identity,
                                  expected_revision=row[0] if row else None, enqueue=False, maintenance=True, status="active")
            with self.connect() as db:
                for row in db.execute("SELECT body FROM memories WHERE id=? OR id LIKE ?", (prefix, prefix + "-part-%")):
                    record = json.loads(row[0])
                    if record["id"] not in seen and record["status"] != "archived":
                        record["status"] = "archived"
                        db.execute("UPDATE memories SET status='archived',body=? WHERE id=? AND revision=?",
                                   (json.dumps(record, ensure_ascii=False), record["id"], record["revision"]))

    def read_source(self, identity, *, start_line=1, limit=20, char_offset=0, revision=None, **access):
        from cirno_memory.evidence import read_evidence

        return read_evidence(self, identity, start_line=start_line, limit=limit,
                             char_offset=char_offset, revision=revision, **access)
