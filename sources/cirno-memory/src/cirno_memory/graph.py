"""Bounded relation snapshots for an explicitly selected memory page.

Reading the graph never loads an embedding model or memory document bodies.
Both endpoints must be visible, including when the caller supplies arbitrary IDs.
"""
from __future__ import annotations

from cirno_memory.scopes import visibility_filter

MAX_GRAPH_NODES = 300
MAX_GRAPH_LINKS = 1500


def graph_ids(ids):
    if not isinstance(ids, list) or len(ids) > MAX_GRAPH_NODES:
        raise ValueError(f"Select at most {MAX_GRAPH_NODES} memory IDs")
    if any(not isinstance(identity, str) or not identity or len(identity) > 100 for identity in ids):
        raise ValueError("Memory IDs must be nonempty strings of at most 100 characters")
    return list(dict.fromkeys(ids))


def memory_graph(repo, ids, *, maintenance=False, session_key=None, project_id=None):
    ids = graph_ids(ids)
    if not ids:
        return {"links": [], "links_truncated": False}
    placeholders = ",".join("?" for _ in ids)
    visibility, access = ("1", []) if maintenance else visibility_filter(session_key, project_id)
    with repo.connect() as db:
        visible = [row[0] for row in db.execute(
            f"SELECT m.id FROM memories m WHERE m.id IN ({placeholders}) AND {visibility}",
            [*ids, *access],
        )]
        if not visible:
            return {"links": [], "links_truncated": False}
        placeholders = ",".join("?" for _ in visible)
        rows = db.execute(
            f"SELECT source,target,relation FROM links WHERE source IN ({placeholders}) "
            f"AND target IN ({placeholders}) ORDER BY source,target,relation LIMIT ?",
            [*visible, *visible, MAX_GRAPH_LINKS + 1],
        ).fetchall()
    return {"links": [dict(row) for row in rows[:MAX_GRAPH_LINKS]],
            "links_truncated": len(rows) > MAX_GRAPH_LINKS}
