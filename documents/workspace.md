# Tabbed workspace

Cirno 0.2.14 uses one workspace for conversations and owner-operated tools. The Launcher appears on the left on desktop and along the bottom on narrow screens. On touch layouts, the top tab strip and Launcher temporarily hide while the software keyboard is open, then return when it closes. Both layouts offer the same destinations; scroll the Launcher when space is limited. Settings and New conversation stay within reach at its end.

## Tabs

- Selecting a conversation opens or selects its tab. Several conversations can stay open while their runs continue on the server. Desktop split groups each have their own tab bar; narrow screens display one selected page.
- Conversations opens a separate catalog of ordinary conversations and explicit Projects. It supports search, project assignment, creation, renaming, pinning, archiving and deletion. Sort by recent updates, creation time, title or saved order. Select conversations across Projects for a single archive or delete action; Shift-click selects a range. On narrow screens, project assignment is available in each conversation’s actions menu so the title keeps its space. Conversation actions are always visible and also open on right-click. Renaming returns keyboard focus to the row after confirmation. The Router and utility pages are excluded. Deleting a Project keeps its conversations and files. The Router can use `projects.*` tools to manage the same catalog.
- Files opens an independent directory browser. Opening a file creates a separate editor or viewer tab, retaining the browser's directory. Text and Markdown are editable; images and supported browser video formats have dedicated viewers. Open preview tab shows Markdown from the editor's current draft, including unsaved edits. Saving checks the file revision and reports conflicts. Closing an unsaved editor asks whether to discard its changes. Preview rendering is extensible through the file-preview registry.
- Terminal opens an interactive local shell or an OpenSSH connection to a configured Node. Choose the server, then Connect. Each terminal is independent; multiple terminal tabs are supported. Closing a connected terminal stops the local shell or SSH connection. After refreshing the browser, Connect in the restored tab reattaches its existing terminal while the server is still running; its bounded recent output is replayed. Detached remote processes can survive that connection. Terminals require a POSIX server (Linux or macOS), and running shells end when that server restarts.
- Browser embeds an HTTP(S) page in a sandbox. Some sites forbid framing or require browser capabilities that the sandbox does not provide. The address bar has an external-open action for these sites. This is not a browser automation session or a server-side browsing proxy.
- Settings keeps all categories inside its tab. Selecting Settings reuses its existing tab. Leaving a modified settings surface follows its save/discard guard.
- Trace starts a temporary developer recording across conversations: user and model messages, reasoning, tool calls, compaction, file changes, lifecycle events and provider requests. Credentials manages encrypted personal records. Both have Launcher buttons on desktop and mobile.

Conversations, Credentials, Inbox, Automations and Settings each use one tab.
Terminal, Files, Browser and Trace allow independent tabs. Reopening the same file
selects its existing editor; a preview uses its own tab. Feature modules declare
this policy through the workspace registry.

Selecting a destination reveals its tab if it is clipped or offscreen. A fully visible tab does not move the strip, and each split group scrolls independently.

Drag tabs and Launcher items to reorder them. On a touch screen, hold the item
before dragging; a normal swipe still scrolls the Launcher. Alt+Arrow keys move
a focused item. Launcher order synchronizes through server-side owner preferences.
On desktop, Split view opens a second tab group with its own bar, initially empty.
Drag a tab between bars or use Move to other tab group. Each group retains its
selected page; drag the divider or use its arrow keys to resize. All tabs can be
closed without creating another conversation. An empty group stays open until
Single view merges the groups. Narrow screens combine the tabs into one bar and
show one selected page; returning to desktop restores group membership, both
selected pages and divider position. Moving tabs or resizing does not remount
their editors, terminals or chat composers.

Closing a conversation tab does not stop or delete its conversation. Closing a file tab discards only unsaved browser edits after confirmation; it does not undo previously saved files. Closing a browser tab releases its embedded page. Inactive custom tabs are loaded only after they are selected for the first time. Tab destinations are saved in this browser; unsaved editor text and terminal output are not stored in that tab list. Temporary conversation destinations are excluded from browser tab persistence.

Signed attachment downloads stream in 64 KiB chunks on the Web UI listener, including full-file and range requests. Each download retains its opened file snapshot; atomic file replacement does not mix old and new content. Local attachment URLs recheck the conversation’s current workspace permissions on each request.

A working-directory refresh failure keeps the last loaded directories and displays the error with Retry. Reconnecting refreshes that catalog without letting an older request replace a newer result.

Appearance, reading, execution display and notification preferences synchronize with the server independently of service configuration loading.

The Router has ordinary execution tools as well as delegation and supervision tools. A small task must fit fewer than ten ordinary tool calls and ten seconds of cumulative tool execution in one run; model waiting time is excluded. Brief CPU/GPU checks, one-file inspection and a simple lookup can qualify. Paper analysis, research, development, debugging, experiments and tasks of uncertain size must start in a durable Worker before substantive work. The runtime enforces the direct-work budget across native and PTC calls; coordination and user replies remain available after it is exhausted. The Router cannot launch private transient subagents to bypass Workers. Separate `user.message` calls remain separate chat bubbles; ordinary conversations keep their existing prose layout. The Router reads `SOUL.md`, ordinary conversations read `WORKER.md`, and both share memory and owner preferences.

## Event and request inspection

Opening a Trace tab starts a fresh recording of subsequent events; it does not import earlier conversation history. Each tab has independent Record/Pause and Clear controls. Pausing skips new events while preserving recorded data; results can still settle for requests that started before the pause. Clear discards the recording and its request snapshots, preserving the current recording/paused state. Closing the tab deletes its recording. Conversation history is unaffected.

The dense table follows capture order, newest first. Event-type and source-conversation filters apply to the entire recording before pagination; the text filter applies to the displayed page. Select a row to inspect raw data, or use the arrow keys to move between rows. Desktop displays the inspector alongside the table, while narrow screens place it below. The newest page refreshes while the tab is active. Older and Newer navigate 100-event pages. Full event bodies load only after selection; request messages load 10 at a time.

Request rows capture the messages supplied at the provider boundary, including system instructions, runtime context, previous tool observations, tool definitions and the returned response. Provider transformations, internal retries and reasoning unavailable through the API are outside this view. Temporary conversations are excluded.

Recordings use temporary server storage, outside the instance volume and backups, with content-addressed request bodies to share repeated messages. Server shutdown removes them; Refresh in an existing tab starts a new empty recording after a restart. At most eight recordings can be open; each pauses at 50,000 events or 64 MiB of storage (a final request or response can exceed that size). Clear a full recording before restarting it. A temporary-storage failure stops the affected recording and reports an error without interrupting the agent.

## Credentials

`state/credentials/vault.sqlite3` stores encrypted values; `state/credentials/vault.key` holds its encryption key with owner-only file permissions. Keep both inside the instance volume. A full-instance backup contains both, so anyone able to read that backup can recover the values. Encryption at rest does not protect against an attacker controlling the server account. An agent with unrestricted shell/file access can also read the key; this vault is not an isolation boundary from Full Access.

Records support account/password values, long text, personal identifiers, tokens or activation codes, and SSH connections. SSH records hold the host, port, username, password or server-side key path, and optional host keys. Passwords stay concealed until explicitly revealed. Switching away clears revealed, unchanged values. Unsaved edits stay in browser memory until saved or explicitly discarded. The `credentials.list` tool returns metadata only; `credentials.read(id=...)` explicitly retrieves one visible secret for the task. `credentials.store` and `credentials.delete` manage saved records. Read values enter model context; avoid repeating them in replies or saving them as memory. User-created records are private by default. Available to Agent controls whether credential tools can list, read secret values, update or delete a record; knowing a hidden ID does not grant access. Agent-created and Agent-updated records are visible to the Agent. Default approval applies to replacing or deleting visible records. Changing a label or visibility does not require revealing or replacing its saved secret. Credential tool values are redacted from tool activity, saved tool-call arguments, independent-review evidence and approval notices. Approval checks bind a digest of the complete operation so changing a concealed value invalidates its prior approval.

Add to SSH Nodes is a separate opt-in. It makes the connection selectable in remote terminals; Agent SSH tools additionally require Available to Agent. New SSH records do not enroll automatically. Settings → Nodes enrolls existing SSH credentials and manages direct commands and jobs. Removing a Node keeps its credential. Connection changes or removal wait until running or unconfirmed remote jobs are stopped or resolved. Hiding a credential blocks new Agent operations but does not terminate existing remote work. Refresh reloads records, and returning to the tab refreshes its catalog.

`nodes.execute` returns `stdout`, `stderr` and `exit_code`. A nonzero remote program exit, including 255, is a command result rather than an SSH transport error; do not add `|| true` merely to preserve its output. An independent shell receipt separates the remote status from the SSH process status. A complete receipt remains authoritative when the tunnel disconnects or the SSH process times out afterwards: the confirmed program result is returned with `connection_warning` and captured diagnostics. If no complete receipt arrived, the Agent receives `state: execution_unknown`, `resubmit_safe: false`, the SSH exit code and available partial output; a timeout is not proof that the command never ran. The command dialog displays the confirmed exit code/output or the explicit unconfirmed-outcome error. Commands are never automatically replayed.

Node SSH/SCP connections enable protocol keepalives every 15 seconds with three unanswered probes, retain a 15-second connection timeout, and allow three attempts during connection establishment. These [OpenSSH options](https://man.openbsd.org/ssh_config) help keep idle tunnels alive and detect unresponsive peers; they cannot prevent an FRP service from deliberately closing a connection. Internal read-only job-status queries may reconnect once after a transient network close/reset/refusal, within one total query deadline. Authentication and host-key failures are reported without this retry. Stop, submission and arbitrary execute commands are not replayed, and cancellation prevents a reconnect from starting. SSH diagnostics are kept separate from successful status-query payloads. WebUI requests for remote execution, connection tests and job operations allow enough time for the backend's 120-second operation deadline.

Use `nodes.start` for long jobs. Its saved ID and remote directory identify one launch. If the SSH acknowledgement is lost, Cirno saves `submission_unknown` and makes one read-only status check of that same job. A running or completed job is returned with the original submission diagnostic. If verification also fails or the outcome remains unknown, the response retains `id`, `submission_error`, `resubmit_safe: false` and a `next_action` pointing to `nodes.status` with that ID. Reconnect and inspect the existing job instead of starting another. A cancelled tool does not initiate a verification connection. The detached job publishes its own PID and atomically publishes its exit status, so those records do not depend on the original SSH connection staying open.

Settings → Nodes also provides automatically saved job-monitoring and retention settings. The server checks active and unconfirmed jobs every **60 seconds** by default, including when the page is closed, without calling an LLM. The interval is configurable; **0 disables automatic SSH checks**. Jobs on the same Node share bounded, serial status queries rather than opening a connection for every job. Automatic checks read status only; use **Read status** to fetch the complete available output. The visible page quietly refreshes its local catalog every five seconds and pauses these browser reads while hidden.

The list shows the last confirmed state, its check time and any check failure. A failed connection preserves the last known state instead of declaring completion or failure. A late background response or delayed launch acknowledgement cannot undo a newer terminal state. Monitoring stops with the Cirno server and resumes on its next launch; stopping the monitor does not stop remote jobs.

Finished local records and their cached output are retained for **30 days** by default, measured from the first confirmation of completion/failure/stopping rather than submission. This duration is editable; **0 retains records indefinitely**. Running, submitting and unconfirmed jobs are never expired, and remote files, logs and experiment results are not removed. Existing finished records without a completion timestamp begin their retention window when maintenance first observes them. Cleanup runs at most once per minute. Both settings persist in `state/instance.sqlite3` and apply without a restart; no additional persistent volume is required.

Visibility applies to the credential and Node tools; it does not isolate files from a Full Access Agent with server-account permissions.

Enter new secrets in the Credentials tab where possible. Secrets previously pasted into chat messages, model-generated prose or unrelated files remain in those places; storing a credential does not erase that earlier history.

## Large conversations and delivery

Conversation history initially loads a bounded latest page and fetches older pages when needed. A very long single execution is paged within its turn, preserving its original input while loading contiguous activity ranges; record and byte limits apply to every page. Tool activity details are also fetched on demand. Display-only state and subagent ownership queries exclude the large in-flight model checkpoint instead of repeatedly copying it during long runs.

Message navigation and search also load metadata pages on demand. The sidebar
markers and searchable list share a bounded cache, and selecting an older
message loads its transcript window while preserving the live conversation.

Ordinary text, attachments and owner shell messages all wait for a server acceptance receipt. A connection loss or unconfirmed send reports failure and retains the draft. A timed-out text message still waiting in the local offline queue is removed so reconnecting does not send an obsolete copy after a retry. An acceptance receipt confirms admission, not model completion.

Waiting messages show their attachment names as well as their text. Browser
storage failures display the error and Retry; an unsaved waiting message stays
in memory when switching conversation tabs. Keep the page open until saving
succeeds. A failed local removal after server acceptance retains an in-memory
record of that acceptance so reopening the tab cannot resend it. Retrying a
failed send clears its error after acceptance. Browser reloads keep restored
waiting messages paused until an explicit send.

The Router Agent cannot be forked. Ordinary conversations may branch from a
message. Router and Worker roles share conversation storage, memory and chat
components; their prompts, tool permissions and Fork capabilities are separate.
