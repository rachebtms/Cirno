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

Pause prevents automatic continuation. The conversation Stop control cancels active execution and stops its Goal until resumed. The model's `stop` operation stops continuation without interrupting a tool already executing. Session controls, `/stop` and session removal share one cancellation owner. Accepted stops wait for settlement before returning caller cancellation. Worker cleanup errors are reported instead of returning a successful stop. Creation, replacement, limit changes and user control operations require fresh user input. Automatic continuation can save progress, wait, block or complete the existing objective.

## Coordination

The Router is a persistent coordination conversation with the full ordinary tool set. It handles brief checks directly, delegates medium and large tasks and organizes incoming reports. Paper reading, literature reviews, development and experiments start in a Worker before substantive execution; a brief resource check can run in the Router. An explicit owner request to work directly here takes precedence. Both roles can execute commands, modify files and use Nodes, CLI Apps, MCP and worker subagents under the same access policies. Ordinary conversations retain streamed assistant replies. The Router's internal execution history is collapsed by default; it sends visible messages and files through `user.message`. Ordinary conversations do not receive this operation.

Both roles can use `conversations.create`, `conversations.send`, `conversations.search` and `conversations.read`. Results include a stable conversation `id` and its current display `@name`. Save the ID for follow-ups: names can change or be reused. `conversations.send(to="<conversation-id>", ...)` sends a request or reply to that conversation; `conversations.report` records structured state, summary, artifacts and a pending user question for the delegating conversation, or the Router. Routine progress is passive; results, blockers, failures and new questions wake the coordinator. A `ready` report does not complete a Goal.

Coordination messages are journaled before delivery and deduplicated by stable IDs and destination-generation receipts. Queued does not mean finished. Delegation preserves source references and the original request; worker reports do not grant new authorization. Each conversation retains its own history, Goal, queue and cancellation scope. See [inbox and report delivery](notification-inbox.md).

The Continue button, `/resume` and Router recovery controls use the same saved-state action. Simultaneous requests queue one continuation; stale requests receive a conflict. Accepted actions finish their state/queue handoff before caller cancellation returns. Maintenance refuses new actions before changing recovery state and waits for accepted actions to settle.

Only the Router receives `conversations.control` and `goals.control`. `conversations.control(action="list")` needs no target and returns running, queued and interrupted conversations plus the configured worker concurrency limit (`0` means unlimited) and background subagent limit. `CIRNO_MAX_CONCURRENT_REQUESTS` limits ordinary conversation execution; the Router has a separate reserved slot so saturated workers cannot block supervision. `action="get"` also reports the target’s execution and recovery state. `action="continue"` uses the same durable recovery path as the owner’s Continue button after an interruption or LLM API failure, without replaying completed tools. It can stop/continue other saved Web conversations and inspect or change their Goals while preserving progress and continuation counts. `goals.control` has no completion action: the executing worker must verify and finish its own Goal. Each control records the Router’s stable ID and current display name.

`conversations.control(action="get", to="@handle")` reads a worker's workspace, PTC mode and selected model preset, including the available preset IDs. `action="configure"` changes any combination of `workspace`, `ptc_mode` and `model_preset` on an idle conversation. Stop active work first, configure it, then continue when ready. Workspace must be an existing absolute server directory; `~/` is accepted. The `model_preset` value uses a stable model ID from the configured catalog; `default` restores the instance's active model. Changes are persisted together and broadcast to the Web UI. Configuration does not restart work, move files, clear history, alter the Goal or Project membership, or switch its Default/AI review/Full Access mode. Ordinary conversations do not receive this supervisory capability.

`conversations.set_title` lets the model set a concise title in the user's language. Automatic title generation is also available; manual titles and the Router's identity are preserved.

## Delegated execution results and failures

Independent conversations created through delegation automatically report terminal execution results to their delegating coordinator. The runtime reports LLM/API failures, empty final answers and unexpected execution-stage exceptions even if the model cannot call `conversations.report`. Reports include the returned output or a bounded excerpt, the source conversation, stop reason, public failure category, selected model and failing stage when available. Read the saved source conversation for complete output and execution details. An execution result does not itself complete a Goal.

A detailed explicit report from the same execution is reused. Segments that will automatically continue and ordinary user conversations do not generate extra result reports. API failures block unfinished Goals instead of silently marking them complete. User cancellation and pauses are respected.

A retry episode and its recovery also wake the coordinator, without blocking the running Goal. Repeated attempts in the same episode are coalesced. If delivery is unavailable, pending retry/recovery updates for the same execution retain only the latest health state; result and failure reports are preserved separately. The Router must check the latest state before acting on a delayed retry notice. These coordination-only retry updates do not create ordinary reply notifications in Inbox.

Reports enter the existing durable conversation inbox and pending report queue. Failed delivery is retried without rerunning the worker; acknowledged reports are not delivered twice. Reports, notifications and delivery acknowledgements belong to their original source generation; clearing or rewriting that conversation prevents an old report from modifying its replacement. Pending reports survive restart and can reach the Router when its provider is available again. A generic Goal status notice does not overwrite a more detailed failure report. Private subagent tasks continue to report outcomes and errors to their owning conversation through the existing task-result channel.

The Router's recovery guidance asks it to inspect the worker's saved state before selecting another configured model or continuing authorized work. Unclear external side effects and missing credentials require owner attention; recovery does not authorize replaying commands or reversing an owner Stop.

## Heartbeat

When enabled under Settings → Agent heartbeat, the protected heartbeat job queues active `Home/HEARTBEAT.md` instructions into the Router. Pending checks survive restart and use the normal conversation queue. The Router is instructed to notify only when something needs attention. Use Automations for an explicit time or interval; heartbeat is for flexible background checks.

Ordinary scheduled tasks run in their bound conversation, including tasks named
`dream` or `heartbeat`. System maintenance uses its own fixed identity. An
unreadable heartbeat file reports an error; a missing file skips the check.

## Memory and learned Skills

Memory, profiles and Skills belong to Home rather than workspaces. Settings → Context consolidation controls the combined checkpoint, experience retention and self-improvement pass. See [memory architecture](architecture/memory.md) for sources, scopes, retryable receipts and cache behavior. Memory retrieval configures recall; Personality edits shared profiles.

Workers retain useful verified lessons at milestones, after a successful failure/fix and after user corrections. They need not wait for task completion. Context consolidation provides the systematic second opportunity whenever a long task fills its window, as well as during manual and idle consolidation. The same model response makes the checkpoint and learning plan; task execution resumes after persistence. There is no independent Dream scheduler and no additional background model execution.

The pass can correct a fully supplied existing Skill using verified evidence and can create a new Skill after recurrence in another independent task. Skill versions are retained. Static metadata/script checks do not establish effectiveness; preserve actual foreground test evidence and explicitly mark remaining behavioral work. A private subagent returns lessons to its owning Worker; Router delegation and execution budgets remain unchanged. Skip trivial or unsupported learning.

## Context consolidation during active work

Settings → Context consolidation separates the active-work trigger from idle compaction. `agents.defaults.activeCompactPercent` is the percentage of the selected model's context window checked before every request, including tool rounds. The effective budget is the smaller of that percentage and the window minus reserved output and the safety buffer. The default, 100, preserves the maximum safe input budget; it never removes the output reserve. Lower values compact earlier. The active threshold does not change the idle timer or idle retention percentage.

`MEMORY.md` remains automatically injected, now as a persisted snapshot on fresh input when it changes. Memory updates do not rewrite the system prefix or historical requests. Coordination records also stay on fresh inputs. Personality/tool/model changes and actual context consolidation can still change request prefixes. Cache hit rates depend on new input volume and provider behavior; they are not guaranteed to exceed a fixed percentage.

Tool activity supports short summaries and expandable complete arguments, commands, results and errors, including nested PTC calls. Secret-like values are redacted for display. Nodes cross the local workspace boundary: Default access permits listing saved records, AI approvals review exact remote operations, and Full Access executes them directly. Remote connection settings are bound to a review; a local script is never treated as evidence for a similarly named remote script. Uninspected remote scripts require the owner to decide.

## Resuming interrupted conversations

A new execution in an interrupted Web conversation resolves the previous interruption, including when the Router, Heartbeat or a scheduled input restarts it through internal routing. The obsolete Continue notice is removed, and the resolved state survives browser reloads. A subsequent genuine failure creates a new interruption notice. Delayed coordination messages and reply-timeout notices belong to their original conversation generation; they cannot revive deleted conversations or run against a replacement context.

When a new message supersedes an active recovery, the runtime first waits for cancellation to save its latest checkpoint, then reads that committed state. Completed tool results are retained once. Completion and failure events from an older generation cannot recreate a deleted conversation or mark a rewritten context as interrupted; recovery notifications carry the same generation boundary.

Internal work reports remain model context rather than human messages. Editing a human message rewinds visible history at that message's saved turn ID; report-only model inputs never become visible chat prompts during the rewrite. Branching maps the displayed prompt boundary to its saved turn identity before copying model context, so internal reports do not shift the branch point. The original report provenance is retained. Repeated coordination delivery creates one visible input as well as one execution. Delayed requests from a replaced generation are rejected before command dispatch or input notifications, including `/stop`.


## Local triggers

`/trigger <name>` creates a trigger for the current conversation. Automations
shows a copyable command using the installed Python interpreter and
`python -m cirno_core.triggers --store <instance-trigger-directory> <id> <message>`.
It queues a delivery in `state/triggers/`; the running service consumes it.
The generated command targets that exact instance, including paths with spaces.

Unreadable automation catalogs or malformed action logs remain in place and
produce an error instead of being replaced with empty state. A failed scheduler
tick reports a system notice and waits before retrying; an unsaved completed
execution is persisted before another execution can run.
