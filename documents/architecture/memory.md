# Disk-first memory

Cirno defaults to files and SQLite FTS5/BM25. It does not load an embedding model, run a vector database or search memory before every reply. Profiles, evidence, memory and Skills live in Home; workspaces contain task artifacts. The independent `cirno-memory` package owns retrieval and evidence stores; core coordinates context consolidation.

## Recall and editing

Settings provides Memory library, Context consolidation and Memory retrieval. Settings → Personality edits Router and Worker personalities, user preferences and workflow instructions. Settings → Agent heartbeat edits heartbeat instructions. The memory library and Agent tools share `cirno_memory.search`: BM25 is the default, with optional semantic and hybrid modes. Filters include layer, scope, tags and dates. The interface reports the actual engine, fallback reason and unfinished vector-index coverage.

An empty query browses records without launching an embedding worker. Evidence, task state and searches including historical records use BM25 because optional vectors do not cover all those records. Open a result to inspect its body, versions and original evidence. Search pagination retains the submitted filters while the next query is being edited. Evidence pages identify the resolved source record and revision; continuation and retry retain that revision, including when a historical finding points to a separate captured source. Index rebuilding is incremental and can be stopped and resumed. Consolidation learning failures expose their reasons; generated learning can be saved again without another model request.

Use `memory.search`, then `memory.read`. Default recall returns knowledge, task checkpoints and profiles. Use `purpose="evidence"` for events and original messages, or `purpose="all"` for both. `memory.tags` discovers visible tag names and counts. `expand_links` adds bounded one-hop relationships: three by default, at most ten across the results. There is no reranker.

Exact values, dates, quotations and prior decisions should be checked against original evidence. A stored URL or Node path establishes a reference, not that Cirno accessed or independently verified it.

## Layers and scopes

| Layer | Purpose | Recovery |
| --- | --- | --- |
| `profile` | Preferences and a brief shared overview | Bounded `memory/MEMORY.md` injection; other profiles follow their normal loading rules |
| `task` | Objective, results, blockers, next steps and artifact references | Checkpoint injected by conversation identity, separately from learned knowledge |
| `event` | Saved observations and historical increments | On-demand retrieval and the next owning-scope consolidation |
| `knowledge` | Grounded facts, hypotheses, decisions and lessons | On-demand retrieval |
| `source` | Immutable original messages captured before consolidation | Paged reads by source ID, line and character offset |

Records have `user`, `project` or `session` scope. Structured retrieval, reads, evidence, revisions, links, tags, statistics and semantic results enforce the same visibility rules. Project identity uses a project ID rather than inferring identity from a working directory. A record's originating session is provenance: moving that conversation out of a Project does not retain access to the Project's memory. Session-scoped records remain accessible to their own conversation. Full Access file and shell tools follow their own access rules; memory scopes are not operating-system isolation.

Large files, web artifacts and Node job output remain at their original locations. Memory stores their references instead of copying entire workspaces.

Immutable memory bodies are checked against their recorded content hash on reads, including historical revisions and semantic indexing/snippet extraction. A mismatch is reported rather than returning altered content. Scope identity uses the user scope, Project ID or conversation key; Project records from different Workers in the same Project can be revised or linked without changing their originating-session metadata. `WORKER.md` is indexed alongside the shared profiles, and removing a profile removes its active indexed record. Original evidence reads are paged with line and character cursors and a 16,000-character total page limit, including memory-body pointers and very long individual lines. Building the source index also reads bounded fragments, retaining line numbers and overlaps without loading an entire JSONL line.

## Context consolidation

Active context pressure, `/consolidate` and idle expiry use one awaited pipeline: capture immutable originals, make one model request for a task checkpoint **and** durable learning, validate and persist learning, then commit the replacement checkpoint and resume the task. `/compact` and `/dream` are legacy aliases for the same session-queued command. There is no separate idle/interval Dream model task. Existing Worker concurrency is unchanged; consolidation does not launch another model run alongside its owner. Provider retries or recovery from an incorrectly returned tool call remain sequential.

The checkpoint retains Task, State, Next and Retained facts. Explicit milestone checkpoints are not overwritten by automatic summaries. Checkpoint slots follow conversation/Project identity; switching Project membership selects that Project's checkpoint, and switching back restores it. Originals remain available even if generation or persistence fails. When a source batch cannot fit or the provider fails, the existing bounded evidence checkpoint preserves recovery; it does not claim that learning completed.

The same response may append structured memory and document updates. No useful learning means no update. Source indices and exact quotes are checked against archived messages; supplied pending inputs can be cited by memory ID. Findings inherit their evidence scope and cite immutable evidence. Corrections retain old evidence through supersedes links. Exact duplicate findings reuse a deterministic ID. Only explicitly reviewed, unchanged pending revisions are acknowledged; omitted or changed inputs stay queued for a later consolidation in that scope. No other conversation's private queue is included. A personal Router may also review explicitly shared user inputs; those inputs can produce shared knowledge only from shared evidence, never by mixing in private task messages.

Self-improvement is part of this pass: verified failures/fixes and user corrections can update a completely supplied existing Skill. New autonomous Skills require repeatable steps and a supplied lesson from another independent task. Shared Skills must omit private task details and credentials. Skill identity/runtime metadata and retained script syntax are checked and readable versions are retained; these checks do not prove behavior. Substantial implementation or additional behavioral testing remains a scoped lesson for later authorized work, not another hidden model run. Only SKILL.md can be edited by this pass.

Only a non-Project Router batch may update supplied SOUL.md, USER.md and memory/MEMORY.md profiles, and changes require explicit user-message evidence. Tool output, internal runtime context and Worker/Project reports cannot redefine the user or Router identity. Full document snapshots and the shared foreground file transaction prevent overwriting an owner or Worker edit made during generation.

The default generation budget is 8,192 tokens shared by checkpoint and learning, low reasoning effort, at most eight memory/document updates and 16,000 characters of additional reference material. The selected conversation model is reused. Optional references are bounded by remaining input space and appended at the request tail. Disabling learning preserves checkpoint generation and previously saved memory. Settings → Context consolidation exposes these controls together with active/idle thresholds and retention.

Learning plans and outcomes persist under `memory/consolidations/<source-id>.json`; a failed save leaves the plan and error for inspection. Memory library's Retry saving consolidation results replays generated plans without an LLM call; conflicting files or revisions still require reconciliation. Each batch is retried independently, with partial failures reported and the status refreshed. Completed receipt files repair a stale status index without applying their edits again. Failed batches rotate behind older pending retries so one invalid result cannot block unrelated work. Pending observations and older unprocessed inputs are included only within the owning scope and available reference budget. Existing Dream receipts/history remain readable for audit, and old schedule entries are removed on startup. The obsolete Home prompts/dream.md tool-agent override is retained on disk but no longer executed.

Journal append and retention share a file lock. Invalid records stop the affected operation with a file location. Restore or correct that file before retrying.

### Cache behavior

The consolidation instruction and bounded references are appended to the accepted transcript without modifying its system prefix, prior messages or tool definitions. A response containing memory updates is split before replay: only its checkpoint becomes task context. No maintenance prompt or unexecuted tool call is injected as a user request.

Task checkpoints and current MEMORY.md reach later fresh input as persisted snapshots. Skill and tool ordering remains deterministic. Changing profiles, Skills or the checkpoint can change the next constructed context at that boundary; consolidation cannot preserve the cache of the history it replaces. It does not rewrite already accepted requests in other running tasks. Cache metrics include cached input; missing provider metrics are unknown rather than misses, and hit rates remain provider-dependent.

The default `releaseArchivedRuntime` behavior releases consolidated runtime prefixes only after originals are saved. Display history remains in conversation SQLite storage. Old prefixes are streamed rather than loaded wholesale; the recent runtime-snapshot cache is bounded to eight conversations. Disabling release retains full runtime prefixes and can increase memory use during long work.

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
| `memory/dream.sqlite3` | Historical receipts and pending input revisions (retained storage name) |
| `memory/vectors.sqlite3` | Optional vector chunks and incremental indexing state |
| `memory/history.jsonl` | Consolidation journal |
| `memory/consolidations/<source-id>.json` | Generated learning plans, snapshots and save outcomes |
| `skills/` and `skills-history/` | Home Skills and retained versions |

Catalog, search and queue writes use attached SQLite databases and rollback-journal transactions. Each database has a 512 KiB page-cache setting; splitting stores does not load the corpus into memory.

Back up the entire instance root while the service is stopped; Agent Home is its `home/` subdirectory. Catalog and pending-input databases contain authoritative state. Search and vectors are derived indexes; after losing the text index, perform a full rebuild in Settings. Vector chunks regenerate on explicit searches. Markdown alone cannot restore scopes, revisions, links or processing state. Evidence and revisions do not expire automatically, so disk usage grows with history.

Checkpoint writes and evidence capture run outside the server event loop, including provider-failure and exhausted-budget fallbacks. Runtime history is released only after its checkpoint is committed. Learning persistence settles before cancellation releases file ownership; no second model task is scheduled.

## Optional embeddings

For the local engine, install the `memory-embedding` extra, then configure a local BGE-small INT8 ONNX model and matching `tokenizer.json` in Settings → Memory retrieval. Model files are not downloaded automatically. The worker uses normalized CLS vectors and one CPU thread. ONNX Runtime, NumPy and tokenizers stay out of the default server process.

Explicit semantic/hybrid retrieval launches a disposable worker. Vectors are cached on disk by model and content fingerprints; similarity scoring streams stored vectors. Only distilled knowledge and shared profiles are embedded. Long records use 224-token windows with a 192-token stride and retain character offsets. Each search generates at most 32 chunks, with at most eight per worker response. Remaining progress is persisted for the next explicit search. A record ranks by its best matching chunk. Hybrid retrieval uses reciprocal-rank fusion.

Missing dependencies, invalid models, a busy worker, timeout or an RSS-limit violation return BM25 results with a reason. The default worker budget is 200 MiB, checked through process RSS sampling. Settings accepts larger budgets (for example 512 or 1024 MiB), with no fixed 200 MiB ceiling; the budget includes model-loading overhead. Embeddings remain disabled by default. The worker budget alone does not enforce a total-service limit. Deployments can set their own resource limits. Historical local benchmark results are archived under `references/`, not treated as a current performance guarantee.

The API engine uses an OpenAI-compatible embeddings endpoint instead of a local model. It shares the same on-disk vector index, scope filtering and hybrid search. API requests send the query and selected knowledge chunks to the configured service; no local inference libraries are loaded. The endpoint, model and chunk size identify the index. API failures return BM25 results with a visible reason. See [Memory retrieval](../memory-retrieval.md) for configuration and privacy details.

The Launcher Memory tab reuses this retrieval pipeline and the existing evidence/version inspector. Its bounded relation view uses stored memory links plus shared tags, with no embedding projection or inferred links. See [Memory cloud](../memory-retrieval.md#memory-cloud) for paging, visibility and rendering lifetime.

Consolidation receipts also retain successfully applied learning when a later checkpoint/journal commit is interrupted. Retrying the same immutable archive reuses its generated output, skips completed learning effects and identifies journal entries by archive ID, without another model call. The catalog retains checkpoint identities across short-term journal retention, so retrying a retired entry still returns its original cursor. Journal retention can retire old entries only after their exact events are mirrored in the catalog; this path no longer relies on the retired idle-Dream cursor, and original evidence remains readable through immutable memory records.
