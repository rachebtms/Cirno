# Configuration

`cirno --port 8000` starts the complete service and Web interface in the foreground. Configure a connection in Settings → Providers and add its models in Settings → Models. An instance stores configuration in `~/.cirno/config.json`; select another instance root with `cirno --home /path/to/instance`.

## Install from a checkout

Requires Python 3.11+ and Node.js 24. From the repository root:

```sh
npm --prefix sources/cirno-web ci
npm --prefix sources/cirno-web run build
python -m pip install -e sources/cirno-memory -e sources/cirno-usage -e sources/cirno-vault -e sources/cirno-core -e sources/cirno-server -e .
cirno --port 8000
```

The initial local launch creates the default configuration automatically. Open `http://localhost:8000`, register the instance owner, choose a theme and light/dark mode, and configure a provider and model. Theme choices synchronize with Settings and other devices. First-time setup takes place in the browser. Starting the first chat wakes the Router for a short introduction; it asks about its identity, your preferred form of address and whatever background you wish to share. You can skip model setup and introduce yourself later. New instances have no selected model: connect a provider, create a model preset, and select it before chatting. Incomplete setup returns a configuration message without contacting a model service or retrying. Web search defaults to DuckDuckGo and does not require a search API key. Existing instances retain their previous authentication settings. For a server deployment, see [Docker](docker.md).

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

- Providers: connections, credentials and optional upstream balance queries.
- Models: named presets, call order, context-window capacity and generation parameters.
- Appearance, Text & reading, Execution display: paired color themes, language, text size, code wrapping and independent brief/detailed reasoning and tool steps. These owner preferences are stored by the service and synchronized across connected devices.
- Browser notifications: per-device browser permission, synchronized sound settings and Inbox category mutes.
- Memory library, Context compaction, Dream consolidation, Memory retrieval: separate pages for stored knowledge, context thresholds, background consolidation and optional embeddings.
- Personality: separate Router and Worker personalities, shared user preferences and agent instructions.
- Agent heartbeat: periodic checks of `HEARTBEAT.md` and wakeups in the Router, separate from service health checks.
- Conversation coordination: concurrent subagents and the per-source outgoing cross-conversation message limit.
- Time & region: automatic or manually selected timezone.
- Goals & execution: default workspace, continuation and execution limits.
- AI approvals: independent review model, review timeout and the switch for automatic review.
- Tools & CLI Apps, Shell execution, Skills: tool availability, shell settings and skill management. Skills separates Installed, Discover and Validation & history. Marketplace and trend failures remain visible alongside usable results.
- Web search and MCP: search services and external tool connections.
- Nodes: enroll SSH credentials from Credentials, test connections, execute remote commands and manage persistent jobs. SSH authentication and Agent visibility are edited in Credentials.
- Telegram: personal account binding and server-side notification preferences. Channel setup configures the Telegram bot token and Web transport.
- Backup & restore: complete instance archives, optional extra directories and import preview.
- Account, Network & retries, Permissions, Server: network policy, access controls and service settings.

The **Add MCP server** panel sits above the MCP catalog, with custom connection and JSON import actions. Custom MCP servers can be edited from **MCP → Manage → Connection → Edit MCP configuration**. The JSON editor loads the saved configuration, including arguments, environment variables, request headers, tool scope and timeouts. Saving updates the same server and reloads its connection. JSON import and configuration editors support indentation with **Format JSON**; invalid JSON is shown as an error without discarding the draft.

See [Home and workspaces](home-and-workspaces.md) for file ownership and [memory](architecture/memory.md) for retrieval and maintenance behavior.

## Channels and remote browsers

Only Telegram and Web (WebSocket) channels are bundled. Authenticated users can install optional support and manage Skills from local or remote browsers, including behind a reverse proxy. Enable and configure them under Settings → Channel setup. Changes save when you finish editing; Enter saves credentials without enabling the channel. Failed saves keep the draft open. Checking a connection does not enable it.

For Telegram, supply a bot token in Channel setup. In Settings → Telegram, generate a PIN and send `/bind <PIN>` to your bot in a private chat. The eight-digit PIN expires after two minutes and can be used once. Pairing checks and PIN renewal run while the page is visible; they pause in the background. A failed check or renewal shows the error and a retry control. Refresh PIN invalidates the previous code; Cancel revokes it. A bound account is the only Telegram account admitted to Cirno; group chats, group commands and group callbacks are ignored. Disconnect revokes the binding and any outstanding PIN. Connection errors appear in channel status.

Telegram private input and Heartbeat use the dedicated Router conversation. Router replies can be mirrored to the bound account, including proactive replies originating in the browser or background work. Inbox Actions, Reports and System notifications use independent server-side switches; browser notification preferences synchronize with the owner profile, while notification permission must be granted separately in each browser. Ordinary replies are not added to Inbox. Pending Inbox notifications enter the existing durable delivery outbox, so a restart does not discard an admitted notification. Notifications are rechecked against the current binding before sending. To include an action button, set the Web UI address to one reachable from your phone; the button opens the corresponding Inbox category and conversation. Unanswered questions include their suggested answers in the Telegram notification. Answer and approve in the authenticated Web UI. For Web, configure the listening address, port, authentication, optional public WebSocket address and TLS certificate paths. A remote browser uses the Cirno server and needs no Cirno client installation.

Authenticated remote sessions can select Full Access. It applies to files and commands on the server host. Stop a running conversation before changing its access mode. Use authentication and the deployment's TLS or reverse-proxy configuration when exposing a server outside the local machine.

Permissions → Default access sets the initial permission for a conversation.
**Use tool policy** follows **Workspace restriction**: enabled confines files and
commands to the working directory; disabled allows Full Access. A conversation's
saved access choice takes precedence over this default.

## Providers, models and balances

Settings → Providers manages connections, credentials and optional balance queries. Settings → Models manages model presets and their call order. A provider can serve several model presets.

OpenAI Codex and GitHub Copilot browser sign-ins are stored in `state/providers/<provider-id>/`. They are included in instance backups. New instances start signed out; another application's CLI login does not sign them in automatically. The 0.1.6 importer copies existing SDK login files into this directory.

Sign-in polling and pasted authorization responses share one completion queue.
A failed request stays visible with Retry. Closing sign-in cancels its server
flow; if cancellation fails, the dialog stays open for retry. A cleanup failure
after leaving Settings appears as a persistent notification with Retry and Close.

Each provider and model has a stable ID, separate from its display name. Newly created entries receive generated IDs; built-in providers use IDs such as `deepseek`. Configuration dictionary keys are IDs. Model tools and conversation selections reference model IDs, so renaming a model leaves active conversations, fallback order and Dream selections unchanged. The upstream model identifier is a separate field, such as `deepseek-chat`.

Balance queries are disabled until configured. Set a complete balance endpoint and select DeepSeek's balance format or a custom JSON response with a JSON Pointer to the amount (for example `/data/balance`) and currency. The endpoint may use a different host from the model API. A separate balance API key is optional; leaving it blank uses the provider key. Refresh queries manually from the provider's balance panel. Balance settings do not change model routing or invalidate its runtime cache.

## Idle context compaction

Settings → Context compaction configures inactivity and two percentages of the active model's context window. Defaults are 15 minutes of inactivity, a 20% trigger and 5% recent-context retention. Idle compaction requires both inactivity and the usage trigger. A zero timeout or trigger disables it. Model preset advanced options can override either percentage; an empty value inherits the global value. Set each model's context-window capacity correctly for meaningful percentages.

Retention must be below a nonzero trigger. Compaction summarizes older context while retaining complete recent turns and paired tool calls/results within its budget. Counts are estimates until a subsequent provider request reports actual usage. Context-window pressure during execution is a separate compaction trigger.

## Projects and conversations

Create projects in the Conversations tab. A project has an independent ID, name, optional description and optional default working directory; two projects may use the same directory. Use the project header's + button to create a conversation within it. Conversation menus move conversations into or out of projects. The project menu opens an editor for its name and default directory, or confirms deletion. Failed writes keep their editor or confirmation open. Deleting a project detaches its conversations while preserving history and working files.

The `@name` beside a conversation is a display alias. Tools accept its stable ID or current alias; saved references use the ID. The Router is the dedicated coordination conversation; ordinary conversations retain execution tools and streamed replies. Both can create delegated conversations, send coordination messages and inspect other conversations through their tools. Only the Router receives `user.message` for visible reply delivery. See [Goals and coordination](goals-and-dream.md).

First-use introduction requests keep one delivery identity across retries and
restart recovery. Already consumed requests do not start another introduction;
when Home `BOOTSTRAP.md` is empty, startup retires leftover introduction requests
from older releases. Existing conversation history and other queued messages stay
in place.

## Additional system prompts

Settings → Personality provides three automatically saved text fields:

- **Shared additional system prompt** applies to both Router and Worker.
- **Router additional system prompt** applies only to the Router.
- **Worker additional system prompt** applies to ordinary Workers and their transient subagents.

Each field accepts up to 32,000 characters. Clear a field to remove its addition. The shared field initially contains the owner's unlimited-token effort instruction; the two role-specific fields start empty. This instruction requests thorough work and does not alter provider billing or model limits.

Changes apply to the next turn without restarting. A running turn keeps its captured prompt, including during compaction. Shared additions precede the role-specific addition, after the built-in instructions and profile context. They customize behavior within the Harness contracts: role permissions, Router delegation and execution budgets remain enforced. Internal Dream and heartbeat decision requests do not receive these conversation additions.

The corresponding configuration keys are `agents.defaults.system_prompts.shared`, `agents.defaults.system_prompts.router` and `agents.defaults.system_prompts.worker`. The same settings page also edits `SOUL.md`, `WORKER.md` and `USER.md`; those profile files remain separate from these additions.

## Router heartbeat pause

The Router conversation header includes **Pause heartbeat** / **Resume heartbeat**. Pause takes effect without a service restart and persists across restarts and browser sessions. It prevents new scheduled heartbeats and retires queued heartbeat inputs before model execution. A turn already running can finish. Owner messages, worker reports and separate automations keep their normal behavior. The global Heartbeat switch and interval remain in Settings; disabling that switch also disables the header control.

## Command duration

Settings → Shell execution separates the default command duration from **Maximum requested command duration**. Zero in the default means no time limit for commands without an explicit duration. Zero in the maximum removes the ceiling on requested durations, and allows an explicit zero for no time limit. A positive maximum still restricts explicit model requests to 1 through that maximum. These values survive automatic saves and reloads.

## Nodes

Settings → Nodes manages SSH connections, host fingerprints, direct commands and persistent jobs. Supply host, port, SSH username, remote working directory and either key or password authentication. A key path refers to a file on the server. A blank password while editing preserves the saved password. SSH credentials are encrypted in the credential vault and omitted from connection listings; Node enrollment and job tracking use instance state. Saved host keys or the server’s `known_hosts` verify the server; compare scanned fingerprints before saving them.

SSH connection details and Agent visibility live in **Credentials**. Enrollment in **Nodes** is optional. The shared SSH startup form stores the remote working directory, an optional initialization script path and environment variables such as `CUDA_VISIBLE_DEVICES=2`. Variables are exported, the shell changes directory, and the initialization script is sourced in that same Bash shell before the command. `~/` resolves on the remote host. A failing directory or initialization step stops execution and reports its error. Direct commands, new interactive Terminals and submitted jobs share this setup; inspecting/stopping jobs does not rerun the initialization script. Updating settings does not retroactively change an already-open Terminal.

Execute command runs a command and returns output without creating a job. The `nodes` tool namespace also lists connections, transfers files and starts, inspects or stops persistent jobs. Job output, PID and exit status stay on the remote host; tracking records stay in `state/instance.sqlite3`. No remote Cirno daemon or client is installed. Remote execution requires Bash and OpenSSH; persistent jobs also require `setsid`. An uncertain submission exposes its job ID for inspection before resubmitting.

## Service lifecycle

Settings retains Restart. There is no in-app upgrade platform or terminal configuration wizard. The CLI Apps catalog remains available for installing command-line integrations. Source installations upgrade by updating the checkout, rebuilding the browser assets and reinstalling the package; container installations rebuild or pull a published image.

## Account password

Settings → Account shows the registered owner and changes the browser-login password. Enter the current password, a new password and confirmation. The same rules apply as registration: at least ten characters, including an uppercase letter and a symbol. Successful changes keep the current browser signed in, revoke other browser sessions, invalidate server access tokens and reconnect Web UI sockets. Other browsers must sign in again. Password hashes and sessions live in `state/webui-auth.sqlite3`; passwords are not saved in `config.json`. Signing out revokes that browser session’s API and unused connection tokens and closes its live sockets, including attachment and backup-transfer capabilities. Other logged-in devices remain connected. Shared-token authentication has no registered browser account and continues to use the existing server authentication settings.

## Conversation controls and access review

Settings → Goals & execution configures the default workspace, continuation text and its visibility. The workspace setting (`agents.defaults.workspace`) accepts an absolute server path, including `~/…`. Restart when prompted to apply it to new conversations. Saving this setting does not move existing files or change existing conversations' working directories; projects can still supply their own default directory. A saved conversation continues to show its working directory as a locked selector. Conversation storage is instance-wide and remains available after changing the default workspace and restarting.

Stop preserves context. An interrupted conversation shows Continue in the composer’s primary action button while the input is empty; typing changes the button back to Send. Continue or `/resume` starts another model request from saved progress. Recovery failures remain visible as inline text, without a separate recovery action panel. New conversation drafts accept `/temporary on|off`, `/ptc on|off` and `/model <preset>`. Creation-only commands are omitted from established conversations' command menus. `/access default|review|full` selects the permission mode. Model display names are unique ignoring case. `/model` accepts a model ID or an unambiguous display name; tools use model IDs.

AI review keeps Default restrictions and reviews blocked operations independently of Cirno memory. Settings → AI approvals selects a saved model preset (or the conversation model), sets a 1–300 second review timeout, and enables or disables automatic review. These settings live under `agents.defaults.approval` as `enabled`, `modelOverride` and `timeoutSeconds`. Disabling review sends blocked operations to the owner for approval. Timeouts, unavailable review models and uncertain cases also appear in Inbox → Actions. Each approval covers one exact operation; it does not grant Full Access. AI can make unsafe decisions, so this mode displays an explicit warning. See [operation review](architecture/access-review.md).

Message action buttons and local timestamps remain visible below each message on desktop and mobile. Copy is directly available; edit is available on idle human messages and branch on completed assistant answers. Completed activity keeps a direct **Worked…** disclosure above the answer, without an action menu. Context changes do not undo previous file edits, commands or external actions; tool history triggers a warning. Editing replaces the original message bubble with a multiline input and Cancel / Save and send controls, retaining its attachments. Enter adds a line; Ctrl/Cmd+Enter sends and Escape cancels. The revised request replaces later conversation context. A failed save keeps the draft and shows the error in place. Switching conversations closes the editor. `/clear` resets only the fixed Router context through its dedicated control.

## Mobile keyboard, reconnection and refresh

The application fits the visual viewport on touch devices when the on-screen keyboard opens. Login and registration forms scroll within the available height; chat composers move above the keyboard while retaining their draft and focus. Touch text fields use at least 16px text to avoid focus-triggered zoom. Manual pinch zoom remains available.


Returning to the foreground checks the WebSocket connection and reloads the server's conversation state, including reasoning and tool activity missed while the browser was suspended. A stale connection reconnects through the normal authenticated path. The top-right refresh button reloads the page in desktop browsers and installed mobile Web apps, including iPhone Home Screen apps. Reloading the page does not stop the server's task or send the previous prompt again.

## Long tasks and embeddings

See [Model context and long-running work](model-context.md) for per-model reasoning replay, active/idle compaction, checkpoint generation and visible progress. See [Memory retrieval](memory-retrieval.md) for local CPU and external API embeddings. Both vector modes remain optional; BM25 is available without an embedding service.

## Browser file uploads

Settings → Server → File uploads controls the per-file image/document limit, per-video limit, and combined image/document size per message. Values are in MiB (1,048,576 bytes). Defaults are 6, 20 and 24 MiB respectively; video has its own allowance of one video per message. Local file references do not consume the upload byte allowance. Files are streamed to disk, and staging capacity accommodates the configured batch size.

These settings are stored under `server.uploads` as `maxFileMb`, `maxVideoMb` and `maxTotalMb`. Restart the service and refresh the browser to apply them. A reverse proxy's request-body limits must also permit the intended upload size; increasing Cirno's limits does not change proxy configuration.

## Usage chart details

Click or tap an Overview or Usage chart bar to keep its details open. Moving the pointer away does not dismiss them. Click the same bar again, click outside the details, or press Escape to close them. Model legend entries use the same interaction.

The Launcher reuses Conversations, Credentials, Inbox, Automations, and Settings.
Terminal, Files, Browser, and Trace open independent tabs. Opening the same file
again activates its existing editor; its preview has a separate tab. Drag tabs
or Launcher items to reorder them; on touch screens, hold an item before dragging.
Alt+Arrow keys also reorder focused items. Launcher order is saved on the server
and shared across devices. Desktop Split view keeps two surfaces visible with a
resizable divider. Narrow screens show the selected surface without disposing
its other tabs. Conversation groups retain their own multi-conversation layouts.

A tool's completion updates its first activity row even when its reply arrives
between the start and completion. Separate invocations retain separate records.

During first registration, choose the Router’s display @name (default `@cirno`).
Names use 3–32 lowercase letters, digits or underscores and start with a letter.
Change the name under Settings → Account. Names are unique across conversations;
renaming preserves the immutable conversation ID, history, memory sources and
running task links. Historical prose remains unchanged. Login and password changes
preserve the current name.

Trace’s download action saves a snapshot of the whole recording as ZIP, including events outside the current page and filters, API input messages, tool definitions and responses. Recording continues during export. The archive contains a manifest, event/request JSONL indexes and content-addressed JSON blobs, so repeated long-context prefixes are stored once. The inspector’s copy action copies the JSON currently displayed in its selected tab; load more messages first when copying a paged message list. Clearing or closing a recording does not delete a downloaded archive.
