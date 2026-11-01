"""Opt-in semantic search. Model inference lives only in a disposable CPU child.

The default gateway imports neither numpy, tokenizers nor ONNX Runtime. Vector
rows are streamed from SQLite; no corpus matrix or permanent model is resident.
"""
from __future__ import annotations

import hashlib
import json
import os
import selectors
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()


class EmbeddingWorker:
    def __init__(self, config):
        self.config = config
        self.process = None
        self.peak_mb = 0.0

    def __enter__(self):
        for value in (self.config.embedding_model_path, self.config.embedding_tokenizer_path):
            if not value or not Path(value).expanduser().is_file():
                raise ValueError("Choose an existing ONNX model and matching tokenizer.json in memory settings")
        self.process = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("embedding_worker.py")),
             str(Path(self.config.embedding_model_path).expanduser()), str(Path(self.config.embedding_tokenizer_path).expanduser())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1, env={**os.environ, "TOKENIZERS_PARALLELISM": "false", "OMP_NUM_THREADS": "1"},
        )
        return self

    def request(self, texts, **options):
        process = self.process
        assert process is not None and process.stdin and process.stdout
        process.stdin.write(json.dumps({"texts": texts, **options}, ensure_ascii=False) + "\n")
        process.stdin.flush()
        deadline = time.monotonic() + self.config.embedding_timeout_seconds
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while time.monotonic() < deadline:
                # Monitor the whole child RSS, including imports and ONNX initialization.
                if os.name == "posix":
                    measured = subprocess.run(["ps", "-o", "rss=", "-p", str(process.pid)], capture_output=True, text=True, timeout=2)
                    rss = float(measured.stdout.strip() or 0) / 1024
                    self.peak_mb = max(self.peak_mb, rss)
                    if rss > self.config.embedding_max_rss_mb:
                        raise MemoryError(f"Embedding worker exceeded {self.config.embedding_max_rss_mb} MB RSS ({rss:.1f} MB); using BM25")
                if selector.select(timeout=0.05):
                    line = process.stdout.readline()
                    if not line:
                        raise RuntimeError("Embedding worker exited; install cirno-ai[memory-embedding] and verify model files")
                    result = json.loads(line)
                    self.peak_mb = max(self.peak_mb, result.get("peak_mb", 0))
                    if self.peak_mb > self.config.embedding_max_rss_mb:
                        raise MemoryError(f"Embedding worker peak {self.peak_mb:.1f} MB exceeds configured limit; using BM25")
                    if result.get("error"):
                        raise RuntimeError(result["error"])
                    return result
        raise TimeoutError("Embedding worker timed out; using BM25")

    def __exit__(self, *_):
        if self.process:
            if self.process.stdin:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
            if self.process.stdout:
                self.process.stdout.close()


def _fingerprint(config):
    digest = hashlib.sha256(b"bge-token-chunks-224-stride-192-v1")
    for value in (config.embedding_model_path, config.embedding_tokenizer_path):
        with Path(value).expanduser().open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
    return digest.hexdigest()


def search(repo, query, config, *, mode="hybrid", limit=10, **filters):
    """Index at most 32 token chunks per explicit search, then stream cosine scores."""
    neighbor_limit = filters.pop("expand_links", 3)
    lexical = repo.search(query, limit=limit, expand_links=neighbor_limit, **filters)
    if not config.embedding_enabled:
        return {**lexical, "warning_code": "disabled", "warning": "Local semantic retrieval is disabled; using BM25"}
    if not _LOCK.acquire(blocking=False):
        return {**lexical, "warning_code": "busy", "warning": "Embedding worker is busy; using BM25"}
    try:
        fingerprint = _fingerprint(config)
        access_clauses = ["m.status='active'", "m.layer IN ('knowledge','profile')"]
        args = []
        if not filters.get("maintenance"):
            access_clauses.append("(m.scope='user' OR m.session_key=? OR (m.scope='project' AND m.project_id=?))")
            args += [filters.get("session_key") or "", filters.get("project_id") or ""]
        for column in ("scope", "layer"):
            if filters.get(column) and filters[column] != "all":
                access_clauses.append(f"m.{column}=?")
                args.append(filters[column])
        for tag in filters.get("tags") or []:
            access_clauses.append("EXISTS(SELECT 1 FROM json_each(m.body,'$.tags') WHERE value=?)")
            args.append(tag.strip().casefold())
        from cirno.memory.repository import time_conditions
        dates, date_args = time_conditions(filters.get("since"), filters.get("until"), filters.get("time_field", "observed_at"), filters.get("time_zone", "UTC"))
        access_clauses.extend(dates)
        args.extend(date_args)
        where = " AND ".join(access_clauses)
        if filters.get("purpose") == "evidence":
            return {**lexical, "warning_code": "lexical_only", "warning": "Original evidence uses full-text BM25; semantic search indexes distilled knowledge only"}
        with repo.connect(vectors=True) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS vectors.vector_records (
                    memory_id TEXT,fingerprint TEXT,content_hash TEXT,next_chunk INTEGER,completed INTEGER,
                    PRIMARY KEY(memory_id,fingerprint)
                );
                CREATE TABLE IF NOT EXISTS vectors.vector_chunks (
                    memory_id TEXT,fingerprint TEXT,content_hash TEXT,chunk_index INTEGER,start_char INTEGER,end_char INTEGER,vector BLOB,
                    PRIMARY KEY(memory_id,fingerprint,chunk_index)
                );
            """)
        with EmbeddingWorker(config) as worker:
            query_vector = worker.request([query[:2000]])["vectors"][0]
            budget = 32
            with repo.connect(vectors=True) as db:
                rows = db.execute(f"""SELECT m.body,e.content_hash,e.next_chunk FROM memories m
                    LEFT JOIN vector_records e ON e.memory_id=m.id AND e.fingerprint=?
                    WHERE {where} AND (e.content_hash IS NULL OR e.content_hash!=m.content_hash OR e.completed=0)
                    ORDER BY m.id LIMIT 33""", [fingerprint, *args]).fetchall()
            for row in rows[:32]:
                if not budget:
                    break
                record = json.loads(row[0])
                content = repo._body_path(record).read_text(encoding="utf-8")
                start_chunk = row["next_chunk"] if row["content_hash"] == record["content_hash"] else 0
                while budget:
                    batch = worker.request([content], chunked=True, start_chunk=start_chunk, max_chunks=min(8, budget))
                    chunks = batch["chunks"]
                    with repo.connect(vectors=True) as db:
                        db.execute("DELETE FROM vector_chunks WHERE memory_id=? AND fingerprint=? AND content_hash!=?", (record["id"], fingerprint, record["content_hash"]))
                        for chunk, vector in zip(chunks, batch["vectors"], strict=True):
                            db.execute("INSERT OR REPLACE INTO vector_chunks VALUES(?,?,?,?,?,?,?)", (
                                record["id"], fingerprint, record["content_hash"], chunk["chunk_index"],
                                chunk["start_char"], chunk["end_char"], struct.pack(f"{len(vector)}f", *vector)))
                        start_chunk += len(chunks)
                        db.execute("INSERT OR REPLACE INTO vector_records VALUES(?,?,?,?,?)", (
                            record["id"], fingerprint, record["content_hash"], start_chunk, int(not batch["has_more"])))
                    budget -= len(chunks)
                    if not batch["has_more"] or not chunks:
                        break
            # Keep only top distinct records while streaming disk vectors.
            best = {}
            with repo.connect(vectors=True) as db:
                for row in db.execute(f"SELECT m.body,e.vector,e.start_char,e.end_char,e.chunk_index FROM memories m JOIN vector_chunks e ON e.memory_id=m.id AND e.content_hash=m.content_hash WHERE e.fingerprint=? AND {where}", [fingerprint, *args]):
                    vector = struct.unpack(f"{len(row[1]) // 4}f", row[1])
                    if len(vector) != len(query_vector):
                        continue
                    score = sum(a*b for a, b in zip(vector, query_vector))
                    record = json.loads(row[0])
                    identity = record["id"]
                    if identity in best and best[identity][0] >= score:
                        continue
                    if identity not in best and len(best) >= limit:
                        lowest = min(best, key=lambda key: best[key][0])
                        if score <= best[lowest][0]:
                            continue
                        del best[lowest]
                    best[identity] = (score, record, row["start_char"], row["end_char"], row["chunk_index"])
                pending = db.execute(f"""SELECT 1 FROM memories m LEFT JOIN vector_records e ON e.memory_id=m.id AND e.fingerprint=?
                    WHERE {where} AND (e.content_hash IS NULL OR e.content_hash!=m.content_hash OR e.completed=0) LIMIT 1""", [fingerprint, *args]).fetchone() is not None
            semantic = []
            for score, record, start, end, chunk_index in sorted(best.values(), key=lambda item: item[0], reverse=True):
                content = repo._body_path(record).read_text(encoding="utf-8")
                semantic.append(dict(record, score=score, snippet=content[start:end], start_char=start, end_char=end, chunk_index=chunk_index))
            results = semantic
            if mode == "hybrid":
                scores, records = {}, {}
                for ranked in (lexical["memories"], semantic):
                    for rank, record in enumerate(ranked, 1):
                        records[record["id"]] = record
                        scores[record["id"]] = scores.get(record["id"], 0) + 1 / (60 + rank)
                results = [dict(records[key], score=score) for key, score in sorted(scores.items(), key=lambda pair: pair[1], reverse=True)[:limit]]
            repo.expand_links(results, limit=neighbor_limit, session_key=filters.get("session_key"), project_id=filters.get("project_id"), maintenance=filters.get("maintenance", False))
            return {"memories": results, "engine": mode, "has_more": False, "next_offset": 0,
                    "embedding_index_pending": pending, "worker_peak_mb": round(worker.peak_mb, 1)}
    except (OSError, ValueError, RuntimeError, MemoryError, TimeoutError, subprocess.SubprocessError) as exc:
        return {**lexical, "warning_code": "unavailable", "warning": str(exc)}
    finally:
        _LOCK.release()
