# Conversation routing and cancellation

A conversation has one immutable canonical session key, formed from its channel and chat identifier. Browser conversations use `websocket:<chat_id>`. Conversations have separate histories, input queues and active task groups. Shared execution sessions are not supported.

WebSocket notifications include their originating chat identifier. Client subscriptions route messages by that identifier, including after reconnecting; changing the visible conversation does not change a running turn’s destination.

Stop is a priority command for the selected conversation. It cancels its active model calls, tool work, subagents and owned command processes, then clears queued follow-ups. Other conversations continue running. The interface waits for the server’s acknowledgement; failed cancellation remains visible as an error. Stop and clear-conversation commands are not queued for replay across a disconnected transport.

A failed status write or child cleanup does not skip the remaining cleanup.
The server reports the original failures after those operations settle.

The Router’s clear button asks for confirmation and uses `/clear`. Reset stops the current execution, starts a new session generation and removes the old transcript, Goal and report state while keeping the conversation identity and saved memory. Empty persisted conversations and the new-conversation page share the same composer presentation.

Server-created providers use the configured `network.requestTimeoutS` and `network.streamIdleTimeoutS`, both 120 seconds by default, and `network.providerMaxRetries`, default three with a minimum of three. Manage these under Settings → Network & retries and restart when required. Provider-constructor environment variables are lower-level defaults and do not override those saved server settings. The request timeout covers connection setup and non-streaming response waits. Streaming reads use their separate inactivity timeout; a continuously active stream has no total-duration cutoff. These values reach native adapters as well as Chat Completions, Responses HTTP and Responses WebSocket transports. Cancellation stops retry waits. Blocking SDK operations settle within their configured network timeouts before their resources are released.

The server owns work; the frontend projects conversation state.

## Identity and display names

Browser routes and WebSocket chat identifiers use fixed UUIDs. The Router has a
reserved UUID within each instance; workers receive generated UUIDs. Public tool
references expose a stable opaque `id` derived from the canonical key, alongside
the current display `name`. Resolve stored references by ID, not by name.

Conversation tools accept the stable ID or a current `@name`; IDs are preferred
for follow-ups. Names are unique display aliases, and the owner can change the
Router’s alias under Settings → Account. Session metadata owns the current alias;
the account database keeps only the initial registration choice for bootstrap.
Login and startup never replace an existing alias with that initial choice.

Rename checks and header updates share one transaction. No history, checkpoint,
queued input, Goal, memory provenance or Project link is rewritten. Source badges
and compact tool summaries resolve IDs to current `@names`; raw tool details and
trace events retain their original IDs and historical text stays as written.

## Execution failures

Admission, recovery checks, concurrency waits, Goal guards and route setup share
one failure boundary with model execution. A failed accepted input emits its
terminal result and releases automation waiters. A delegated conversation records
the failed stage through the same work-report service as model failures. A failed
input does not stop the main bus loop or the next input in its conversation.

Session privacy controls diagnostic tracebacks, including failures before context
restoration or after cache eviction. Temporary conversations keep their in-memory
history while remaining excluded from durable memory and reporting.
