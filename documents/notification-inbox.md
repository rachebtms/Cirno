# Notification inbox

Open Inbox from the workspace launcher on desktop or mobile. Its category pages are:

| Route | Contents |
| --- | --- |
| `#/inbox?category=operations` | Asynchronous questions, tool approvals and conversation recovery requiring user action |
| `#/inbox?category=conversations` | Explicit work reports; ordinary replies and successful completions are not recorded |
| `#/inbox?category=system` | Context consolidation outcomes and failed runs, including failure reasons |

Notice bodies use the same Markdown renderer as conversation replies, including
headings, lists, tables, links and code blocks. Approval argument details retain
their literal JSON display.

Operation notices open the existing workflow: questions return to the originating conversation's composer, tool approvals open the requested operation, and recovery opens the affected conversation. Marking a notice read does not answer a question or approve access. Accepted user answers resolve their corresponding question notices; messages from another agent cannot stand in for user answers.

Inbox reads and updates use the authenticated server's selected configuration
state directory. Approval decisions, retained decisions and review-setting reloads
use that same owner, including older notices whose conversation generation must
be recovered from the saved approval. Changing a process-global configuration
selection does not redirect an existing review service to another instance.
SSH operation evidence and its final recheck inspect the Node tool's actual
connection store. A matching imported credential ID in another instance cannot
substitute that instance's host or connection hash during approval.

The composer's question queue follows saved conversation history. If editing an earlier message removes a saved answer while retaining its question, that question becomes pending again in the original order. A temporary delivery acknowledgement does not permanently mark the question as answered.

## Notification preferences

Settings → Browser notifications allows each category to be muted separately. These preferences synchronize through the owner profile; muting disables that category's browser alerts and sounds while keeping inbox records and pending actions. Notification permission must be granted in each browser. Delivery also requires the overall switch and an available page. Popups use category-level text rather than exposing message bodies, paths or approval codes. Opening the page does not replay every historical notice as a popup.

## Storage

Records live in `state/notifications/inbox.sqlite3` under the instance root, separate from Agent Home, conversation and memory stores. Pages load records in batches. The main interface refreshes the inbox summary and recent records every ten seconds without a model call. Cleanup retains the latest 10,000 records and preserves unresolved actions outside that window. Temporary-conversation notices are not persisted.

Each page's rows, unread counts and delivery cursor share one database snapshot. Mark-read responses include the committed timestamp and unread counts for all categories, so a failed subsequent refresh does not undo a saved read or leave the old unread badge. A page read spanning a completed local mark-read is fetched again serially, keeping its category and pagination cursor. Refresh errors remain visible. Accepted inbox writes finish before shutdown cancellation releases their request; no model call is involved. Leaving the Inbox tab or replacing its view prevents a delayed Open response from navigating away from the user's current page.

Snapshots and read receipts also carry a committed revision; each notice carries
its last content/status revision. Read acknowledgements advance the snapshot
revision without changing the notice's content revision. A delayed read receipt cannot replace newer
observed counts or mark a newly arrived or updated notice read, including rows
retained from older pages. Actual changes advance the revision in the same
transaction as their data; failed writes roll both back. Repeated unchanged
notices or reads do not advance it. Existing databases start with revision zero
without changing notice IDs, pagination sequences or timestamps. Revision state
lives inside the existing Inbox database, and does not replace Telegram's separate
delivery-queue revision. Older servers and receipts retain their previous format
compatibility.

Switching connections immediately hides the previous Inbox snapshot. Late read
receipts and retained callbacks belong to their original connection lifetime,
including switching away and back to the same client object. An old pending
action cannot block or clear a replacement connection's action. Hiding and
returning to the same Inbox can still finish its initial read.

## Coordination reports

The Router has the full ordinary tool set plus coordination and Project management. It handles simple checks directly and delegates medium and large tasks to ordinary conversations. Only the Router receives `user.message`; ordinary conversations stream assistant replies. PTC, compaction and context accounting use the same role selection.

`conversations.report` records a state, factual summary, artifact paths and optional `human_action` question. Routine progress and waiting update passive records. Results, blockers, failures and new questions enter the coordinator's durable inbox. Independent work can continue while a question is pending. Omitting `human_action` retains it; an empty string clears it. A `ready` report may include a question about a reviewable result, such as choosing between validated options; it does not mean the Goal is complete.

Reporting `ready` does not complete a Goal. The executing model verifies the result and explicitly calls `goals.update(action="complete")`. Delegated Goal completion uses the same report path and reuses an already queued ready report. Failed report delivery remains pending for ordered retry; newer progress does not overwrite it. A conversation can retain at most twenty pending reports; a full queue returns an error while existing reports continue to drain. A report failure in one conversation does not prevent other Goals from waking. Inbox writes are retried independently of coordinator delivery: a notification storage failure never changes a completed execution to a failed task or reruns its tools.

Stable IDs and receipts in conversation storage deduplicate coordination inputs across restarts. Queued means accepted for delivery; consumed means committed into the destination turn's context, not successfully completed. Receipts are scoped to the destination generation and removed with the conversation. Delegation preserves the source conversation, turn/message references and a bounded original-request excerpt. Reports and routing summaries do not grant additional user authorization.

## Telegram delivery

Bind your personal account in Settings → Telegram using the expiring PIN sent to your bot. Router replies and the three Inbox categories have separate notification switches. Disabling Telegram delivery preserves these choices. Browser mutes do not change Telegram delivery. Configure a phone-accessible Web UI address to attach an Open Cirno Inbox button to notifications; actions are completed in the authenticated browser. See [configuration](configuration.md#channels-and-remote-browsers).

Telegram binding, sender authorization and final/stream destination checks perform storage work off the shared event loop. A busy database does not block unrelated conversations. Shutdown cancellation waits for accepted binding verification and pending-action updates, as well as Inbox capture, answer, queue-pruning and queue-acknowledgement writes. Notifications selected for delivery enter the durable outbox before their Inbox queue revision is acknowledged; the stored notice revision prevents acknowledging a newer update with an older delivery receipt.

Telegram settings, PIN verification, sender admission, final/stream delivery,
Router forwarding and downloaded media retain their server's selected instance
directory. Changing a global configuration selection does not move an existing
channel to another instance's binding or Inbox. Initial status reads also finish
their local database initialization before cancellation returns.

Queued Inbox notifications retain the notice content/status revision separately
from the queue acknowledgement token. Immediately before transport, Cirno rejects
a removed, changed or resolved notice instead of sending an obsolete action
request. Marking an unchanged notice read does not invalidate delivery. Older
queued messages without a content revision still recheck the binding, category
and pending action status.

An explicitly rejected streaming preview does not count as delivery: its buffered text is still sent at the final response boundary. Empty or whitespace-only streams retire their buffer and typing/reaction state without sending an empty message. A continuation boundary keeps the current preview, and an older stream's terminal event cannot clear a newer stream. An unknown new-message submission remains an error and is not replayed automatically.

Runtime retry, recovery and final reports for one execution share `turn_id`. New runtime reports share a stable `execution_id` across retry/recovery/final states, identifying updates to one execution rather than separate runs. Older durable delivery receipts retain their original payload. Terminal runtime results retire undelivered retry-health snapshots, including snapshots retained by an older pending sender. This does not delete already delivered history or discard a distinct verified artifact report. Retry-health updates are coordinator inbox inputs, separate from ordinary Reports notifications.

These statuses describe separate objects: a runtime report can say a **turn failed**, its unfinished **Goal is blocked**, and its **execution is interrupted** awaiting continuation. Recovery `attempts` counts explicit Continue actions, not the provider's automatic network retries. The owner or an authorized Router can continue the saved work; recovery then becomes `resuming`, its attempt count increases, and supervision shows the execution as queued until it starts, with the Goal active again. The old failed-turn report remains an account of that earlier execution.

The Goal scheduler waits for an executing turn to settle its detailed result before creating a Goal lifecycle report, preventing a transient blocked Goal from producing a second failure report. Continue and explicit Goal resume remove obsolete runtime-stop recap text while preserving actual saved progress; the earlier failure remains in its report and recovery history.
