# Disk-first memory

Cirno defaults to files and SQLite FTS5/BM25. It does not load an embedding model, run a vector database or search memory before every reply. Profiles, evidence, memory and Skills live in Home; workspaces contain task artifacts. The independent `cirno-memory` package owns retrieval and evidence stores; core coordinates Dream and compaction.

## Recall and editing

Settings separates Memory library, Context compaction, Dream consolidation and Memory retrieval. Settings → Personality edits Router and Worker personalities, user preferences and workflow instructions. Settings → Agent heartbeat edits heartbeat instructions. The memory library and Agent tools share `cirno_memory.search`: BM25 is the default, with optional semantic and hybrid modes. Filters include layer, scope, tags and dates. The interface reports the actual engine, fallback reason and unfinished vector-index coverage.

An empty query browses records without launching an embedding worker. Evidence, task state and searches including historical records use BM25 because optional vectors do not cover all those records. Open a result to inspect its body, versions and original evidence. Search pagination retains the submitted filters while the next query is being edited. Evidence pages identify the resolved source record and revision; continuation and retry retain that revision, including when a historical finding points to a separate captured source. Index rebuilding is incremental and can be stopped and resumed. Dream failures expose their reasons and can be retried.

Use `memory.search`, then `memory.read`. Default recall returns knowledge, task checkpoints and profiles. Use `purpose="evidence"` for events and original messages, or `purpose="all"` for both. `memory.tags` discovers visible tag names and counts. `expand_links` adds bounded one-hop relationships: three by default, at most ten across the results. There is no reranker.

Exact values, dates, quotations and prior decisions should be checked against original evidence. A stored URL or Node path establishes a reference, not that Cirno accessed or independently verified it.

## Layers and scopes

| Layer | Purpose | Recovery |
| --- | --- | --- |
| `profile` | Preferences and a brief shared overview | Bounded `memory/MEMORY.md` injection; other profiles follow their normal loading rules |
| `task` | Objective, results, blockers, next steps and artifact references | Checkpoint injected by conversation identity, independently of Dream |
| `event` | Saved observations and compaction increments | On-demand retrieval and the Dream queue |
| `knowledge` | Grounded facts, hypotheses, decisions and lessons | On-demand retrieval |
| `source` | Immutable original messages captured before compaction | Paged reads by source ID, line and character offset |

Records have `user`, `project` or `session` scope. Structured retrieval, reads, evidence, revisions, links, tags, statistics and semantic results enforce the same visibility rules. Project identity uses a project ID rather than inferring identity from a working directory. A record's originating session is provenance: moving that conversation out of a Project does not retain access to the Project's memory. Session-scoped records remain accessible to their own conversation. Full Access file and shell tools follow their own access rules; memory scopes are not operating-system isolation.

Large files, web artifacts and Node job output remain at their original locations. Memory stores their references instead of copying entire workspaces.

Immutable memory bodies are checked against their recorded content hash on reads, including historical revisions and semantic indexing/snippet extraction. A mismatch is reported rather than returning altered content. Scope identity uses the user scope, Project ID or conversation key; Project records from different Workers in the same Project can be revised or linked without changing their originating-session metadata. `WORKER.md` is indexed alongside the shared profiles, and removing a profile removes its active indexed record. Original evidence reads are paged with line and character cursors and a 16,000-character total page limit, including memory-body pointers and very long individual lines. Building the source index also reads bounded fragments, retaining line numbers and overlaps without loading an entire JSONL line.

## Compaction, checkpoints and Dream

Before compaction, Cirno streams original messages to disk and saves the compaction increment in a durable queue. The executing model saves explicit task checkpoints at milestones and before compaction; automatic summaries do not overwrite them. Task recovery does not depend on a successful Dream run.

Task checkpoints have separate conversation/Project slots. Switching or removing Project membership selects the corresponding slot; switching back restores that Project's checkpoint. Legacy conversation-only checkpoint IDs remain readable and writable when their stored scope matches the current Project or unfiled conversation. Automatic compaction respects the same selection and cannot overwrite an explicit checkpoint in that slot.

Journal append and retention share a file lock across instances. Cursor files are replaced atomically. Invalid journal records or cursor counters stop the affected operation with a file location; retention leaves the original file intact. Restore or correct that file before retrying.

Task checkpoints and current `MEMORY.md` content are attached as model-only evidence to the fresh input and saved with that exact input before the model request. Later updates do not rewrite the system prompt or earlier messages. Skill and tool declarations use deterministic ordering. Claude cache breakpoints cover the latest cacheable input, including first-turn documents and tool results. Changes to system instructions, personality profiles, available tools or compacted summaries still change the request prefix and can invalidate provider caches.

Token totals include cached input; they are not a billable-cost estimate. The cache hit rate divides provider-reported cache reads by input tokens from requests that report cache metrics. Missing cache metrics are unknown, not misses. Cache persistence and pricing remain provider-specific.

By default Dream runs after 180 seconds of foreground inactivity, processing at most eight inputs and 16,000 characters per batch, with up to 24 model iterations. Interval mode is also available. Each batch has one visibility scope. Derived records inherit their evidence scope and version; project/session batches cannot edit shared profiles. Dream's file tools cannot read configuration or modify original evidence logs.

Leases prevent simultaneous processing, and long calls renew them. New foreground input interrupts automatic idle Dream, releases the lease and does not consume a failure attempt. Knowledge already saved remains; a later run searches for duplicates. Inputs changed during processing stay queued.

Manual and scheduled Dream runs share the same batch lifecycle. Manual runs are tracked background tasks and finish before service shutdown completes. Failed preparation or execution releases the batch for retry and preserves the cursor. Errors reach the command or scheduler; manual runs also send a failure message to their source conversation.

Dream must call its restricted `memory.confirm` operation for every input revision:

| Outcome | Meaning |
| --- | --- |
| `created` | Saved grounded knowledge citing the input |
| `merged` | Added the evidence to existing knowledge |
| `skipped` | No durable update, with a concrete reason |
| `failed` | Unresolved processing error |

Confirmation validates the lease, input revision, target knowledge, revision-body hash and evidence relationship. A normal model response does not confirm a batch. Missing, failed or invalid confirmations stay queued; successful and failed inputs can coexist. Ordinary failures retain their cause and back off, with at most three automatic attempts before manual retry. Receipts survive restart. Ordinary conversations cannot acknowledge Dream inputs.

The default `releaseArchivedRuntime` behavior releases compacted runtime prefixes only after originals are saved. Display history remains in conversation SQLite storage. Old prefixes are streamed rather than loaded wholesale; the recent runtime-snapshot cache is bounded to eight conversations. Disabling release retains full runtime prefixes and can increase memory use during long work.

## Revisions and maintenance

Updates require the `expected_revision` just read. Historical bodies are retained. Relations include `supports`, `conflicts`, `related`, `derived_from` and `supersedes`. Superseded findings leave default search results but remain readable.

Time filters default to event occurrence (`observed_at`); unknown dates are not guessed. Use `time_field="created_at"` or `"updated_at"` for storage/edit times. Derived knowledge inherits its primary evidence's occurrence time unless explicitly supplied. Dates and naive times use the configured timezone, overridable through `time_zone`; a date-only upper bound includes that entire day.

Managed edits update the index immediately. Idle scans detect changes and deletions in Markdown mirrors in bounded batches. Shortened or deleted profiles lose stale search chunks. Original evidence is indexed in full, rather than indexing only summaries or file headers.

| Path inside Home | Role |
| --- | --- |
| `memory/MEMORY.md` | Shared overview, with a default 2,000-token injection budget |
| `memory/entries/<id>.md` | Editable body mirrors |
| `memory/revisions/<id>/<revision>.md` | Retained historical bodies |
| `memory/sources/<id>.jsonl` | Original messages, paged by line and character offset |
| `memory/catalog.sqlite3` | Authoritative metadata, revisions and evidence links |
| `memory/search.sqlite3` | Rebuildable text chunks and FTS5/BM25 index |
| `memory/dream.sqlite3` | Queue, leases, receipts and processing status |
| `memory/vectors.sqlite3` | Optional vector chunks and incremental indexing state |
| `memory/history.jsonl` | Compaction journal |
| `skills/` and `skills-history/` | Home Skills and retained versions |

Catalog, search and queue writes use attached SQLite databases and rollback-journal transactions. Each database has a 512 KiB page-cache setting; splitting stores does not load the corpus into memory.

Back up the entire instance root while the service is stopped; Agent Home is its `home/` subdirectory. Catalog and Dream databases contain authoritative state. Search and vectors are derived indexes; after losing the text index, perform a full rebuild in Settings. Vector chunks regenerate on explicit searches. Markdown alone cannot restore scopes, revisions, links or processing state. Evidence and revisions do not expire automatically, so disk usage grows with history.

Checkpoint writes and evidence capture run outside the server event loop, including provider-failure and exhausted-budget fallbacks. Runtime history is released only after its checkpoint is committed. Dream renews its batch lease during provider calls; a failed renewal stops the run and leaves its inputs recoverable.

## Optional embeddings

For the local engine, install the `memory-embedding` extra, then configure a local BGE-small INT8 ONNX model and matching `tokenizer.json` in Settings → Memory retrieval. Model files are not downloaded automatically. The worker uses normalized CLS vectors and one CPU thread. ONNX Runtime, NumPy and tokenizers stay out of the default server process.

Explicit semantic/hybrid retrieval launches a disposable worker. Vectors are cached on disk by model and content fingerprints; similarity scoring streams stored vectors. Only distilled knowledge and shared profiles are embedded. Long records use 224-token windows with a 192-token stride and retain character offsets. Each search generates at most 32 chunks, with at most eight per worker response. Remaining progress is persisted for the next explicit search. A record ranks by its best matching chunk. Hybrid retrieval uses reciprocal-rank fusion.

Missing dependencies, invalid models, a busy worker, timeout or an RSS-limit violation return BM25 results with a reason. The default worker budget is 200 MiB, checked through process RSS sampling. Embeddings remain disabled by default. The worker budget alone does not enforce a total-service limit. Deployments can set their own resource limits. Historical local benchmark results are archived under `references/`, not treated as a current performance guarantee.

The API engine uses an OpenAI-compatible embeddings endpoint instead of a local model. It shares the same on-disk vector index, scope filtering and hybrid search. API requests send the query and selected knowledge chunks to the configured service; no local inference libraries are loaded. The endpoint, model and chunk size identify the index. API failures return BM25 results with a visible reason. See [Memory retrieval](../memory-retrieval.md) for configuration and privacy details.
