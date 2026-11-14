# Notification inbox

Open Inbox from the workspace launcher on desktop or mobile. Its category pages are:

| Route | Contents |
| --- | --- |
| `#/inbox?category=operations` | Asynchronous questions, tool approvals and conversation recovery requiring user action |
| `#/inbox?category=conversations` | Explicit work reports; ordinary replies and successful completions are not recorded |
| `#/inbox?category=system` | Context consolidation outcomes and failed runs, including failure reasons |

Operation notices open the existing workflow: questions return to the originating conversation's composer, tool approvals open the requested operation, and recovery opens the affected conversation. Marking a notice read does not answer a question or approve access. Accepted user answers resolve their corresponding question notices; messages from another agent cannot stand in for user answers.

The composer's question queue follows saved conversation history. If editing an earlier message removes a saved answer while retaining its question, that question becomes pending again in the original order. A temporary delivery acknowledgement does not permanently mark the question as answered.

## Notification preferences

Settings → Browser notifications allows each category to be muted separately. These preferences synchronize through the owner profile; muting disables that category's browser alerts and sounds while keeping inbox records and pending actions. Notification permission must be granted in each browser. Delivery also requires the overall switch and an available page. Popups use category-level text rather than exposing message bodies, paths or approval codes. Opening the page does not replay every historical notice as a popup.

## Storage

Records live in `state/notifications/inbox.sqlite3` under the instance root, separate from Agent Home, conversation and memory stores. Pages load records in batches. The main interface refreshes the inbox summary and recent records every ten seconds without a model call. Cleanup retains the latest 10,000 records and preserves unresolved actions outside that window. Temporary-conversation notices are not persisted.

## Coordination reports

The Router has the full ordinary tool set plus coordination and Project management. It handles simple checks directly and delegates medium and large tasks to ordinary conversations. Only the Router receives `user.message`; ordinary conversations stream assistant replies. PTC, compaction and context accounting use the same role selection.

`conversations.report` records a state, factual summary, artifact paths and optional `human_action` question. Routine progress and waiting update passive records. Results, blockers, failures and new questions enter the coordinator's durable inbox. Independent work can continue while a question is pending. Omitting `human_action` retains it; an empty string clears it. A `ready` report may include a question about a reviewable result, such as choosing between validated options; it does not mean the Goal is complete.

Reporting `ready` does not complete a Goal. The executing model verifies the result and explicitly calls `goals.update(action="complete")`. Delegated Goal completion uses the same report path and reuses an already queued ready report. Failed report delivery remains pending for ordered retry; newer progress does not overwrite it. A conversation can retain at most twenty pending reports; a full queue returns an error while existing reports continue to drain. A report failure in one conversation does not prevent other Goals from waking. Inbox writes are retried independently of coordinator delivery: a notification storage failure never changes a completed execution to a failed task or reruns its tools.

Stable IDs and receipts in conversation storage deduplicate coordination inputs across restarts. Queued means accepted for delivery; consumed means committed into the destination turn's context, not successfully completed. Receipts are scoped to the destination generation and removed with the conversation. Delegation preserves the source conversation, turn/message references and a bounded original-request excerpt. Reports and routing summaries do not grant additional user authorization.

## Telegram delivery

Bind your personal account in Settings → Telegram using the expiring PIN sent to your bot. Router replies and the three Inbox categories have separate notification switches. Disabling Telegram delivery preserves these choices. Browser mutes do not change Telegram delivery. Configure a phone-accessible Web UI address to attach an Open Cirno Inbox button to notifications; actions are completed in the authenticated browser. See [configuration](configuration.md#channels-and-remote-browsers).

Runtime retry, recovery and final reports for one execution share `turn_id`. New runtime reports share a stable `execution_id` across retry/recovery/final states, identifying updates to one execution rather than separate runs. Older durable delivery receipts retain their original payload. Terminal runtime results retire undelivered retry-health snapshots, including snapshots retained by an older pending sender. This does not delete already delivered history or discard a distinct verified artifact report. Retry-health updates are coordinator inbox inputs, separate from ordinary Reports notifications.

These statuses describe separate objects: a runtime report can say a **turn failed**, its unfinished **Goal is blocked**, and its **execution is interrupted** awaiting continuation. Recovery `attempts` counts explicit Continue actions, not the provider's automatic network retries. The owner or an authorized Router can continue the saved work; recovery then becomes `resuming`, its attempt count increases, and supervision shows the execution as queued until it starts, with the Goal active again. The old failed-turn report remains an account of that earlier execution.

The Goal scheduler waits for an executing turn to settle its detailed result before creating a Goal lifecycle report, preventing a transient blocked Goal from producing a second failure report. Continue and explicit Goal resume remove obsolete runtime-stop recap text while preserving actual saved progress; the earlier failure remains in its report and recovery history.
