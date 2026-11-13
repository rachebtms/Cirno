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

Active context pressure, `/consolidate` and idle expiry share one foreground operation: retain immutable originals, generate a task checkpoint and optional learning in one response, save each outcome independently, then resume. Learning parsing, source checks or learning-file writes cannot veto a usable task checkpoint. Checkpoint persistence and input-budget checks remain required before replacing active context. `/compact` and `/dream` remain aliases. There is no parallel Dream task, extra background extraction run or automatic second request merely because learning failed.
The checkpoint retains Task, State, Next and Retained facts. Explicit milestone checkpoints are not overwritten by automatic summaries. Checkpoint slots follow conversation/Project identity; switching Project membership selects that Project's checkpoint, and switching back restores it. Originals remain available even if generation or persistence fails. When a source batch cannot fit or the provider fails, the existing bounded evidence checkpoint preserves recovery; it does not claim that learning completed.

The response may append structured memory and document updates. Ordinary findings do not require the model to copy quotes or select evidence: the framework links them to the immutable original batch automatically. Batch provenance identifies where a finding came from; it does not prove that the finding is true. Scope boundaries, source revisions, correction targets and independent-task requirements remain enforced. No useful learning means no update.

Document edits and references to a specific pending input use framework-provided `source_id` handles. Only offered handles are accepted. The framework binds them to original excerpts; model-written quotes accompanying a handle are not used as evidence. Archive excerpts consume at most one eighth of the existing additional-reference budget, preserving the initial user objective and recent text. Full writable documents and pending memory revisions share the remaining budget. Legacy archive quotations attached to ordinary batch findings are not used as provenance or save gates, even if the model supplies them despite the prompt. References to pending memory inputs retain exact-quote, revision and visibility checks; document edits retain their source and user-authorization checks. Mixed input/archive references remain intact so private evidence cannot be dropped to promote a finding into shared memory. Image metadata and tool-call arguments are not offered as textual evidence. Exact duplicate findings reuse deterministic IDs; unreviewed or changed pending inputs stay queued. Private task inputs cannot be combined into shared knowledge.
Self-improvement is part of this pass: verified failures/fixes and user corrections can update a completely supplied existing Skill. New autonomous Skills require repeatable steps and a supplied lesson from another independent task. Shared Skills must omit private task details and credentials. Skill identity/runtime metadata and retained script syntax are checked and readable versions are retained; these checks do not prove behavior. Substantial implementation or additional behavioral testing remains a scoped lesson for later authorized work, not another hidden model run. Only SKILL.md can be edited by this pass.

Only a non-Project Router batch may update supplied SOUL.md, USER.md and memory/MEMORY.md profiles, and changes require explicit user-message evidence. Tool output, internal runtime context and Worker/Project reports cannot redefine the user or Router identity. Full document snapshots and the shared foreground file transaction prevent overwriting an owner or Worker edit made during generation.

The default generation budget is 8,192 tokens shared by checkpoint and learning, low reasoning effort, at most eight memory/document updates and 16,000 characters of additional reference material. The selected conversation model is reused. Optional references are bounded by remaining input space and appended at the request tail. Disabling learning preserves checkpoint generation and previously saved memory. Settings → Context consolidation exposes these controls together with active/idle thresholds and retention.

Learning plans, source bindings, raw invalid output, errors and completed item IDs persist under `memory/consolidations/<source-id>.json`. A task checkpoint can succeed while learning remains incomplete. The conversation notice and Memory status list completed updates separately from updates needing retry, including document paths and memory labels. An incomplete item may already have partial writes; the UI says so instead of claiming a rollback. Original source IDs remain visible. A first consolidation after upgrading can reuse an older batch's retained checkpoint and show that batch's unresolved learning error; this does not imply another extraction request was made. A successful checkpoint is never reported as a total consolidation failure because learning failed.

Memory's **Retry saving consolidation results** replays generated plans without an LLM call. To re-extract an invalid or missing result, run `/consolidate retry [source-id]` in its original conversation. Each invocation retries one batch within the owning session queue and current Project scope. It first tries the saved plan; only invalid output with no completed effects is regenerated. This explicit model call returns learning updates only: it does not rewrite the saved task checkpoint, append another checkpoint journal entry or advance archive boundaries. Partial writes and file/revision conflicts require replay or reconciliation rather than blind regeneration. Completed effects remain idempotent. Cancelling recovery waits for accepted file writes to settle.

The command emits the same persisted consolidation lifecycle report as manual checkpointing, rather than an assistant reply. Reports distinguish replayed writes from regenerated learning, show confirmed saved items, earlier acknowledgements, remaining items and the original source, and record whether a model invocation was attempted. A completed batch with no updates is explicitly reported as no updates; original proposals are shown separately from saved results. No matching failed batch is reported as no pending work, not as a saved batch.

Settings → Context consolidation → **Consolidation generation retries** controls additional serial generation attempts (`max_retries`, default 1, range 0–10). Zero allows only the initial attempt. This covers generation failure, unusable output and tool-call recovery; explicit learning regeneration uses the same limit. A usable checkpoint with failed learning is not regenerated automatically. Provider-level network retry settings are separate. Cancellation is not retried. Invalid model output and storage errors remain visible; no retry adds concurrency.

Existing Dream receipts and histories remain readable for audit. Old schedule entries are removed on startup, and the obsolete Home `prompts/dream.md` override is no longer executed.
Journal append and retention share a file lock. Invalid records stop the affected operation with a file location. Restore or correct that file before retrying.

### Cache behavior

The consolidation request reuses the accepted instruction/history prefix, model and tool definitions, appending the request at the tail. After consolidation, the checkpoint is a clearly delimited history message after the instruction prefix, rather than text embedded in the system prompt. Repeated compactions retain the captured system/developer messages byte-for-byte and do not rebuild them from newly edited profile or Skill files during the same run. There is no timestamp inserted into the stable prefix. Real configuration/profile changes on a later turn can legitimately change that prefix.

Replacing old history inherently changes the summarized region; it cannot retain that region's exact-prefix cache hit. The goal is to preserve the stable instruction prefix and establish a new reusable checkpoint/history prefix. Code tests check request layout and equality, not a promised billing rate. Actual hits depend on the provider or proxy and must be checked in returned usage, such as DeepSeek's `prompt_cache_hit_tokens` and `prompt_cache_miss_tokens`.

Design references: [Hermes compression and caching](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/developer-guide/context-compression-and-caching.md) separates context engines and memory hooks and preserves stable prompt prefixes; [DeepSeek caching](https://api-docs.deepseek.com/guides/kv_cache/) describes provider-side prefix matching. Cirno keeps failures visible rather than copying silent error suppression from optional hooks.

The default `releaseArchivedRuntime` behavior releases consolidated runtime prefixes only after originals are saved. Display history remains in conversation SQLite storage. Old prefixes are streamed rather than loaded wholesale; the recent runtime-snapshot cache is bounded to eight conversations. Disabling release retains full runtime prefixes and can increase memory use during long work.

## Revisions and maintenance

Updates require `expected_revision` from the latest read or successful write. Each conversation has one task checkpoint per Project scope: its first `memory.checkpoint` may omit the version, but replacing it requires the previous checkpoint's returned `revision` as `expected_revision`. Historical bodies are retained. Relations include `supports`, `conflicts`, `related`, `derived_from` and `supersedes`. Superseded findings leave default search results but remain readable.

A rejected write distinguishes a missing version (`memory_revision_required`) from an outdated version (`memory_revision_conflict`). Tool results explicitly report `write_applied: false` and include the authorized current record's ID, revision, source and content, captured before any mutation. The Agent compares that snapshot with its proposal and retries the appropriate checkpoint/update using the snapshot revision; no extra read is needed unless the result was truncated. Another intervening edit is still rejected. Conflict handling never automatically overwrites, creates a duplicate, or schedules another model request. Inaccessible records return the existing scope error without disclosing their state. Snapshots live in the ordinary tool result, leaving the system prefix unchanged.

Write failures remain tool execution errors in native and PTC paths. A PTC program can catch a nested `ToolError` and finish successfully while the nested write remains failed; the program's completion is not a persistence receipt. Agent instructions require a non-error write result with the saved ID and revision before claiming a save. The `current` snapshot in a conflict describes the existing record, not a saved version of the rejected proposal.

Time filters default to event occurrence (`observed_at`); unknown dates are not guessed. Use `time_field="created_at"` or `"updated_at"` for storage/edit times. Derived knowledge inherits its primary evidence's occurrence time unless explicitly supplied. Dates and naive times use the configured timezone, overridable through `time_zone`; a date-only upper bound includes that entire day.

`memory/entries/*.md` contains body text only. Conversation/Project scope, `session_key`, revisions and source references belong to `catalog.sqlite3`; searching Markdown bodies for a session key is not an index-completeness check. Use scoped memory search/read to inspect catalog records and validate their stored bodies.

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
