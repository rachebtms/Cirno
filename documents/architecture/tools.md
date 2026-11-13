# Tool namespaces

Cirno keeps one implementation per capability. The shared catalog in
`sources/cirno-core/src/cirno_core/agent/tools/names.json` defines model-facing operation names;
Python execution, PTC, activity rendering and persisted calls use the same map.

| Namespace | Operations |
| --- | --- |
| `files` | Read, write, edit, list, find, search, ripgrep, patch |
| `shell` | Execute, continue a process, list running processes |
| `web` | Search and fetch |
| `memory` | Search, read, original evidence, revisions, tags, save, update, link, checkpoint, status |
| `goals` | Create, update, inspect; Router-only control of other conversations' Goals |
| `conversations` | Create, title, search, read, send, report; Router-only stop and continue |
| `user` | Asynchronous questions; Router-only visible messages |
| `agents` | Create, check, send, cancel subtasks |
| `automations` | Add, list, update, enable, disable, remove, history |
| `nodes` | SSH execution, file transfer and durable job control |
| `skills` | Validate and read retained versions |
| `runtime` | Inspect or change allowed runtime settings |
| `apps` | Run installed CLI Apps |
| `ptc` | Execute a program using the available tools |

Native function-calling APIs restrict characters in tool names, so native calls
use `memory__search`. The PTC SDK uses `await tools.memory.search(query="...")`.
Activity labels display the dotted logical name or a localized description.
MCP calls use provider-safe names. Names requiring character normalization receive a stable hash suffix so distinct upstream names remain distinct. Very long names are capped at 64 characters. MCP allowlists accept the original upstream tool name or the exact exposed name; repeated exposed names fail discovery before registration.

Action-based implementations expose separate operations with their action
bound by the registry. Memory and Node schemas contain only the relevant
parameters. A caller cannot override the bound action. Context consolidation acknowledges only supplied, explicitly reviewed and unchanged pending input revisions. Ordinary turns do not receive `memory.confirm`.

Only the Router conversation receives `user.message`. Ordinary conversations
reply through normal assistant output. The same selection is used for turns,
compaction and context accounting. PTC wraps that selection rather than
reintroducing tools excluded from the conversation.

Visible replies use short, complete `user.message` calls. Invalid JSON is rejected
without delivery; the tool error asks for a complete replacement argument object,
not a continuation of the broken string. Earlier successful messages remain
delivered and must not be replayed. The framework does not silently repair live
arguments, trim repeated text or impose a separate reply-length cap. Chat stream
slots cannot combine different call IDs into one argument string; an inconsistent
gateway stream returns an error instead.

The Router receives ordinary execution tools plus coordination controls and
`user.message`, but excludes transient `subagent` execution. Worker catalogs
exclude Router-only messaging, cross-conversation controls and Project management.
Both native and nested PTC execution check the same role policy. Within each run,
the Router may make at most nine ordinary calls and spend ten cumulative seconds
executing them; overlapping calls count elapsed time once. Model waiting is not
charged. PTC programs share the same cumulative wall-time allowance across model
rounds, including Python computation; nested ordinary calls count once. In PTC
mode, coordination tools, `runtime.check` and `memory.checkpoint` are also exposed
directly, so supervision does not require another execution program. Replies,
coordination, runtime snapshot inspection and task-checkpoint saves do not consume
ordinary calls or their direct execution time and remain available after exhaustion.
The PTC wrapper itself still consumes wall time; use the direct supervision tools
after exhaustion. Runtime changes and other memory operations remain budgeted.
Read-only task execution such as file reading, web search and remote checks also
remains budgeted; being read-only does not make an investigation a small task.
The budget starts fresh for each run, not each model round or each PTC program,
and is not a conversation-lifetime quota. Limits are returned as explicit tool-policy
decisions with `router_budget_exhausted` or `router_execution_timeout`, rather than
an implementation `ValueError`. A timed-out operation may
have completed effects; its error instructs the model to inspect before retrying.

The Router prompt requires paper analysis, literature reviews, development,
debugging, experiments and uncertain-size tasks to start in a durable Worker
before substantive work. Brief CPU/GPU checks can qualify as direct work. Task
classification is a model responsibility; the runtime enforces the execution
limit and tool permissions. Workers do not inherit the Router's small-task budget.
Access and approval policies apply equally to both roles. Unavailable or already
exhausted work is rejected before asking the owner to approve it; admission is
checked again after approval without charging native approval waiting time.

`runtime.check` reads the allowlisted runtime snapshot, not arbitrary configuration
paths such as `agents.defaults.heartbeat`. Omit `key` to discover its available
runtime fields. It retains its access and secret-field restrictions even when
ordinary execution has exhausted its budget.

The Python file-search backend shares directory scanning, filters and paging
between path discovery and content search. Unreadable directories and failed
file reads return errors. Content search checks symlink targets against the
workspace policy and skips non-regular files such as named pipes; it does not
wait for a pipe writer. Document parse failures identify the failed document.
Regex evaluation shares the scan deadline and releases the Python interpreter
lock, so a pathological pattern cannot stall other conversations indefinitely.

Shell execution returns a process-session ID when its initial observation ends
before the command finishes. `shell.session` reads output, writes or closes
stdin, waits for text or exit, and terminates the process. Observation waits do
not extend the command's runtime budget. Process sessions belong to their
execution runtime and conversation; another runtime cannot read or close them.
Their output is retained in memory until consumed or expired, and service
shutdown terminates them. Execution diagnostics retain the starting request's
content-logging policy when another caller performs cleanup.

The Router manages explicit Projects with `projects.list`, `projects.get`,
`projects.create`, `projects.update`, `projects.assign` and `projects.delete`.
Assignment accepts a conversation handle and a Project ID, or null to remove
membership. It does not change the working directory. Deleting a Project keeps
its conversations and files. Web UI actions use the same project service and
broadcast catalog updates to connected clients.

`conversations.report` records the worker's latest structured state, factual
summary, artifact paths and optional `human_action` question. Progress and waiting
are passive records, available to the coordinator on its next turn. Results,
failures, blockers and new questions enter its durable inbox. Omit `human_action`
to retain a question; an empty string clears it. Reporting `ready` never completes
a Goal; `goals.update(action="complete")` remains explicit. Delegated Goal
completion uses the same report path and reuses a previously queued ready report.

Conversation sends mean **queued**, not read or finished. Stable message IDs and
SQLite inbox receipts prevent replay of already-consumed coordination inputs,
including after restart; pending inputs remain recoverable. Receipts live with
session runtime state, separate from memory databases. A consumed receipt means
the input was committed into the turn's context, not that the task succeeded.
They are scoped to the destination session generation and deleted with the
conversation. A reused ID with a different payload is rejected.

Delegation keeps the source conversation, turn/message identifiers and a bounded
verbatim original-request excerpt. Workers read the source when it is incomplete;
neither routing notes nor reports grant new user authorization.

Python implementation identifiers connect tool classes to the shared namespace
catalog. They are internal dispatch details, not a second advertised tool API.
When adding or renaming an operation, update the shared catalog and its schema,
then check native execution, PTC dispatch and activity rendering together.

## File operations

File reads scan text in chunks, retaining only the selected page and its snapshot
hash. A page contains at most 128,000 characters; text files may be up to 100 MiB
and inline images up to 6 MiB. Long individual lines are explicitly marked when
clipped. PDF and Office documents use their page or extracted-line readers.

Text editing and patching retain bounded originals for validation and diffs:
2 MiB per file and 8 MiB across a patch's original and updated snapshots. Use
targeted shell commands for larger data files. Match preparation runs outside the
service event loop. Stop settles that worker before returning and cannot commit
its abandoned edit. If another operation changed a prepared file, the edit fails
and asks the model to read it again.

File writes and edits share atomic replacement, preserving existing permissions.
Patches validate the whole batch before writing. If a later commit fails, already
attempted files are restored; any restoration failure names the affected files.

Credential tools operate only on Agent-visible records. Agent writes mark a record visible; owner writes default to private. SSH enrollment belongs to the owner, and Node tools require both enrollment and visibility. Settings, credential tools, direct Node commands and terminals share the credential service instead of storing separate authentication copies.

The `files.view_image` operation uses the shared `files.read` implementation for path authorization, bounded reads and visual content blocks. Model configurations record image/video input declarations separately from request API routing. Setup probes use the chosen endpoint with no fallback chain, so another model cannot produce a misleading capability result.
