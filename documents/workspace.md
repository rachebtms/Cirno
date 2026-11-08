# Tabbed workspace

Cirno 0.2.1 uses one workspace for conversations and owner-operated tools. The Launcher stays visible on the left on desktop and along the bottom on narrow screens. Both layouts offer the same destinations; scroll the Launcher when space is limited. Settings and New conversation stay within reach at its end.

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

The Router has the ordinary execution tools as well as delegation and supervision tools. Its role prompt favors direct execution for small checks and delegation for larger tasks. Separate `user.message` calls remain separate chat bubbles; ordinary conversations keep their existing prose layout. The Router reads `SOUL.md`, ordinary conversations read `WORKER.md`, and both share memory and owner preferences.

## Event and request inspection

Opening a Trace tab starts a fresh recording of subsequent events; it does not import earlier conversation history. Each tab has independent Record/Pause and Clear controls. Pausing skips new events while preserving recorded data; results can still settle for requests that started before the pause. Clear discards the recording and its request snapshots, preserving the current recording/paused state. Closing the tab deletes its recording. Conversation history is unaffected.

The dense table follows capture order, newest first. Event-type and source-conversation filters apply to the entire recording before pagination; the text filter applies to the displayed page. Select a row to inspect raw data, or use the arrow keys to move between rows. Desktop displays the inspector alongside the table, while narrow screens place it below. The newest page refreshes while the tab is active. Older and Newer navigate 100-event pages. Full event bodies load only after selection; request messages load 10 at a time.

Request rows capture the messages supplied at the provider boundary, including system instructions, runtime context, previous tool observations, tool definitions and the returned response. Provider transformations, internal retries and reasoning unavailable through the API are outside this view. Temporary conversations are excluded.

Recordings use temporary server storage, outside the instance volume and backups, with content-addressed request bodies to share repeated messages. Server shutdown removes them; Refresh in an existing tab starts a new empty recording after a restart. At most eight recordings can be open; each pauses at 50,000 events or 64 MiB of storage (a final request or response can exceed that size). Clear a full recording before restarting it. A temporary-storage failure stops the affected recording and reports an error without interrupting the agent.

## Credentials

`state/credentials/vault.sqlite3` stores encrypted values; `state/credentials/vault.key` holds its encryption key with owner-only file permissions. Keep both inside the instance volume. A full-instance backup contains both, so anyone able to read that backup can recover the values. Encryption at rest does not protect against an attacker controlling the server account. An agent with unrestricted shell/file access can also read the key; this vault is not an isolation boundary from Full Access.

Records support account/password values, long text, personal identifiers, tokens or activation codes, and SSH connections. SSH records hold the host, port, username, password or server-side key path, and optional host keys. Passwords stay concealed until explicitly revealed. Switching away clears revealed, unchanged values. Unsaved edits stay in browser memory until saved or explicitly discarded. The `credentials.list`, `credentials.store` and `credentials.delete` tools let the agent manage records without a plaintext read tool. User-created records are private by default. Available to Agent controls whether credential tools can list, update or delete a record; knowing a hidden ID does not grant access. Agent-created and Agent-updated records are visible to the Agent. Default approval applies to replacing or deleting visible records. Changing a label or visibility does not require revealing or replacing its saved secret. Credential tool values are redacted from tool activity, saved tool-call arguments, independent-review evidence and approval notices. Approval checks bind a digest of the complete operation so changing a concealed value invalidates its prior approval.

Add to SSH Nodes is a separate opt-in. It makes the connection selectable in remote terminals; Agent SSH tools additionally require Available to Agent. New SSH records do not enroll automatically. Settings → Nodes enrolls existing SSH credentials and manages direct commands and jobs. Removing a Node keeps its credential. Connection changes or removal wait until running or unconfirmed remote jobs are stopped or resolved. Hiding a credential blocks new Agent operations but does not terminate existing remote work. Refresh reloads records, and returning to the tab refreshes its catalog.

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
