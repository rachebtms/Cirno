# Workspace access and operation review

A conversation keeps one selected access mode. The current turn captures that choice; stop the turn before changing it.

- **Default** uses the existing workspace path and command guards. Explicit Home resources and configured tool capabilities retain their own policies.
- **AI review** keeps those restrictions. A blocked filesystem operation or command goes to an independent model request using the active model connection. It receives only the original human request, exact operation and bounded contents of explicitly referenced scripts. It does not receive conversation history, Cirno memory, profiles or tools.
- **Full Access** disables application workspace restrictions. An operating-system sandbox, if configured, still applies.

AI review is a convenience, not an additional security guarantee. It can approve an unsafe operation. Its interface displays a risk warning. Use Default when operations outside the workspace should remain prohibited.

The reviewer returns `approve`, `deny` or `human`, with a reason. Invalid output, provider errors, timeouts, missing human context or incomplete script inspection require a human decision. Referenced script inspection is limited to four files of 16 KiB each; oversized or unreadable scripts require the owner. Review input is bounded and no additional model process is loaded.

An automatic approval applies only to that tool invocation. Uncertain operations appear under Inbox → Actions with their arguments and explanation. Approve or deny from the authenticated browser. An approval covers one use of the exact operation, original request, conversation generation and inspected script contents. It does not change the conversation to Full Access. Changing arguments or scripts requires a new decision; clearing or editing the conversation invalidates its old approvals. An unused human approval expires after one hour.

Pending approval has no tool effects. A related running Goal waits without a timer rather than repeatedly attempting the blocked operation. The owner's decision normally queues a durable, source-labelled continuation. A later pause, Stop or Goal closure takes precedence: the decision is retained, but does not reactivate the Goal or wake the stopped task. A decision already queued before Stop is checked again at admission and before execution, and its obsolete follow-up is acknowledged without clearing the stopped recovery state. Explicit Continue/Goal resume can use a still-valid one-use grant later. Completed work is not replayed automatically.

The model review can be cancelled without waiting for a normal completion. Once a reviewed decision starts
local persistence, cancellation waits for its decision record, Inbox notice and
related Goal bookkeeping to settle together. Accepted local evidence reads and
storage initialization also settle before cancellation returns. A concurrent
Stop keeps the Goal stopped; saving a pending notice does not resume it. This
does not execute the proposed tool or add a concurrent model request.
The decision and Inbox databases commit separately; publication failures remain
visible errors rather than permission to execute the proposed tool.
An unfinished publication is journaled in the existing approval database. The
next identical operation check, or startup before input admission, repairs its
missing notice and Goal bookkeeping without repeating the model review. The
notice retains the inspected arguments, source generation and access boundary.
Review persistence and authenticated owner decisions use the same local writer,
so a late pending update cannot overwrite the owner's decision. Accepted owner
decisions and each local startup settlement also finish before cancellation returns.

New approvals bind Goal bookkeeping to the Goal that was active when review
started. Recovery cannot put a replacement Goal into waiting or queue the old
operation as its continuation. Stopped Goals remain stopped. Older records keep
their IDs and timestamps; their notices can be repaired, but missing original
Goal identities are not guessed for a new waiting transition. A one-use approval
already consumed before interrupted delivery remains approved in the recovered
notice; recovery does not restore that grant or execute the operation again.
Late review calls read their saved source without creating it: deleting the
conversation cannot leave behind an empty replacement conversation from review.

Approved commands cannot receive interactive standard input. They can run to completion or continue as owned, pollable command sessions. Approval does not bypass private-URL restrictions, grant another conversation access, or override a configured operating-system sandbox. PTC nested calls use the same tool execution boundary.

Decision records are separate from Agent Home and memory, under `state/security/approvals.sqlite3`. Inbox notices are stored in the notification database. Review and owner-decision errors remain visible.

Retrying delivery of an approved or denied decision rechecks the current
conversation generation before returning the saved decision. A matching
generation can retry unfinished delivery; a deleted or replaced conversation
cannot reuse that retry path. Approval notices retain their source generation
both while pending and after a decision. When opening an older notice that
lacks it, Cirno resolves the source from the durable approval record. Missing
or obsolete sources are shown as unavailable instead of opening a replacement
conversation.
