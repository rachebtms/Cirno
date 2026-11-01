# Conversation routing and cancellation

A conversation has one canonical session key, formed from its channel and chat identifier. Browser conversations use `websocket:<chat_id>`. Conversations have separate histories, input queues and active task groups. Shared execution sessions are not supported.

WebSocket notifications include their originating chat identifier. Client subscriptions route messages by that identifier, including after reconnecting; changing the visible conversation does not change a running turn’s destination.

Stop is a priority command for the selected conversation. It cancels its active model calls, tool work, subagents and owned command processes, then clears queued follow-ups. Other conversations continue running. The interface waits for the gateway’s acknowledgement; failed cancellation remains visible as an error. Stop and clear-conversation commands are not queued for replay across a disconnected transport.

Cirno’s clear button asks for confirmation and uses `/new`. Reset stops the current execution, starts a new session generation and removes the old transcript, Goal and report state while keeping the conversation identity and saved memory. Empty persisted conversations and the new-conversation page share the same composer presentation.

Gateway-created providers use the configured `network.requestTimeoutS` and `network.streamIdleTimeoutS`, both 120 seconds by default, and `network.providerMaxRetries`, default three with a minimum of three. Manage these under Settings → System and restart when required. Provider-constructor environment variables are lower-level defaults and do not override those saved gateway settings. Cancellation interrupts provider requests and retry waits.

The frontend and gateway retain the upstream execution boundary: the gateway owns work; the frontend projects conversation state.
