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
parameters. A caller cannot override the bound action. Dream alone receives
`memory.confirm`; ordinary turns cannot acknowledge Dream's evidence queue.

Only the Router conversation receives `user.message`. Ordinary conversations
reply through normal assistant output. The same selection is used for turns,
compaction and context accounting. PTC wraps that selection rather than
reintroducing tools excluded from the conversation.

The Router receives all ordinary execution tools plus coordination controls and
`user.message`. It can run brief resource checks directly and delegates medium
and large tasks. Paper reading, literature reviews, development and experiments
start in a Worker; brief CPU/GPU checks can run directly in the Router.
Access and approval policies apply equally to both roles.

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
