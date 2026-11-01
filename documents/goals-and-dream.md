# Goals, coordination and Skills

A Goal is a durable objective belonging to one conversation. Use `/goal` to request sustained work. The executing model records the objective and completion criteria; a normal reply does not complete it. Completion requires explicit `goals.update(action="complete")` after verification.

Logical names below use dots. Native calls use double underscores, such as `goals__create`; PTC uses `await tools.goals.create(...)`. See [tool namespaces](architecture/tools.md).

| Operation | Purpose |
| --- | --- |
| `goals.create` | Create an objective, optionally overriding the default continuation limit |
| `goals.get` | Read the objective, state and continuation count |
| `goals.update` | `continue`, `wait`, `complete`, `block`, `pause`, `resume`, `stop`, `cancel`, `replace` or `delete` |

The instance continuation limit is configured under Settings → Advanced. Zero means unlimited and is the default. `/goal` does not require a limit. Counts persist across waiting, pauses and gateway restarts. Creating or replacing a Goal starts a new count. Reaching a finite limit pauses it and preserves progress.

A running Goal continues between execution segments until it completes, waits, blocks or is paused/stopped. `wait` saves progress and a `wake_after_seconds` deadline. Due work resumes through its conversation queue; incoming conversation input also wakes a waiting Goal. Deadlines require the gateway to run; overdue work is handled after restart. Interrupted tools follow the existing recovery process rather than being blindly repeated.

Pause prevents automatic continuation. The conversation Stop control cancels active execution and stops its Goal until resumed. The model's `stop` operation stops continuation without interrupting a tool already executing. Creation, replacement, limit changes and user control operations require fresh user input. Automatic continuation can save progress, wait, block or complete the existing objective.

## Coordination

Cirno is a persistent coordination conversation with a restricted tool selection. It discusses priorities, delegates execution and organizes incoming reports. Ordinary conversations execute commands, modify files and use Nodes, CLI Apps, MCP and worker subagents. They retain streamed assistant replies. Cirno's internal execution history is collapsed by default; it sends visible messages and files through `user.message`. Ordinary conversations do not receive this operation.

Both roles can use `conversations.create`, `conversations.send`, `conversations.search` and `conversations.read`. The returned `@handle` is a stable conversation address. An ordinary conversation can send a report to Cirno with `conversations.send(to="Cirno", ...)`, or use `conversations.report` for structured state, summary, artifacts and a pending user question. Routine progress is passive; results, blockers, failures and new questions wake the coordinator. A `ready` report does not complete a Goal.

Coordination messages are journaled before delivery and deduplicated by stable IDs and destination-generation receipts. Queued does not mean finished. Delegation preserves source references and the original request; worker reports do not grant new authorization. Each conversation retains its own history, Goal, queue and cancellation scope. See [inbox and report delivery](notification-inbox.md).

`conversations.set_title` lets the model set a concise title in the user's language. Automatic title generation is also available; manual titles and Cirno's identity are preserved.

## Heartbeat

When enabled under Settings → System, the protected heartbeat job queues active `Home/HEARTBEAT.md` instructions into Cirno. Pending checks survive restart and use the normal conversation queue. Cirno is instructed to notify only when something needs attention. Use Automations for an explicit time or interval; heartbeat is for flexible background checks.

## Memory and learned Skills

Memory, profiles and Skills belong to Home rather than workspaces. See [memory architecture](architecture/memory.md) for bounded profile injection, task checkpoints, evidence, scopes and Dream's per-input confirmations. Settings → Memory manages recall and consolidation; Settings → Personality edits shared profile files.

Dream can extract or improve a reusable workflow under `Home/skills/<name>/`. Its restricted file tools cannot modify application code. Home Skills are checked for identity metadata and Python/shell syntax before being offered as available. Syntax validation does not execute scripts or prove behavior.

File-tool edits preserve versions under `Home/skills-history/<name>/<revision>/`; UI deletion also preserves the current version. Unchanged content reuses its revision. `skills.validate`, `skills.history` and Settings → Skills expose validation and history paths. The model can read old files and deliberately edit the current Skill. There is no automatic rollback.
