"""Shared retrieval entry point for the agent and authenticated memory settings."""
from __future__ import annotations


def search(repo, query, config, *, mode="bm25", limit=10, **filters):
    if mode not in {"bm25", "semantic", "hybrid"}:
        raise ValueError("mode must be bm25, semantic or hybrid")
    limit = max(1, min(int(limit), 30))
    # Browsing metadata never starts an embedding worker.
    if mode == "bm25" or not query.strip():
        result = repo.search(query, limit=limit, **filters)
    elif filters.get("include_history") or filters.get("purpose") == "evidence" or filters.get("layer") in {"event", "source", "task"}:
        result = {**repo.search(query, limit=limit, **filters),
                  "warning_code": "lexical_only",
                  "warning": "Original evidence, task state and historical records use BM25; vectors index active knowledge and profiles only"}
    else:
        from cirno.memory.embedding import search as semantic_search
        result = semantic_search(repo, query, config, mode=mode, limit=limit, **filters)
    return {**result, "requested_mode": mode, "time_zone": filters.get("time_zone", "UTC")}
