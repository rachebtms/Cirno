# Disk-first memory

Cirno defaults to files and SQLite FTS5/BM25. It does not load an embedding model, run a vector database or search memory before every reply. Profiles, evidence, memory and Skills live in Home; workspaces contain task artifacts.

## Recall and editing

Settings separates Memory library, Context compaction, Dream consolidation and Memory retrieval. Settings → Personality edits personality, user preferences, workflow instructions and heartbeat instructions. The memory library and Agent tools share `memory/search.py`: BM25 is the default, with optional semantic and hybrid modes. Filters include layer, scope, tags and dates. The interface reports the actual engine, fallback reason and unfinished vector-index coverage.

An empty query browses records without launching an embedding worker. Evidence, task state and searches including historical records use BM25 because optional vectors do not cover all those records. Expand a result to read its body, versions and original evidence. Index rebuilding is incremental and can be stopped and resumed. Dream failures expose their reasons and can be retried.

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

Records have `user`, `project` or `session` scope. Structured retrieval, reads, evidence, revisions and links enforce scope. Project identity uses a project ID rather than inferring identity from a working directory. Full Access file and shell tools follow their own access rules; memory scopes are not operating-system isolation.

Large files, web artifacts and Node job output remain at their original locations. Memory stores their references instead of copying entire workspaces.

## Compaction, checkpoints and Dream

Before compaction, Cirno streams original messages to disk and saves the compaction increment in a durable queue. The executing model saves explicit task checkpoints at milestones and before compaction; automatic summaries do not overwrite them. Task recovery does not depend on a successful Dream run.

By default Dream runs after 180 seconds of foreground inactivity, processing at most eight inputs and 16,000 characters per batch, with up to 24 model iterations. Interval mode is also available. Each batch has one visibility scope. Derived records inherit their evidence scope and version; project/session batches cannot edit shared profiles. Dream's file tools cannot read configuration or modify original evidence logs.

Leases prevent simultaneous processing, and long calls renew them. New foreground input interrupts automatic idle Dream, releases the lease and does not consume a failure attempt. Knowledge already saved remains; a later run searches for duplicates. Inputs changed during processing stay queued.

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

Legacy `index.sqlite3` migrates into the split stores under a lock; the old database is retained as `index.legacy.sqlite3`. Catalog, search and queue writes use attached SQLite databases and rollback-journal transactions. Each database has a 512 KiB page-cache setting; splitting stores does not load the corpus into memory.

Back up the entire Home while the service is stopped. Catalog and Dream databases contain authoritative state. Search and vectors are derived indexes; after losing the text index, perform a full rebuild in Settings. Vector chunks regenerate on explicit searches. Markdown alone cannot restore scopes, revisions, links or processing state. Evidence and revisions do not expire automatically, so disk usage grows with history.

## Optional CPU embeddings

Install the `memory-embedding` extra, then configure a local BGE-small INT8 ONNX model and matching `tokenizer.json` in Settings → Memory retrieval. Model files are not downloaded automatically. The worker uses normalized CLS vectors and one CPU thread. ONNX Runtime, NumPy and tokenizers stay out of the default gateway process.

Explicit semantic/hybrid retrieval launches a disposable worker. Vectors are cached on disk by model and content fingerprints; similarity scoring streams stored vectors. Only distilled knowledge and shared profiles are embedded. Long records use 224-token windows with a 192-token stride and retain character offsets. Each search generates at most 32 chunks, with at most eight per worker response. Remaining progress is persisted for the next explicit search. A record ranks by its best matching chunk. Hybrid retrieval uses reciprocal-rank fusion.

Missing dependencies, invalid models, a busy worker, timeout or an RSS-limit violation return BM25 results with a reason. The default worker budget is 200 MiB, checked through process RSS sampling. Embeddings remain disabled by default. The deployment target is at most 400 MB for Cirno and its children combined; the worker budget alone does not enforce a total-service limit. Measure the complete process tree on the target server and use a container or host memory limit when needed. Historical local benchmark results are archived under `references/`, not treated as a current performance guarantee.
