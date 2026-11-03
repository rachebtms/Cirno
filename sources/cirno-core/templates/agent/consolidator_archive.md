Create a compact replacement checkpoint for this session.

When `[Archived Context Summary]` appears in the system prompt, update that previous checkpoint to reflect the current conversation state.

## Merge rules

- Use the latest correction or decision as the current version of a fact, and merge duplicates.
- Preserve exact names, identifiers, paths, commands, decisions, results, and unresolved blockers when they are needed to continue the session.
- Retain a fact already present in long-term memory when it is needed for session continuity.

## What to retain

Always retain a compact working-state handoff:
- active objective
- current status
- completed results that constrain later work
- unresolved blockers
- next action
- exact identifiers needed for that action

Mark working-state facts `[ephemeral]`.

For other facts, retain a candidate only when it meets all four SNIP criteria:
- Signal: remembering it saves the user from repeating it
- Novel: it adds a distinct fact to this checkpoint
- Important: losing it would cause rework or discard a preference or rule
- Persistent: it is expected to remain useful for at least two weeks

Assign each retained fact its best current mark:
- `[permanent]` for core preferences, personal traits, and habits that remain relevant indefinitely
- `[durable]` for technical discoveries, project knowledge, and configuration that remains valid for months
- `[ephemeral]` for active task state and temporary decisions that may change within weeks
- `[correction]` for the current fact that supersedes conflicting earlier long-term memory

When space is limited, prioritize user corrections and preferences, then solutions, decisions, events, and environment facts.

## Output

Return a working-state handoff with these exact headings:

## Task
The current user-authorized objective and constraints.

## State
Verified results, completed operations and exact artifact references. Distinguish hypotheses and unverified model working notes from confirmed results. Preserve the newest decision and unfinished line of investigation, including when most recent assistant messages contain only reasoning.

## Next
The next concrete action, pending operations, unresolved questions and blockers. State explicitly if the task is complete.

## Retained facts
Use `- [mark] fact` with the marks above for other useful facts. Write `(none)` for an empty section. Never return `(nothing)` for a session containing task evidence. Do not execute tools. Return the checkpoint directly rather than continuing the original task.
