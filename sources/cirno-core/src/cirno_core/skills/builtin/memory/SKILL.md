---
name: memory
description: Retrieve exact past findings and decisions, preserve task checkpoints, and maintain source-backed memory with revisions and scoped links.
---

# Memory

The Home memory store is disk-backed. `MEMORY.md` supplies a small persistent overview; scoped memory is retrieved when needed, without automatic retrieval on every reply.

1. Search `memory__search(query="distinctive terms")`. BM25 supports Chinese and English, tags, layer, scope, dates and pagination. Prefer exact identifiers and precise keywords. Do not invent a result when no match exists.
2. Read the returned memory ID. For precise measurements or quotations, inspect `source` and `source_refs`; `memory__source()` pages original archived messages. Follow `next_char_offset` for a long source line before advancing `start_line`. External files/URLs/Nodes use their normal tools and access rules.
3. Save atomic records with sources, tags and kind: fact, observation, hypothesis or lesson. User scope is shared, project scope is project-specific, session scope is local. Derived knowledge uses `based_on` to inherit evidence visibility.
4. Update with the revision just read. Inspect `history` for earlier versions. Link supports/conflicts/related evidence; a new finding may `supersedes` an old one with an explanation. Preserve evidence and uncertainty.
5. Checkpoint long work at milestones and before compaction: objective, exact results, completed work, blockers, next actions, and artifact/Node/job references. This checkpoint is restored independently of Dream.

Idle Dream consolidates queued compaction increments and saved events. It may be interrupted by foreground work and resumed later. Original messages and immutable revisions remain under Home. Large artifacts stay at their original location. Semantic/hybrid retrieval is optional and explicitly requested; BM25 remains usable when the embedding worker is unavailable or over budget.


Default search recalls distilled knowledge, task state and profiles. Request `purpose=evidence` explicitly for raw originals or events not yet consolidated; `purpose=all` searches both. Discover visible tags using `memory__tags()`, and request up to ten one-hop neighbors via `expand_links`. Event date filters use `observed_at` by default; unknown occurrence dates are excluded. Choose `time_field=created_at`/`updated_at` for saved/edited dates. A date-only `until` includes the entire day. Semantic results identify their matching token chunk; pending chunks are completed by later explicit searches.
