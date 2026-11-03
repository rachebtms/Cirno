# Configuration

`cirno --port 8000` starts the complete service and Web interface in the foreground. Configure a provider in Settings → Models. An instance stores configuration in `~/.cirno/config.json`; select another instance root with `cirno --home /path/to/instance`.

## Install from a checkout

Requires Python 3.11+ and Node.js 24. From the repository root:

```sh
npm --prefix sources/cirno-web ci
npm --prefix sources/cirno-web run build
python -m pip install -e sources/cirno-core -e sources/cirno-server -e .
cirno --port 8000
```

The initial local launch creates the default configuration automatically. Open `http://localhost:8000`, register the instance owner, and configure a provider and model. First-time setup takes place in the browser. Existing instances retain their previous authentication settings. For a server deployment, see [Docker](docker.md).

## Model providers

A minimal OpenAI-compatible configuration is included in [examples/config.json](examples/config.json):

```json
{
  "agents": {
    "defaults": {
      "provider": "local-api",
      "model": "your-model"
    }
  },
  "providers": {
    "local-api": {
      "apiBase": "https://api.example.com/v1",
      "apiKey": "${CIRNO_API_KEY}"
    }
  }
}
```

Replace the endpoint and model with values accepted by your provider. Set referenced environment variables before starting Cirno; missing references and invalid configuration produce errors. Configuration accepts camelCase and snake_case keys. Provider credentials, named model presets and connection settings can be managed in the browser. Saved connection settings take precedence over provider-constructor environment defaults.

Settings → Network & retries exposes request timeout, stream idle timeout and retry count. The configured defaults are 120 seconds for both timeouts and three retries. Proxy settings determine whether a provider uses the configured shared proxy. Restart the server to apply service-level settings when requested by the interface.

## Settings pages

Overview shows model and web-search status, plus shortcuts to Memory library, Context compaction, Goals & execution, Personality, Telegram, Nodes, MCP and Tools & CLI Apps.

- Models: provider connections, credentials, presets, context-window capacity and generation parameters.
- Appearance, Text & reading, Execution display: theme/language, text size, code wrapping and independent brief/detailed reasoning and tool steps.
- Browser notifications: browser permission, sound and Inbox category mutes for this browser.
- Memory library, Context compaction, Dream consolidation, Memory retrieval: separate pages for stored knowledge, context thresholds, background consolidation and optional embeddings.
- Personality: Home personality, preferences and agent instructions.
- Agent heartbeat: periodic checks of `HEARTBEAT.md` and wakeups in Cirno, separate from service health checks.
- Conversation coordination: concurrent subagents and the per-source outgoing cross-conversation message limit.
- Time & region: automatic or manually selected timezone.
- Goals & execution: default workspace, continuation and execution limits.
- AI approvals: independent review model, review timeout and the switch for automatic review.
- Tools & CLI Apps, Shell execution, Skills: tool availability, shell settings and skill management.
- Web search, Nodes, MCP: independently configured agent connections.
- Telegram: personal account binding and server-side notification preferences. Channel setup configures the Telegram bot token and Web transport.
- Backup & restore: complete instance archives, optional extra directories and import preview.
- Account, Network & retries, Permissions, Server: network policy, access controls and service settings.

The **Add MCP server** panel sits above the MCP catalog, with custom connection and JSON import actions. Custom MCP servers can be edited from **MCP → Manage → Connection → Edit MCP configuration**. The JSON editor loads the saved configuration, including arguments, environment variables, request headers, tool scope and timeouts. Saving updates the same server and reloads its connection. JSON import and configuration editors support indentation with **Format JSON**; invalid JSON is shown as an error without discarding the draft.

See [Home and workspaces](home-and-workspaces.md) for file ownership and [memory](architecture/memory.md) for retrieval and maintenance behavior.

## Channels and remote browsers

Only Telegram and Web (WebSocket) channels are bundled. Authenticated users can install optional support and manage Skills from local or remote browsers, including behind a reverse proxy. Enable and configure them under Settings → Channels.

For Telegram, supply a bot token in Channel setup. In Settings → Telegram, generate a PIN and send `/bind <PIN>` to your bot in a private chat. The eight-digit PIN expires after two minutes, refreshes while the pairing panel remains open, and can be used once. Generating a new PIN invalidates the previous one. A bound account is the only Telegram account admitted to Cirno; group chats, group commands and group callbacks are ignored. Disconnect revokes the binding and any outstanding PIN. Connection errors appear in channel status.

Telegram private input and Heartbeat use the dedicated Cirno conversation. Cirno replies can be mirrored to the bound account, including proactive replies originating in the browser or background work. Inbox Actions, Reports and System notifications use independent server-side switches; browser notification preferences remain local to each browser. Ordinary replies are not added to Inbox. Pending Inbox notifications enter the existing durable delivery outbox, so a restart does not discard an admitted notification. Notifications are rechecked against the current binding before sending. To include an action button, set the Web UI address to one reachable from your phone; the button opens the corresponding Inbox category and conversation. Unanswered questions include their suggested answers in the Telegram notification. Answer and approve in the authenticated Web UI. For Web, configure the listening address, port, authentication, optional public WebSocket address and TLS certificate paths. A remote browser uses the Cirno server and needs no Cirno client installation.

Authenticated remote sessions can select Full Access. It applies to files and commands on the server host. Stop a running conversation before changing its access mode. Use authentication and the deployment's TLS or reverse-proxy configuration when exposing a server outside the local machine.

## Idle context compaction

Settings → Context compaction configures inactivity and two percentages of the active model's context window. Defaults are 15 minutes of inactivity, a 20% trigger and 5% recent-context retention. Idle compaction requires both inactivity and the usage trigger. A zero timeout or trigger disables it. Model preset advanced options can override either percentage; an empty value inherits the global value. Set each model's context-window capacity correctly for meaningful percentages.

Retention must be below a nonzero trigger. Compaction summarizes older context while retaining complete recent turns and paired tool calls/results within its budget. Counts are estimates until a subsequent provider request reports actual usage. Context-window pressure during execution is a separate compaction trigger.

## Projects and conversations

Create projects from the sidebar. A project has an independent ID, name, optional description and optional default working directory; two projects may use the same directory. Conversation menus move conversations into or out of projects. Project menus create conversations, rename projects or delete them. Deleting a project detaches its conversations while preserving history and working files.

The `@handle` beside a conversation is its stable address for coordination tools, not another user. Cirno is the dedicated coordination conversation; ordinary conversations retain execution tools and streamed replies. Both can create delegated conversations, send coordination messages and inspect other conversations through their tools. Only Cirno receives `user.message` for visible reply delivery. See [Goals and coordination](goals-and-dream.md).

## Nodes

Settings → Nodes manages SSH connections, host fingerprints, direct commands and persistent jobs. Supply host, port, SSH username, remote working directory and either key or password authentication. A key path refers to a file on the server. A blank password while editing preserves the saved password. Credentials are stored in the private `state/instance.sqlite3` database and omitted from connection listings. Saved host keys or the server’s `known_hosts` verify the server; compare scanned fingerprints before saving them.

Execute command runs a command and returns output without creating a job. The `nodes` tool namespace also lists connections, transfers files and starts, inspects or stops persistent jobs. Job output, PID and exit status stay on the remote host; tracking records stay in `state/instance.sqlite3`. No remote Cirno daemon or client is installed. Persistent jobs require a POSIX shell, OpenSSH and `setsid`. An uncertain submission exposes its job ID for inspection before resubmitting.

## Service lifecycle

Settings retains Restart. There is no in-app upgrade platform or terminal configuration wizard. The CLI Apps catalog remains available for installing command-line integrations. Source installations upgrade by updating the checkout, rebuilding the browser assets and reinstalling the package; container installations rebuild or pull a published image.

## Account password

Settings → Account shows the registered owner and changes the browser-login password. Enter the current password, a new password and confirmation. The same rules apply as registration: at least ten characters, including an uppercase letter and a symbol. Successful changes keep the current browser signed in, revoke other browser sessions, invalidate server access tokens and reconnect Web UI sockets. Other browsers must sign in again. Password hashes and sessions live in `state/webui-auth.sqlite3`; passwords are not saved in `config.json`. Shared-token authentication has no registered browser account and continues to use the existing server authentication settings.

## Conversation controls and access review

Settings → Goals & execution configures the default workspace, continuation text and its visibility. The workspace setting (`agents.defaults.workspace`) accepts an absolute server path, including `~/…`. Restart when prompted to apply it to new conversations. Saving this setting does not move existing files or change existing conversations' working directories; projects can still supply their own default directory. A saved conversation continues to show its working directory as a locked selector.

Stop preserves context; Continue or `/resume` starts another model request from saved progress. New conversation drafts accept `/temporary on|off`, `/ptc on|off` and `/model <preset>`. Creation-only commands are omitted from established conversations' command menus. `/access default|review|full` selects the permission mode. Model preset names are unique ignoring case.

AI review keeps Default restrictions and reviews blocked operations independently of Cirno memory. Settings → AI approvals selects a saved model preset (or the conversation model), sets a 1–300 second review timeout, and enables or disables automatic review. These settings live under `agents.defaults.approval` as `enabled`, `modelOverride` and `timeoutSeconds`. Disabling review sends blocked operations to the owner for approval. Timeouts, unavailable review models and uncertain cases also appear in Inbox → Actions. Each approval covers one exact operation; it does not grant Full Access. AI can make unsafe decisions, so this mode displays an explicit warning. See [operation review](architecture/access-review.md).

Use message actions to branch or edit an idle human message. Context changes do not undo previous file edits, commands or external actions; tool history triggers a warning. Editing retains attachments and replaces later conversation context before sending the revised request. `/clear` resets only the fixed personal Cirno context through its dedicated control.

## Mobile reconnection and refresh

Returning to the foreground checks the WebSocket connection and reloads the server's conversation state, including reasoning and tool activity missed while the browser was suspended. A stale connection reconnects through the normal authenticated path. The top-right refresh button reloads the page in desktop browsers and installed mobile Web apps, including iPhone Home Screen apps. Reloading the page does not stop the server's task or send the previous prompt again.

## Long tasks and embeddings

See [Model context and long-running work](model-context.md) for per-model reasoning replay, active/idle compaction, checkpoint generation and visible progress. See [Memory retrieval](memory-retrieval.md) for local CPU and external API embeddings. Both vector modes remain optional; BM25 is available without an embedding service.
