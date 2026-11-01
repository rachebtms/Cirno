# Tool namespaces

Cirno keeps one implementation per capability. The shared catalog in
`sources/cirno-core/agent/tools/names.json` defines model-facing operation names;
Python execution, PTC, activity rendering and persisted calls use the same map.

| Namespace | Operations |
| --- | --- |
| `files` | Read, write, edit, list, find, search, ripgrep, patch |
| `shell` | Execute, continue a process, list running processes |
| `web` | Search and fetch |
| `memory` | Search, read, original evidence, revisions, tags, save, update, link, checkpoint, status |
| `goals` | Create, update, inspect |
| `conversations` | Create, title, search, read, send, report |
| `user` | Asynchronous questions; Cirno-only visible messages |
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
MCP plugin names retain their existing identity and allowlist behavior.

Action-based implementations expose separate operations with their action
bound by the registry. Memory and Node schemas contain only the relevant
parameters. A caller cannot override the bound action. Dream alone receives
`memory.confirm`; ordinary turns cannot acknowledge Dream's evidence queue.

Only the Cirno conversation receives `user.message`. Ordinary conversations
reply through normal assistant output. The same selection is used for turns,
compaction and context accounting. PTC wraps that selection rather than
reintroducing tools excluded from the conversation.

Cirno receives coordination, memory, reference-reading and lifecycle tools.
Shell commands, file mutation, Nodes, CLI Apps, worker subagents and MCP execution
are delegated to ordinary execution conversations. Ordinary conversations retain
their execution tools and streamed replies. PTC wraps the same role selection.

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
