"""Bounded relation snapshots for an explicitly selected memory page.

Reading the graph never loads an embedding model or memory document bodies.
Both endpoints must be visible, including when the caller supplies arbitrary IDs.
"""
from __future__ import annotations

from cirno_memory.scopes import visibility_filter

DEFAULT_GRAPH_NODES = 300
MAX_GRAPH_LINKS = 1500


def graph_node_limit(value):
    if type(value) is not int or value < 1:
        raise ValueError("Graph memory limit must be a positive integer")
    return value


def graph_ids(ids, *, max_nodes=DEFAULT_GRAPH_NODES):
    max_nodes = graph_node_limit(max_nodes)
    if not isinstance(ids, list) or len(ids) > max_nodes:
        raise ValueError(f"Select at most {max_nodes} memory IDs")
    if any(not isinstance(identity, str) or not identity or len(identity) > 100 for identity in ids):
        raise ValueError("Memory IDs must be nonempty strings of at most 100 characters")
    return list(dict.fromkeys(ids))


def memory_graph(repo, ids, *, maintenance=False, session_key=None, project_id=None, max_nodes=DEFAULT_GRAPH_NODES):
    ids = graph_ids(ids, max_nodes=max_nodes)
    if not ids:
        return {"links": [], "links_truncated": False}
    visibility, access = ("1", []) if maintenance else visibility_filter(session_key, project_id)
    with repo.connect() as db:
        # A temporary selection avoids SQLite's bound-variable ceiling for larger views.
        db.execute("CREATE TEMP TABLE graph_selection (id TEXT PRIMARY KEY)")
        db.executemany("INSERT INTO graph_selection VALUES (?)", ((identity,) for identity in ids))
        db.execute(
            "CREATE TEMP TABLE graph_visible AS SELECT m.id FROM memories m "
            f"JOIN graph_selection selected ON selected.id=m.id WHERE {visibility}", access,
        )
        rows = db.execute(
            "SELECT source,target,relation FROM links "
            "JOIN graph_visible selected_source ON selected_source.id=source "
            "JOIN graph_visible selected_target ON selected_target.id=target "
            "ORDER BY source,target,relation LIMIT ?", [MAX_GRAPH_LINKS + 1],
        ).fetchall()
    return {"links": [dict(row) for row in rows[:MAX_GRAPH_LINKS]],
            "links_truncated": len(rows) > MAX_GRAPH_LINKS}
