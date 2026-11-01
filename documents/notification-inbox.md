# Notification inbox

The inbox appears beside Cirno and Automations in the main sidebar. Its category pages are:

| Route | Contents |
| --- | --- |
| `#/inbox?category=operations` | Asynchronous questions, pairing approvals and conversation recovery requiring user action |
| `#/inbox?category=conversations` | Explicit work reports and failed runs; ordinary replies and successful completions are not recorded |
| `#/inbox?category=system` | Dream and context-compaction outcomes, including failure reasons |

Operation notices open the existing workflow: questions return to the originating conversation's composer, pairing decisions use the pairing interface, and recovery opens the affected conversation. Marking a notice read does not answer a question or approve access. Accepted user answers resolve their corresponding question notices; messages from another agent cannot stand in for user answers.

## Notification preferences

Settings allows each category to be muted separately. Muting controls this browser's notification popups and sounds; it does not remove inbox records or cancel pending actions. Browser notifications also require the overall switch, permission and an available page. Popups use category-level text rather than exposing message bodies, paths or approval codes. Opening the page does not replay every historical notice as a popup.

## Storage

Records live in `Home/notifications/inbox.sqlite3`, separate from conversation and memory stores. Pages load records in batches. The main interface refreshes the inbox summary and recent records every ten seconds without a model call. Cleanup retains the latest 10,000 records and preserves unresolved actions outside that window. Temporary-conversation notices are not persisted.

Ordinary replies and successful turn completions are not written to Inbox. Reports, failures and action requests are retained.

## Coordination reports

Cirno has coordination, memory, reference-reading and lifecycle tools. It delegates commands, file changes, Nodes, CLI Apps, MCP execution and worker subtasks to ordinary conversations. Only Cirno receives `user.message`; ordinary conversations stream assistant replies. PTC, compaction and context accounting use the same role selection.

`conversations.report` records a state, factual summary, artifact paths and optional `human_action` question. Routine progress and waiting update passive records. Results, blockers, failures and new questions enter the coordinator's durable inbox. Independent work can continue while a question is pending. Omitting `human_action` retains it; an empty string clears it. A `ready` report cannot retain an unanswered question.

Reporting `ready` does not complete a Goal. The executing model verifies the result and explicitly calls `goals.update(action="complete")`. Delegated Goal completion uses the same report path and reuses an already queued ready report. Failed report delivery remains pending for ordered retry; newer progress does not overwrite it. A conversation can retain at most twenty pending reports; a full queue returns an error.

Stable IDs and receipts in conversation storage deduplicate coordination inputs across restarts. Queued means accepted for delivery; consumed means committed into the destination turn's context, not successfully completed. Receipts are scoped to the destination generation and removed with the conversation. Delegation preserves the source conversation, turn/message references and a bounded original-request excerpt. Reports and routing summaries do not grant additional user authorization.

## Telegram delivery

Bind your personal account in Settings → Telegram using the expiring PIN sent to your bot. Cirno replies and the three Inbox categories have separate notification switches. Browser mutes do not change Telegram delivery. Configure a phone-accessible Web UI address to attach an Open Cirno Inbox button to notifications; actions are completed in the authenticated browser. See [configuration](configuration.md#channels-and-remote-browsers).
