# Workspace access and operation review

A conversation keeps one selected access mode. The current turn captures that choice; stop the turn before changing it.

- **Default** uses the existing workspace path and command guards. Explicit Home resources and configured tool capabilities retain their own policies.
- **AI review** keeps those restrictions. A blocked filesystem operation or command goes to an independent model request using the active model connection. It receives only the original human request, exact operation and bounded contents of explicitly referenced scripts. It does not receive conversation history, Cirno memory, profiles or tools.
- **Full Access** disables application workspace restrictions. An operating-system sandbox, if configured, still applies.

AI review is a convenience, not an additional security guarantee. It can approve an unsafe operation. Its interface displays a risk warning. Use Default when operations outside the workspace should remain prohibited.

The reviewer returns `approve`, `deny` or `human`, with a reason. Invalid output, provider errors, timeouts, missing human context or incomplete script inspection require a human decision. Referenced script inspection is limited to four files of 16 KiB each; oversized or unreadable scripts require the owner. Review input is bounded and no additional model process is loaded.

An automatic approval applies only to that tool invocation. Uncertain operations appear under Inbox → Actions with their arguments and explanation. Approve or deny from the authenticated browser. An approval covers one use of the exact operation, original request, conversation generation and inspected script contents. It does not change the conversation to Full Access. Changing arguments or scripts requires a new decision; clearing or editing the conversation invalidates its old approvals. An unused human approval expires after one hour.

Pending approval has no tool effects. A related running Goal waits without a timer rather than repeatedly attempting the blocked operation. The owner's decision queues a durable, source-labelled continuation. Completed work is not replayed automatically. If the worker has been stopped, the owner can also continue it through the usual controls.

Approved commands cannot receive interactive standard input. They can run to completion or continue as owned, pollable command sessions. Approval does not bypass private-URL restrictions, grant another conversation access, or override a configured operating-system sandbox. PTC nested calls use the same tool execution boundary.

Decision records are separate from Agent Home and memory, under `state/security/approvals.sqlite3`. Inbox notices are stored in the notification database. Review and owner-decision errors remain visible.
