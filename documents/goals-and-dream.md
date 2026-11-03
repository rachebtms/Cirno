# Goals, coordination and Skills

A Goal is a durable objective belonging to one conversation. Use `/goal` to request sustained work. The executing model records the objective and completion criteria; a normal reply does not complete it. Completion requires explicit `goals.update(action="complete")` after verification.

Logical names below use dots. Native calls use double underscores, such as `goals__create`; PTC uses `await tools.goals.create(...)`. See [tool namespaces](architecture/tools.md).

| Operation | Purpose |
| --- | --- |
| `goals.create` | Create an objective, optionally overriding the default continuation limit |
| `goals.get` | Read the objective, state and continuation count |
| `goals.update` | `continue`, `wait`, `complete`, `block`, `pause`, `resume`, `stop`, `cancel`, `replace`, `update` or `delete` |

The instance continuation limit is configured under Settings → Goals & execution. Zero means unlimited and is the default. `/goal` does not require a limit. Counts persist across waiting, pauses and service restarts. Creating or replacing a Goal starts a new count. Reaching a finite limit pauses it and preserves progress.

A running Goal continues between execution segments until it completes, waits, blocks or is paused/stopped. `wait` saves progress and a `wake_after_seconds` deadline. Due work resumes through its conversation queue; incoming conversation input also wakes a waiting Goal. Deadlines require the server to run; overdue work is handled after restart. Interrupted tools follow the existing recovery process rather than being blindly repeated.

Pause prevents automatic continuation. The conversation Stop control cancels active execution and stops its Goal until resumed. The model's `stop` operation stops continuation without interrupting a tool already executing. Creation, replacement, limit changes and user control operations require fresh user input. Automatic continuation can save progress, wait, block or complete the existing objective.

## Coordination

Cirno is a persistent coordination conversation with a restricted tool selection. It discusses priorities, delegates execution and organizes incoming reports. Ordinary conversations execute commands, modify files and use Nodes, CLI Apps, MCP and worker subagents. They retain streamed assistant replies. Cirno's internal execution history is collapsed by default; it sends visible messages and files through `user.message`. Ordinary conversations do not receive this operation.

Both roles can use `conversations.create`, `conversations.send`, `conversations.search` and `conversations.read`. The returned `@handle` is a stable conversation address. An ordinary conversation can send a report to Cirno with `conversations.send(to="Cirno", ...)`, or use `conversations.report` for structured state, summary, artifacts and a pending user question. Routine progress is passive; results, blockers, failures and new questions wake the coordinator. A `ready` report does not complete a Goal.

Coordination messages are journaled before delivery and deduplicated by stable IDs and destination-generation receipts. Queued does not mean finished. Delegation preserves source references and the original request; worker reports do not grant new authorization. Each conversation retains its own history, Goal, queue and cancellation scope. See [inbox and report delivery](notification-inbox.md).

Only Cirno receives `conversations.control` and `goals.control`. It can stop/continue other saved Web conversations and inspect or change their Goals while preserving progress and continuation counts. `goals.control` has no completion action: the executing worker must verify and finish its own Goal. Each control is recorded with the `@cirno` source.

`conversations.control(action="get", to="@handle")` reads a worker's workspace, PTC mode and selected model preset, including the available preset names. `action="configure"` changes any combination of `workspace`, `ptc_mode` and `model_preset` on an idle conversation. Stop active work first, configure it, then continue when ready. Workspace must be an existing absolute server directory; `~/` is accepted. Model names use the configured preset catalog, and `default` restores the instance's active model. Changes are persisted together and broadcast to the Web UI. Configuration does not restart work, move files, clear history, alter the Goal or Project membership, or switch its Default/AI review/Full Access mode. Ordinary conversations do not receive this supervisory capability.

`conversations.set_title` lets the model set a concise title in the user's language. Automatic title generation is also available; manual titles and Cirno's identity are preserved.

## Delegated execution results and failures

Independent conversations created through delegation automatically report terminal execution results to their delegating coordinator. The runtime reports LLM/API failures, empty final answers and unexpected execution-stage exceptions even if the model cannot call `conversations.report`. Reports include the returned output or a bounded excerpt, the source conversation, stop reason, public failure category, selected model and failing stage when available. Read the saved source conversation for complete output and execution details. An execution result does not itself complete a Goal.

A detailed explicit report from the same execution is reused. Segments that will automatically continue and ordinary user conversations do not generate extra result reports. API failures block unfinished Goals instead of silently marking them complete. User cancellation and pauses are respected.

A retry episode and its recovery also wake the coordinator, without blocking the running Goal. Repeated attempts in the same episode are coalesced. If delivery is unavailable, pending retry/recovery updates for the same execution retain only the latest health state; result and failure reports are preserved separately. Cirno must check the latest state before acting on a delayed retry notice. These coordination-only retry updates do not create ordinary reply notifications in Inbox.

Reports enter the existing durable conversation inbox and pending report queue. Failed delivery is retried without rerunning the worker; acknowledged reports are not delivered twice. Pending reports survive restart and can reach Cirno when its provider is available again. A generic Goal status notice does not overwrite a more detailed failure report. Private subagent tasks continue to report outcomes and errors to their owning conversation through the existing task-result channel.

Cirno's recovery guidance asks it to inspect the worker's saved state before selecting another configured model or continuing authorized work. Unclear external side effects and missing credentials require owner attention; recovery does not authorize replaying commands or reversing an owner Stop.

## Heartbeat

When enabled under Settings → Agent heartbeat, the protected heartbeat job queues active `Home/HEARTBEAT.md` instructions into Cirno. Pending checks survive restart and use the normal conversation queue. Cirno is instructed to notify only when something needs attention. Use Automations for an explicit time or interval; heartbeat is for flexible background checks.

## Memory and learned Skills

Memory, profiles and Skills belong to Home rather than workspaces. See [memory architecture](architecture/memory.md) for bounded profile injection, task checkpoints, evidence, scopes and Dream's per-input confirmations. Settings → Memory retrieval manages recall, and Dream consolidation manages background consolidation; Settings → Personality edits shared profile files.

Dream can extract or improve a reusable workflow under `Home/skills/<name>/`. Its restricted file tools cannot modify application code. Home Skills are checked for identity metadata and Python/shell syntax before being offered as available. Syntax validation does not execute scripts or prove behavior.

File-tool edits preserve versions under `Home/skills-history/<name>/<revision>/`; UI deletion also preserves the current version. Unchanged content reuses its revision. `skills.validate`, `skills.history` and Settings → Skills expose validation and history paths. The model can read old files and deliberately edit the current Skill. There is no automatic rollback.

## Context compaction during active work

Settings → Context compaction separates the active-work trigger from idle compaction. `agents.defaults.activeCompactPercent` is the percentage of the selected model's context window checked before every request, including tool rounds. The effective budget is the smaller of that percentage and the window minus reserved output and the safety buffer. The default, 100, preserves the maximum safe input budget; it never removes the output reserve. Lower values compact earlier. The active threshold does not change the idle timer or idle retention percentage.

`MEMORY.md` remains automatically injected, now as a persisted snapshot on fresh input when it changes. Dream updates no longer rewrite the system prefix or historical requests. Coordination records also stay on fresh inputs. Personality/tool/model changes and actual context compaction can still change request prefixes. Cache hit rates depend on new input volume and provider behavior; they are not guaranteed to exceed a fixed percentage.

Tool activity supports short summaries and expandable complete arguments, commands, results and errors, including nested PTC calls. Secret-like values are redacted for display. Nodes cross the local workspace boundary: Default access permits listing saved records, AI approvals review exact remote operations, and Full Access executes them directly. Remote connection settings are bound to a review; a local script is never treated as evidence for a similarly named remote script. Uninspected remote scripts require the owner to decide.
