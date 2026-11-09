# Source layout

Cirno has six Python distributions and one browser frontend. They run as one
service and share one release version; package boundaries do not create extra
processes or network services.

| Source | Installed package | Responsibility |
| --- | --- | --- |
| `sources/cirno-memory/` | `cirno_memory` (`cirno-memory`) | Evidence catalog, BM25/vector retrieval, revisions and Dream receipts |
| `sources/cirno-usage/` | `cirno_usage` (`cirno-usage`) | Content-free request accounting, context-local attribution and SQLite usage queries |
| `sources/cirno-vault/` | `cirno_vault` (`cirno-vault`) | Encrypted owner credentials and activity redaction |
| `sources/cirno-core/` | `cirno_core` (`cirno-core`) | Agent execution, Goals, PTC, providers, tools, memory coordination, Skills, durable sessions and domain services |
| `sources/cirno-server/` | `cirno_server` (`cirno-server`) | HTTP/WebSocket API, authentication, settings, Telegram, optional channel dependencies and service lifecycle |
| `sources/cirno/` | `cirno` (`cirno-ai`) | Small installation entry and public `from cirno import Cirno` SDK facade |
| `sources/cirno-web/` | Browser bundle | React/TypeScript interface, channel UI contributions and client transport contracts |

The dependency direction is `cirno-ai → cirno-server → cirno-core →
cirno-memory / cirno-usage / cirno-vault`. The three storage libraries accept
explicit paths and do not import the engine or server. The core must not import
the server or application facade. Shared history projection, turn
recovery and the Router session initializer belong to `core/session/`;
HTTP routes and channel adapters consume them. Offline version migrations live
in `server/maintenance/migrations/`; the runtime only reads the current layout. Package ownership is checked by
`sources/development/check_import_boundaries.py`.

Each Python distribution uses a standard `src/<package>/` layout. Core and
server modules live in `sources/cirno-core/src/cirno_core/` and
`sources/cirno-server/src/cirno_server/`. Their project roots contain packaging
metadata and tests. The `cirno` facade lives in `sources/cirno/src/cirno/` and
is built from the repository’s `pyproject.toml`. Editable installs, wheels and
static analysis resolve the same namespace without custom import finders.

## Core domains

- `command/builtin/`: command metadata, registration and domain handlers. Service status, session controls, model selection, history and Dream commands have separate owners. Transports consume the same catalog and router. Compaction delegates to the shared consolidator; Dream commands delegate to `memory/dream_run.py`.
- `agent/`: execution, Goals, PTC, subagents and tools. `tools/mcp/` separates transport ownership, capability discovery, schema conversion, result rendering and runtime reconnection. `tools/web/` separates page extraction, network policy and independent search-provider adapters. `tools/search/` owns file discovery, shared traversal, glob matching, bounded content paging, document sources and function-call schemas.
- `agent/subagents/`: private-task contracts and limits, task-owned resources, progress projection, capability construction, shared-runner execution, persisted child sessions and parent reports have separate owners. Capability construction requires the task-owned process manager; there is no spare shared process pool. The manager admits and controls tasks, settles their resources and publishes observations; it does not implement another model/tool loop.
- `agent/governance/`: model-message repair and merging, accepted-prefix/delta state, Token budgets, workspace-backed results, serialized prompt workers and checkpoint replacement. The request governor composes these owners; runner execution and token estimation use the same policy functions.
- `agent/context_usage.py`: shared saved-context measurement for Web UI and slash commands. It binds the target's workspace, privacy policy and runtime, then measures on a physical worker.
- `agent/conversation_models.py`: persisted model selection, default admission and canonical model-change notifications. Admitted turns retain their immutable runtime. `execution/command_execution.py` owns command dispatch and trusted user shell execution through the shared shell tool and workspace policy.
- `agent/runner/tool_results.py`: output preparation and completed-tool checkpoints. It uses the shared result policy in a physical worker and settles the checkpoint before propagating cancellation. A preparation failure records complete raw results and invalidates provider continuation state before reporting the error.
- `agent/tools/filesystem/`: shared path policy, streamed reads, bounded edit preparation, match selection and transactional patches. File creation and editing use the shared atomic writer and per-path transactions shared with the browser. Batches hold every target through validation, publication and rollback. Owned workers settle before cancellation returns.
- `agent/tools/shell/`: command-tool schema, preparation, authorization and shell-token parsing. Shell execution and ripgrep share preparation and session submission; ripgrep supplies its native argument vector through the approval contract.
- `processes/`: child environments, shell selection, launching, termination and Windows Job Object ownership. `sessions/` separates bounded output, status contracts, process supervision, admission and observation. Process infrastructure does not import Agent tools or conversation state. Each tool context owns a session manager shared by its execution capabilities.
- `memory/`: raw checkpoints, working-state preservation, Dream and compaction coordination. Retrieval and split SQLite stores belong to `cirno-memory`. `store.py` owns profile files and raw checkpoints; `journal.py` owns journal cursors and retention; `dream.py` owns batch tools and confirmations; `dream_run.py` owns batch execution, settlement, cursor advancement and cleanup for manual, idle and scheduled runs. One run owns each mutable Dream scope; preparation and durable cleanup use workers that settle before cancellation releases that scope. `archiver.py` generates checkpoints; `checkpoint_prompt.py` fits omitted reasoning evidence to the available request budget; `consolidation.py` coordinates session commits.
- `session/`: durable state, display history, recovery and turn ownership. `model.py` owns detached records, privacy policy and replay; `contracts.py` defines serialized payloads; `previews.py` projects catalog text. `branching.py` shares context-prefix projection between message edits and forks, while only public forks apply role eligibility. `manager.py` locates storage and exposes offline administration. Prompt navigation retains bounded previews and streaming answer digests; it does not keep every answer from a long turn or build a second full JSON copy for recovery matching. `state/` separates bounded operation scheduling and connection shutdown, detached record snapshots, access/policy, metadata projections, turn/checkpoint commits, display history, follow-up receipts, branches and lifecycle operations. Its facade composes these services around one shared repository and queue; it does not keep a second cache or persistence path.
- `session/recovery/`: checkpoint validation/restoration, pending follow-ups, state projection, delivery, actions and restart scanning. The coordinator composes these owners for runtime admission. Browser, Router and slash-command continuation share the same action owner; it serializes each conversation and settles accepted state/queue handoffs before releasing cancellation or maintenance admission.
- `session/webui_turns/`: activity projections, title generation, admitted model observation and routing. The event coordinator composes these owners; it does not own transport connections or storage. Input provenance has a required kind, and Router identity reads exclude model checkpoints.
- `providers/`: shared connection/response/stream timeout policy, request/response contracts, physical requests, usage accounting, retry execution, transports, authentication and catalogs. `chat_completions/` owns request policy, history conversion, cache markers, complete responses and incremental stream decoding. `bedrock/` separates request/message conversion, response/progress decoding, error mapping and ownership of blocking event streams.
- `config/`: separate agent, model, provider, server, channel and tool configuration models; `schema.py` composes and resolves the instance configuration.
- `security/`, `runtime/`, `bus/`: permissions, execution contracts and events.
- `observability/`: opt-in per-tab diagnostic recordings, disposable request snapshots and cancellation-safe request settlement. It does not own conversation history.
- `profile/`: server-owned presentation preferences and paired light/dark themes, stored independently of Agent memory.
- `skills/`: catalog discovery and reads, model context formatting, runtime metadata validation, script validation and retained history have separate owners. Settings and Agent execution consume the same runtime declaration.
- `nodes/`, `notifications/`, `storage/`: SSH operations, Inbox and instance records.
- `cron/`, `triggers/`, `apps/`, `sdk/`, `utils/`: scheduling, wakeups, CLI Apps, SDK and shared utilities. `apps/cli/` separates registry catalogs, package command execution, installed records, managed Skill paths, branding and artifact reporting. Updates to individual installation records are committed under a file lock.

The server's `lifecycle/` separates process ownership, instance paths, health
probes and their HTTP listener, MCP readiness, development-sidecar monitoring,
shutdown signals and resource settlement. Browser startup lives in
`cli/startup_browser.py`. One state directory has one process identity,
independent of workspace or configuration filename. Background service failures
use `notifications/service_errors.py` to record coalesced owner notices.
Shutdown closes remaining resources after a channel or resource fails, then
raises the collected failures. Failed cleanup does not report a successful exit.

WebSocket settings and trusted proxy validation live in
`channels/websocket/config.py`; importing configuration does not load the
transport runtime. Protocol handlers use the shared session identity validator.
`channels/configuration.py` resolves channel defaults and presentation overrides.
`factory.py` constructs adapters using the current configuration; `webui_binding.py`
owns Web UI service dependencies. `runtimes.py` owns instances, background tasks
and status; `activation.py` initializes and serializes settings changes. Startup
and hot reload use the same factory. The manager composes these owners and
coordinates service startup/shutdown.

`scheduling/agent_jobs.py` registers system maintenance and routes scheduled
execution. System payloads select handlers by fixed job ID; ordinary jobs keep
their conversation binding regardless of their display name. Idle and scheduled
Dream use the same handler. Heartbeat file reads run on workers and only a
missing file is skipped.

`channels/websocket/writers.py` owns ordered, bounded physical writes for each
connection and retirement of slow or failed peers. Connection cleanup settles
its writer before releasing subscriptions; closing a connection prevents queued
envelopes from registering it again. The channel composes this owner with its
listener and application router.

The server's `webui/commands/` separates connection routing, request delivery and
message intake. The request owner retains accepted mutations across reconnects;
the intake owner authorizes and commits turns before acknowledgement. Attachment
parsing and commits share one owner for ordered local and uploaded files.

The server's `webui/mcp/` separates identity/query contracts, preset field
materialization, manifests, catalog projection, custom configuration parsing,
persistence, settings actions and connection inspection. Inspection and runtime
reconnection share the same connection-close owner. Configuration failures reach
the caller; a failed inspection cleanup cannot report success.

The browser's `features/conversations/catalog/` owns the Conversations tab and
explicit Project sections. `features/conversations/shared/` owns selection,
batch actions and deletion contracts. The workbench owns tab selection, deletion
reconciliation and split layout across all panel types. Rows share rename, action-menu and
activity-state components. `features/conversations/projects/` owns project API
operations, scoped list reads and membership retries. Creating and updating use
one editor; deleting retains its confirmation until the write succeeds. Project
and conversation editors share mutation ownership and the IME Escape guard.
Catalog menus dismiss when their pane hides; editor drafts and failed
confirmations remain owned by their pane while their overlays are closed.

## Build and development

Install the local distributions together from the repository root:

```sh
python -m pip install -e sources/cirno-memory -e sources/cirno-usage -e sources/cirno-vault -e sources/cirno-core -e sources/cirno-server -e ".[dev]"
npm --prefix sources/cirno-web ci
npm --prefix sources/cirno-web run build
cirno
```

`cirno` starts the complete service in the foreground. Initial owner registration
and model configuration take place in the browser. There are no separate
`gateway`, `webui`, terminal agent or terminal onboarding commands. A supervisor
or Docker handles background execution.

Frontend compilation writes `build/webui/`. The server wheel embeds that bundle;
the core wheel embeds the current documentation in its documentation Skill.
Build hooks stage generated resources without writing them into the source tree.
Source distributions contain the resources needed to rebuild their own wheels.
The frontend build helpers load without importing the application, so isolated
package builds can run before runtime dependencies are installed.

Root `conftest.py` contains shared test fixtures. Core tests, server tests and
colocated channel tests run from the repository root and are excluded from
release wheels. Only Web (WebSocket) and personal Telegram channels are bundled.
Container files live at the repository root and in `sources/deployment/`.

Historical research, verification output and runtime samples belong in ignored
`references/`. Current English product guides live in `documents/`.

## Browser modules

`src/app/` composes authentication, navigation, conversation state and the workspace
shell. `src/features/settings/` owns the settings domain. `src/features/workbench/`
owns tab hosting and module composition; `files/`, `terminal/`, `browser/`,
`credentials/` and `trace/` own their respective panels. `src/features/composer/` owns drafting, attachments, queued guidance,
commands, mentions and sending. `src/features/preferences/` owns the synchronized
owner preference document, paired theme previews and palette editing. Shared page, confirmation and detail-overlay components live under `src/ui/`. Provider connections, login flows, balances and advanced controls live under `settings/providers/`; model presets, request overrides and call order live under `settings/models/`.

`src/features/channels/` owns discovery, connection-scoped filters, catalog cards,
setup and instance editors. Shared field values, validation, draft snapshots and
serialized operations live in `model/`; `ui/fields/` and `ui/setup/` render them.
Saving acknowledges only the submitted changes, preserving later edits. Draft
completion runs before switching editors or closing the overlay; a failed save
leaves the draft open. `channel-plugins/` defines schema, presentation and
panel/help/connect contribution contracts. Channel connection flows own their UI.

`src/features/messages/` separates human, assistant, system, incoming-session and
tool messages from their routing and formatting models. It owns persistent
message actions, delivery details, attachment grouping and inline editing.
Edit acknowledgements belong to their connection and conversation; replacing
either owner cannot reset another transcript. Mixed image, video and file
uploads use one attachment projection, which omits images already rendered in
the answer. Closed tool-message groups mount no event rows; large groups reveal
200 more events per action. Composer and message editors share textarea sizing
under `src/ui/fields/`.

The thread shell composes separate hooks for model selection, context usage, message editing, installed capability catalogs and file previews. New and existing conversations share one composer configuration.

`useAppViewport` owns the touch app's visual-viewport height and pan offset. Critical first-paint CSS in `index.html` uses the same `--app-viewport-height` variable; an unlayered fixed root height would override the interactive stylesheet's base layer. Keyboard regression checks load that shipping HTML, render the real account entry, and retain its styles when mounting controlled chat data. Model-provider fallback icons own their SVG dimensions and margins instead of inheriting HeroUI Button's generic icon spacing.

`src/features/telegram/` separates personal binding, expiring PIN pairing, notification
preferences and action links. Status reads are serialized per connection; accepted
writes invalidate older reads. Background pages suspend pairing checks. The server's
`webui/telegram_api.py` runs binding storage operations outside the event loop and
settles accepted writes before propagating cancellation.

`src/hooks/stream/useStreamBuffer.ts` owns pending stream batches, paint timers,
hidden-pane throttling and foreground refresh. The conversation hook uses its
queue, flush, snapshot and discard operations without owning its timer handles.
Input receipts and cross-conversation input projection live beside the shared
transcript reducer in `lib/thread-event-projection/inputs.ts`.

`src/components/thread/viewport/` owns history windows and reading anchors,
camera motion, keyboard insets, native input and the shared viewport surface.
The input controller keeps listeners attached through streaming updates and
retains a touch target until its gesture ends, even if history replaces that
target. Changing conversations resets the gesture. `ThreadViewport` composes
these owners and exposes prompt navigation.

`src/components/thread/activity/` separates activity disclosure, timeline rendering, CLI/MCP run projection, file-edit summaries and shared tool lifecycle states. Deferred trace reads are scoped to a conversation and require an explicit retry after failure.

`src/lib/contracts/` separates message, conversation, model, settings, file and
transport types by domain. `src/lib/api/` contains their HTTP and authenticated
mutation operations; its index defines the browser API’s public exports. Shared
request handling lives in `api/transport.ts`, and history validation lives beside
the history operations.

`src/lib/client-connection.ts` owns the browser socket and reconnect lifecycle.
Socket callbacks and authorization refreshes belong to one connection generation;
closing or replacing it revokes that generation. `cirno-client.ts` composes this
transport with delivery receipts, conversation subscriptions and the run ledger.
`client-mutations.ts` owns correlated mutation results, deadlines and exact-frame
replay. `client-chat-requests.ts` owns creation/fork correlation and removes expired
commands from the unsent queue. `client-listeners.ts` isolates and diagnoses UI
observer failures. `client-transcripts.ts` owns exclusive transcript delivery,
live observers and retained tails; an initial replay failure releases its own
subscription and retains unconsumed events for retry. Repeated acceptance waits for one turn ID share
the same send and deadline in `packages/client-events/delivery.ts`.

`webui/media/` separates signed reference projection, workspace authorization,
byte-range parsing and backpressured HTTP transfer. `channels/websocket/binary_http.py`
selects the HTTP parser for downloads and uploads on the same listener. Media
reads retain one opened snapshot and settle their worker before releasing it on
cancellation. The handshake parser handles WebSocket upgrades and ordinary API reads.

The server's `webui/settings/providers/` owns provider connections, balance configuration, authorization and connection payloads. `webui/settings/models/` owns presets, request overrides, upstream catalogs and model selection. Their transport coordinator is `settings/connections.py`; callers import domain helpers from their owners.

`channels/delivery/publish.py` admits outbound messages, records their history
and mirrors Router replies to the verified Telegram owner. Binding storage reads
run outside the event loop.

`channels/delivery/` separates bus dispatch, bounded per-destination queues,
retry admission, durable receipts, duplicate detection and Inbox forwarding.
Retry waits release send permits while preserving destination order. Durable
sends recheck the source session's generation and attachment scope using header
reads, without loading long model checkpoints. Inbox forwarding owns its event
subscription; ordinary replies do not create Inbox notices.
Both live replies and durable sends use `events.send_event` through the
`BaseChannel` interface, including the `merge_next` stream boundary flag.
Coalescing retains destination, stream identity and all message metadata;
changes in turn, context generation or response source remain separate events.

The Telegram channel separates the application connection, API calls, rich-message
capability detection, personal-account delivery policy, typing workers and stream
state. `writer.py` owns confirmed chunk progress and uncertain delivery;
`streams.py`, `overflow.py` and `finalizer.py` share it for previews and completed
replies. `delivery.py` owns text, attachments and action rendering;
`compaction.py` edits one status notice per operation. The runtime still coordinates
startup, polling and inbound workers.

The server's `webui/http/` package separates transport admission from controllers
for bootstrap, sessions, history, recovery, automation, files, Skills and assets.
Public service endpoints use the [major API namespace](api.md).
HTTP and temporary-chat file previews share one file policy. Temporary-chat
preview reads run off the event loop and stay outside the mutation replay cache.

## Execution and history modules

`agent/execution/` separates message dispatch, pending input injection, context
preparation, model execution, persistence, worker reports and lifecycle ownership.
`execution/cancellation.py` owns stop settlement for commands, supervisory controls
and session removal; it receives the owned registries and services explicitly.
`SessionDispatcher` owns pending inboxes; `SessionTurn` owns each input’s recovery,
lock, concurrency and cancellation lifetime. Restore failures use the normal stage
reporter, while intake/setup failures enter the same durable work-report service.
Shared diagnostic policy keeps content privacy consistent across these boundaries.
`session/transcript/` projects persisted records into messages, activity, recovery
state and bounded trace details. Runtime archives remain searchable after
compaction, restart and moving an instance directory. These services share the
canonical session store rather than loading separate copies of conversation history.

`session/transcript/prompts.py` builds the canonical prompt projection and recovery
matches; `prompt_directory.py` supplies bounded pages and search over that view.
The frontend's `features/prompt-history/` owns the shared sparse page cache,
revision changes and failed-read retry. The rail and search list consume that
same cache; `usePromptHistory` owns bounded transcript windows and live-input
merging. JSON object guards shared by API and browser persistence readers live
in `lib/record.ts`.

Source-checkout bundle builds share a process lock. An instance waiting for another build rechecks freshness before installing dependencies or writing assets.

## Frontend contribution interfaces

`src/features/workbench/` defines panel contracts and composes feature modules.
Files, terminals, browser views, credentials and trace recordings each declare
their icon, title, component and disposal behavior. The workspace owns tab
activation, unsaved-change guards and closing resources. Namespaced panel IDs
allow additional modules to use the same host.

`src/ui/layout/TabSurface.tsx` owns each tab's available width through
ResizeObserver and the named `cirno-tab` CSS container. Tab content uses
`useTabCompact` for structural choices and container queries for styles. Moving
a tab or resizing a split updates its layout without remounting its state.
Window queries control the launcher, split availability and device capabilities.
Fullscreen overlays use their own bounds; anchored dialogs keep the tab bounds.

`src/features/settings/` owns the section catalog, registry and lazily loaded
panels. Routing, launcher navigation and panel selection consume the same
identities. v0.2.0 composes built-in modules at build time. A general plugin
platform is deferred beyond this release. The panel, settings and tool registries
provide composition boundaries for that future work; v0.2.0 does not define a
public plugin SDK or add a dynamic frontend plugin host.

Browser history and workspace startup restore one canonical tab for each routed utility page. The workbench module separates tab/resource state (`model/`), its HeroUI tab bar, launcher and discard dialog (`ui/`), and the panel registry. `features/inbox/` owns the inbox feed, category routing and notice actions. `features/conversations/ConversationsPage.tsx` composes its native HeroUI menus, project and rename forms, catalog projection and bulk selection. Shared page layout and confirmation flows live under `src/ui/`. Retired workspace and inbox screen implementations are removed when their replacements are installed.


The composer separates its editor, attachments, queued messages, Goal details and toolbar under `features/composer/view/`. Model selection and provider icons live under `features/model-selection/`. The editor and its decoration layer share typography and block geometry to keep selection, IME composition and scrolling aligned.

Settings navigation and the content frame live under `features/settings/ui/`. `composition/` assembles typed section maps by domain and separates exit/save coordination from operation overlays. Pending completions can only execute the latest navigation intent for their mounted connection. Runtime configuration separates its schema, persistence controller and field renderers; all fields use the same automatic-save controller. Fields marked `saveOnBlur` commit when focus leaves their group, while other fields save after edits settle. Normal edits and pending saves never expose Save/Cancel actions; failed saves retain their draft and offer Retry/Cancel. A save response acknowledges its submitted values without clearing edits entered while the request was running. Unexpected completion errors use the native notice queue and retain the draft. Account settings separate credential operations from their form.

The web file feature separates directory requests, create-entry forms and document view state. Editor and preview tabs share the document store; tab disposal waits for a pending save and preserves the tab when that save fails.

Provider and model settings use separate setup controllers and native editor views.
Their `actions/` modules own preset editing, creation and ordering, provider writes,
and credential drafts. `providers/oauth/` owns authorization flows, serialized
polling and manual completion, cancellation and disposal notices. Model state
does not own authorization state. `ui/resources/useLifetime.ts` gives reads,
writes and authorization callbacks the same mounted-owner boundary.
`models/model/presetChanges.ts` supplies both dirty
state and changed-field updates. Draft initialization uses `modelDraft.ts`;
connection selection and token parsing use `modelValues.ts`. Request parameter
fields share one implementation. API preview failures remain visible with Retry;
closing advanced options waits for a successful save. Catalog input stays a draft
until selection or blur. Reasoning choices share catalog loading, error details and
retry; the localized Default label maps to an empty API value. Model settings tests are grouped by behavior, with shared
fixtures and native interaction helpers under `src/tests/helpers/`.

`settings/apps/` owns catalog projection, custom MCP forms and CLI installation views. `settings/mcp/` owns connection management and tool-scope drafts. Shared proxy fields serve both runtime settings and inline setup; configuration editors preserve drafts and reject stale reads after reopening. Externally controlled overlays use `Modal.Backdrop`; `Modal` owns flows with an actual trigger.

`features/automations/` separates schedule parsing, calendar entries, inspection,
editing, chat binding and recorded results. The task page and conversation task
dialog reuse these views and operations. Conversation task dialogs keep one modal
mounted while loading or changing views. Edits submit changed fields, preserving
exact intervals and drafts across background refreshes. Task polling cancels reads
when its surface closes and displays refresh errors alongside retained records.

`settings/web/` separates search-provider rules from credential and fetch-option presentation. It shares provider secret fields and settings edit completion; provider changes, explicit retries and blur commits use the same save action. Capability configuration commits pending edits before closing its overlay.

Global styles have one ordered import entry. `styles/global/` separates base tokens, typography utilities, thread controls, settings layout, navigation, directory loading and syntax highlighting. Component styles remain with their features.

`features/entry/` owns registration, account sign-in, access-secret entry and model onboarding. Its shared layout and password fields use the same native form primitives as Settings. Account requests and onboarding readiness have separate state owners; route-history updates and token-expiry calculations live outside the entry views.

`features/trace/` separates recording ownership, filtering/paging controls, event selection and detail inspection. Its dense native table provides keyboard selection; the inspector uses native tabs for request messages, responses, tool schemas and raw events. Recordings still belong to their workspace tab and are deleted when that tab closes. Launcher shortcut hints and keyboard dispatch share `lib/app-shortcuts.ts`.

`features/terminal/` separates host discovery, PTY ownership and rendering. Reconnection waits for the previous resource to close; visibility changes share one output reader. Palette updates preserve the PTY. `features/credentials/` separates metadata loading, SSH connection fields, visibility and enrollment from its editor and record list. SSH forms load redacted connection details; visibility edits retain concealed values. Late reveal responses cannot repopulate a hidden editor; modified drafts remain owned by their tab.

`settings/nodes/` owns SSH record editing, direct commands and retained job views. Requests share operation and metadata owners; failed writes keep their form drafts. `features/skills/` separates installed catalogs, marketplace search and trends, detail reads and mutations, and retained validation history. Native overlays keep failed installation and deletion actions reviewable. Read and write ownership helpers prevent stale responses from modifying another instance or selection. `settings/notifications/` separates browser permission and worker readiness from preference controls. Category and sound choices share the owner preference store.

The web memory feature owns search snapshots, independent status and maintenance requests, and a revision-pinned evidence inspector. Profile files load independently; editing reads content and revision together, and saving uses that opening’s revision. Shared request ownership, date inputs and error presentation live under `ui/`.

Workbench panel contributions declare `tabPolicy`: `single`, `multiple`, or a
resource identity function. Both opening and restoration use that policy, so
extensions use the same ownership rules as built-in panels. `useStripReorder`
owns pointer, touch-hold, and keyboard sorting; `useSplitLayout` owns desktop
surface placement without remounting panels. Routed pages share one route host. Each desktop group owns its tab bar and
selection across panel types; mobile combines the bars while retaining the
desktop layout. Owner preferences persist Launcher
order independently of per-browser tab restoration.

Activity coalescing runs before answer/activity segmentation. Invocation IDs and
turn identities select the original record; mixed transport batches are split
by invocation without moving unrelated calls or file activity. Hidden completion
contributions retain transcript counts for fork boundaries. Deferred trace rows
keep their references until their details are loaded.

The composer's `queue/` separates persistence, transport acceptance ownership and
attachment payload conversion. Storage failures are part of the queue snapshot;
failed writes retain its owner across unmounts and provide an explicit retry.
Send errors render directly from that snapshot instead of being copied into
another error state. Command catalogs, capability mention payloads, Goal
presentation and viewport geometry use separate modules.

Workspace metadata updates belong to their conversation ID. They update that
conversation's scope override without changing an unsent conversation's directory.
Selecting an existing tab also leaves the new-conversation draft scope intact.
The shared Hint uses React Aria's tooltip state for pointer movement after typing,
including triggers that also own a model menu; the library owns delay and dismissal.

Conversation catalog preferences have their own transport contract. They do not
store tab layouts. The workbench reconciles restored conversation tabs only after
a complete catalog read succeeds; partial caches and failed refreshes cannot
remove them. Deleting a conversation and closing a tab share group-local neighbor
selection, preserving other tabs' mounted editors and drafts.

`core/credentials/` owns credential access policy and SSH enrollment over `cirno-vault`. Nodes resolve their authentication there; the instance database retains jobs rather than a second connection store. Existing Node rows migrate into the vault before runtime writers start.
