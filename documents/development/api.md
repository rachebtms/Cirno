# API versions

All Cirno service endpoints use a major-version prefix. The current prefix is
`/v0/`. Cirno 0.2.21 still uses `/v0/`; a minor or patch release does not change
that prefix. A future Cirno 1.x API will use `/v1/`.

The v0 contract may change between releases. Update clients together with the
service. There are no aliases or redirects from the former unversioned or
`/api/` endpoints. Unsupported versions return HTTP 404, rather than the Web UI
HTML document.

## Endpoints and authentication

- `/v0/bootstrap`: authenticated browser bootstrap, including connection URLs,
  capabilities and owner presentation preferences.
- `/v0/connection`: connection capability probe.
- `/v0/auth/*`: owner registration, login, logout and password management.
- `/v0/ws`: default WebSocket endpoint for conversation events and authenticated
  commands. Bootstrap supplies the actual configured URL; clients should use it.
- `/v0/sessions/*`, `/v0/settings/*`, `/v0/workspaces/*` and `/v0/webui/*`:
  conversation, settings, file and navigation reads.
- `/v0/media/*`, `/v0/attachments/*` and `/v0/backups/*`: media and binary transfer
  endpoints, with their existing access checks and transfer capabilities.
- `/v0/mcp/oauth/callback`: MCP authorization callback. Existing external OAuth
  client registrations must use the new redirect URL.
- `/v0/health`: readiness on the separately configured health listener. Container
  checks and local service management use this path.

Live replies and completed streams resolve local Markdown media under the
conversation's project, matching thread-history replay. Stream history stores
source Markdown paths; signed media URLs are generated for the current server
instance when projecting a response. Unusable optional media references leave
the reply text intact. Invalid saved workspace policy returns an explicit 400
for thread and subagent-history projection instead of a default file-access
scope.

Versioning does not change access rules. Browser account changes use HTTP POST;
Web UI mutations use allowlisted actions over an authenticated WebSocket. Binary
uploads and downloads retain their dedicated authenticated transport.

`preferences.read` and `preferences.update` bind their respective read/write
operation; a conflicting `operation` payload returns 400. A read never writes
the supplied patch or increments the preference revision. Preference writes
accept an object patch and an optional non-negative integer `expected_revision`;
booleans and floating-point values are rejected. Invalid patches/operations
return 400 without changing storage, while stale valid revisions return 409.
An accepted database write finishes before request cancellation propagates.

`settings.network_safety.update` validates existing workspace preferences before
publishing its config and preference changes. It holds the shared in-process file
locks through snapshot, write and compensating rollback. Caught write or response
projection failures return a structured 500 after restoring attempted files;
failed restoration explicitly reports the files whose state may have changed.
New files from the rejected operation are removed during successful rollback.
Accepted network-safety and web-search operations retain ownership through
worker completion and restart-state bookkeeping even if the caller cancels.
Restart bookkeeping compares saved values after failed operations too, so an
incomplete rollback cannot hide an already-saved runtime change. Reverting the
network flag clears its baseline independently of live default-access changes.

Ordinary model/provider configuration mutations retain ownership of both the
serialized disk save and the runtime refresh on the event-loop thread. Their
route result bookkeeping, and runtime-config result bookkeeping, settle before
caller cancellation propagates. This policy excludes interactive OAuth flows and
does not add concurrent model calls. Home-profile writes likewise drain their
accepted file work; profile reads use atomic snapshots with the editor's existing
universal-newline revision format. Missing-file races retain missing-file/read
and revision-conflict/save behavior. Non-regular profile paths are rejected at
lookup. Channel integer fields reject fractional and boolean input; float fields
reject boolean and non-finite input before any configuration is saved.

Feature enable/disable and channel configuration, plus CLI install/update/
uninstall/test actions, retain accepted worker work, runtime application and
route restart bookkeeping through caller cancellation. Interactive channel
connectors and OAuth retain their own cancellation protocols. Optional feature
installers use the setup-owned subprocess runner, including its timeout and
process cleanup; this does not change the WebUI installer's 300-second timeout.
Raw channel toggles publish configuration atomically and hold the shared
in-process file transaction through read, modification and publication.

When a channel enable installs missing dependencies, the result includes
`last_action.dependencies_installed: true`. The service verifies availability,
saves the requested configuration without importing the new runtime, and marks
the channel `restart_pending`. Install-only actions also mark a pending restart
when they actually install dependencies. That marker lasts for the current
server process; subsequent enable/configure requests cannot activate the new
channel runtime, while disabling remains available. The browser offers the channel's
existing Restart control. This guarantee does not claim rollback of partial
package-manager changes after an installation failure.

Conversation creation commands (`new_chat`, `new_temporary_chat`, `fork_chat`)
accept a `request_id` of 1–128 ASCII letters, digits, `.`, `_`, `:` or `-`.
Creation replies and validation errors echo a supplied ID. The browser always
supplies one and settles only the matching request; ordinary subscription
acknowledgements remain separate events. Expired or disconnected creation
requests are removed from the browser's unsent queue. Accepted server operations
retain their own lifetime after a browser timeout.

Authenticated `webui_request` mutations retain one serialized frame, request ID
and deadline across reconnects. Size admission measures the UTF-8 bytes of that
same frame. A timeout ends its browser replay eligibility.

Custom WebSocket and optional connection-token endpoints must also live below
`/v0/`. A configured public WebSocket URL must match the configured endpoint.
Reverse proxies should forward this prefix and allow WebSocket upgrades. The
development server proxies `/v0/` HTTP requests to Cirno; the application socket
connects directly to the service.

The browser application and static assets remain at `/`. Hash navigation such as
`/#/settings` is not an API endpoint. URLs for external model providers, MCP
servers and marketplaces retain the versions defined by those services.

## Updating an existing configuration

The [0.1.6 importer](../migrations.md) converts configured WebSocket paths,
public URLs and token-issue paths to `/v0/` before channel configuration is
loaded. Update external clients, reverse-proxy path rules and OAuth redirect
registrations to match. New configuration must already use versioned paths;
the runtime does not register unversioned aliases.

## Conversation navigation

`GET /v0/sessions/{key}/webui-thread` includes an opaque `history_generation`
for persisted conversations. It stays stable when messages are appended or the
conversation is renamed, and changes when history is replaced by reset or edit.
An existing empty conversation returns an empty event list and its generation;
an absent conversation still returns HTTP 404. This identity is separate from
the response `revision` and ETag, which also change with content and query state.

`GET /v0/sessions/{key}/webui-thread/prompts` returns a bounded metadata page.
`limit` defaults to 64 and accepts 1–256; `offset` selects a zero-based position.
Omitting `offset` selects the latest page. `q` searches prompt previews without
loading conversation bodies. System control turns and model-switch commands are
excluded from this directory.

The response includes `prompts`, `offset`, `total` matching rows, `count` of all
directory rows, and a history `revision`. Each prompt has its original `index`,
stable `id` and transcript `cursor`; filtered results keep those original
positions. The same cursor selects a bounded transcript page. ETags include the
requested range and search term, so a validator for one page cannot validate
another page.

## Workbench terminals

Authenticated `workbench.action` calls use `terminal.write` for terminal input.
Writes to one terminal are serialized across browser connections so partial
writes preserve input order and own one readiness callback. Different terminals
remain independent. Closing a terminal wakes blocked writes with a closed-session
error and removes its readiness callback before releasing the descriptor. A late
writer cleanup cannot remove a new terminal's callback if the OS reuses that
descriptor.

## Model and provider identities

Model-catalog configuration failures return `not_configured` or
`missing_api_base` without submitting an HTTP request when required environment
references are missing. Transport, invalid-URL and response-format failures use
safe `status: "error"` messages without raw URLs, proxy credentials or keys.

OAuth catalog cache identities separate absent credentials, legacy tokens
without account IDs, and known accounts. Known-account access-token rotation
does not invalidate a fresh model list. Identity keys retain only digests of
account IDs or legacy access tokens; they do not contain the raw credential.
Owned catalog HTTP clients, the xAI OAuth HTTP helper and Responses HTTP/
WebSocket transports disable implicit environment proxy routing. External SDK
refresh and other interactive login flows have their own transport behavior.
Responses transport shutdown waits for accepted connection closes, including
through repeated cancellation; a pool-close error propagates after peer closes
settle. This changes cleanup ownership without adding concurrent model calls.

OpenAI-compatible client initialization owns its HTTP transport until the SDK
constructor succeeds. If construction fails, transport cleanup finishes before
another initialization attempt is admitted. Closing the SDK client and closing
all providers retained by a model runtime likewise settle accepted cleanup
before propagating caller cancellation. Runtime shutdown still reports peer
close failures together. Provider-level custom headers replace automatic
OpenAI-compatible headers case-insensitively; Anthropic HTTP clients disable
environment proxy routing for both direct and explicitly proxied requests.

Responses `error`/`response.failed` events and failed non-streaming responses
are projected through the owning adapter with bounded type/code metadata,
available HTTP status, retry timing and reported usage. The failure text does
not echo the upstream message or response output. Known rate-limit/server kinds
retain their public category without inventing an HTTP status; unknown failures
remain generic. Failed or cancelled response output cannot become a usable
continuation or executable tool batch. OpenAI-compatible Responses-to-Chat
compatibility fallback is restricted to requests that have not yet produced
text, reasoning or tool progress, including when no UI callbacks were supplied.

MCP tool-result rendering runs on an owned worker: image decoding and artifact
writes do not block the event loop, and cancellation drains an accepted render
before releasing the caller. Request context propagates to that worker. Render
failures stay outside remote retry/reconnect logic, preserving `isError` and
structured-result behavior without repeating completed remote operations.

MCP local `$ref` normalization visits schema-bearing keywords. `default`,
`examples`, `enum`, `const` and extension metadata remain detached instance data;
literal `$ref` fields inside them are not rewritten. Actual structural refs
still move into `$defs`, including recursive and escaped JSON Pointers.

A reconnect callback returning no replacement capability terminates recovery;
it does not authorize a retry against the old session. A replacement must retain
the wrapper kind, model-facing definition and side-effect/replay hints before
automatic replay. Definition comparison uses canonical JSON so booleans and
numbers remain distinct. A mismatch asks for an explicit call with the current
catalog. Calls without an explicit read-only/idempotent replay guarantee retain
their unconfirmed-outcome warning.

File tool observations retain structured failure status for ambiguous matches
and invalid selector combinations, including create-file calls. Patch dry-run
and built-in activity path resolution do not capture Skill versions. File
activity snapshots read at most the configured limit plus one sentinel byte,
and snapshot/diff/history work runs in owned file workers. Post-write history
failures return an explicit saved-content warning and retire every committed
file's read receipt; this is distinct from a rejected edit or a rolled-back
patch. File-edit activity continues using the existing editing/done/error event
format and bounded unified diff payload.

Ordinary write/edit publication errors explicitly distinguish an unconfirmed
outcome: contents may already have changed, so callers must read before
retrying. This also applies when a rename succeeds but persistence reporting
fails. `files.read` checks cancellation between Office extraction lines and PDF
pages. The page extractor closes its admitted PDF reader in a finalizer; a
current synchronous parser call is drained before Stop completes.

The Python `files.find` and `files.search` implementations use the same owned
file-worker cancellation boundary. PDF/XLSX search line iterators close the
admitted owner exactly once, even when closed before iteration. Text search
reads a replaceable atomic snapshot with one sentinel byte; observed growth
beyond the byte limit is an error rather than a successful partial scan.
Document errors in directory count searches do not contribute hidden partial
counts to the reported successful-file total.
After an owner cancels, a worker error observed during cleanup cannot replace
the original cancellation with a normal tool-error result.

`conversations.send` retains one accepted inbox/wakeup/rate/timeout operation
under the send lock until it settles, then propagates caller cancellation.
This prevents a persisted request from missing its live wakeup or optional
reply-timeout registration merely because its sender stopped. Conversation
search/read excerpts map case-folded match offsets back to original character
positions; compact search excerpts also normalize query whitespace so a
cross-line literal match remains present in its own preview.

Goal self-updates and Router supervisory waits share deadline validation.
An unrepresentable delay returns a tool error before supervisory controls stop
current work. `wait`/`continue` distinguish an omitted recap (preserve) from an
explicit empty string (clear). Task-subagent tool construction copies the full
configured settings deeply before applying its workspace restriction, retaining
capability switches and network policy without sharing nested parent models.

Goal-change events include their committed session generation. The WebUI
coordinator rejects retired generations and publishes current saved metadata,
rather than an older event snapshot. Legacy events without a generation also
read current metadata and cannot recreate a deleted session.

Task-subagent creation atomically stores `parent_session_generation` alongside
`parent_session_key`. New completion inputs and `SubagentTaskChanged` events
forward that generation; dispatch and WebUI coordination reject replacements.
Task status/list/history ownership also checks the binding, including after
cache disposal. Normal parent metadata revisions do not retire children, and
non-persistent parents are checked against their in-memory identity. Old child
records are retained; records predating generation binding retain legacy
parent-key ownership until a reset or message edit atomically sets
`child_session_generation_required` on the replacement parent. Old unbound
children then become unavailable from that replacement, without record deletion.

Task observations also hold a private `child_generation` write binding. It is
set at child creation or an explicit status read and is excluded from stored
task DTOs and public/model-facing status. Status saves use the existing session
generation fence; unbound writes are rejected. Runtime cache/control/history
reads and completion reports respect the same child identity. New queued
reports carry `subagent_child_generation` in internal metadata, so a child
replaced after publication cannot deliver its former result. Startup recovery
uses its captured child generation too. Transient children use their in-memory
identity and do not require database rows.

A saved queued/running/stopping observation is not proof of live execution.
`subagent.send` and active-task `subagent.cancel` reject orphan observations
with a control error instead of raising `KeyError` or claiming a stop. Repeated
cancellation of terminal tasks stays idempotent. Constructing a reader does not
seal another host's tasks: interrupted-task recovery remains an explicit host
startup operation after execution ownership is acquired, without work replay.

Terminal task persistence errors set `state=error` and
`stop_reason=persistence_failed`, retain available output as partial, and name
the failed history/status save in `error`. History and status writes are
attempted independently. The live terminal cache and background report (or
inline tool error) expose that failure even when status persistence itself
failed. No model execution is retried; unsaved output can be lost on restart.

`subagent.send` returns its accepted `message_id` even if the receipt save
fails after live enqueue. In that case only, its JSON adds `persisted: false`
and `warning`; callers should check the task's receipts before resending.
Failed/cancelled inbox-drain saves preserve the accepted body and receipt,
so terminal settlement can mark it `undelivered`. A successful drain claims
only its initial FIFO snapshot; later arrivals remain queued. Live delivered
receipts persist through the next ordinary observation/terminal save.

A rejected task-status write (including a child deleted during the write) is a
save failure, not a successful no-op. A live send still returns its accepted ID
with `persisted: false`; inbox draining retains the body instead of claiming
delivery. A queued task whose initial status cannot be saved does not start
model/tool execution. Terminal settlement retains output with
`stop_reason=persistence_failed`; a removed child is not recreated or announced
to its former parent.

The task list endpoint returns a complete owned snapshot. The browser removes
previous observations missing from a successful snapshot, but keeps task events
or control receipts received after that read began. Failed/malformed reads keep
the last valid list. A late cancellation receipt cannot recreate a removed row.
`session_updated(scope="reset")` immediately clears task UI and fences old list
reads and controls, including resets that retain the same session key. A pending
list read settles before the replacement read starts; no polling is added.

`runtime.set(key="model_preset")` forwards the active request generation to
`set_session_model_preset` and `ConversationModels.select_session`. Those APIs
accept optional `expected_generation`; a supplied generation prohibits session
creation and fences the atomic metadata update. Retired-session conflicts are
reported as tool errors. Calls without a generation preserve explicit
administrative creation semantics.

`AgentLoop.from_config` passes its bound `source_config_path` into default-tool
and task-subagent construction. Search reloads retain that path; standalone
tool contexts with a provider loader capture the current default once.
Configuration I/O runs on a worker, inside the search's elapsed-time deadline.
The synchronous exclusivity check performs no reload; DDGS's shared lock still
serializes its underlying requests. Search error projection redacts known
service/proxy/endpoint credentials while preserving `ToolResult` error and
sensitivity flags.

Web-search drafts use `apiKey: undefined` to retain the stored key and `""`
for an explicit empty edit. Optional-key providers treat an explicit empty
value as key removal; the saved-key Delete action uses that same patch.
Opening/resetting the editor does not create a removal draft. Required keys
still reject explicit empty API patches. Jina/DeepSeek diagnostic logging
redacts known credentials before recording the exception text.

The browser combines same-draft install/retry/autosave requests and serializes
distinct search saves. After awaiting Olostep installation it checks draft
ownership again before sending a settings mutation. Installation may finish
after the user changes the draft; that superseded draft is not saved. Errors
from an already submitted older draft do not replace the current draft's error.

Fetch redirect location parsing is inside response cleanup for both buffered
and streaming helpers. Malformed targets return a blocked-redirect error,
close the hop once, and bypass fallback extraction; successful final responses
retain their caller-owned lifetime.

`files.rg` and `shell.exec` accept `stdin: "closed" | "pipe"` as a per-call
parameter. Invalid values are rejected before launch. Native search defaults
to closed stdin even when `yield_time_ms` is explicitly supplied; this prevents
ripgrep's stdin heuristic from waiting on an unused pipe. Explicit pipe mode
retains interactive input through `shell.session`, including an explicit `-`
path. Omitting stdin on `shell.exec` preserves its legacy default: closed when
`yield_time_ms` is omitted/null, pipe when it is explicitly supplied. Neither
mode rewrites native argument elements or changes timeout handling.

Provider and model settings rows expose `id` and `name` separately. The ID is
immutable; `name` is the editable display name. Model creation returns
`created_model_preset`, and model updates/deletions target `id`. Changing a model
name does not rewrite conversation references or fallback order. Configuration
dictionary keys and model tool arguments use IDs.

`GET /v0/settings/provider-balance?provider_id=<id>` queries an explicitly
configured balance endpoint. An unconfigured query returns `status: "disabled"`
without contacting the provider. Successful responses contain decimal amount
strings and their currencies; endpoint failures are reported as errors. Balance
settings are edited through `settings.provider.update`, with credentials redacted
in returned settings.
JSON numeric amounts are decoded as decimals before producing those strings.
Queries use only the provider's explicit proxy setting and do not follow
redirects. Invalid endpoints, including invalid environment-expanded addresses,
return a safe query error (HTTP 502) without disclosing embedded credentials.
Saved endpoint validation rejects invalid ports and any user information.

## Skill catalog and detail

`GET /v0/webui/skills` includes the author-declared `always` boolean and lists Skill availability separately from the saved enabled
state. Sources are `home`, `builtin` and `plugin`. Home Skills are independent of
the conversation workspace.

`GET /v0/webui/skills/<name>` includes the original `raw_markdown`, requirements
and supported installation hints. Invalid runtime declarations return
`available: false`, a specific `unavailable_reason` and `requirements: null`;
they are not represented as a successful empty requirements list. Filesystem
read failures remain request errors.

Runtime settings also expose `agents.defaults.always_skills` (Skill names), `agents.defaults.memory.context_files` (Home-relative paths under `memory/`) and `agents.defaults.memory.context_files_tokens` (256–32768). The separate shared-memory budget, `agents.defaults.memory.context_tokens`, also accepts 256–32768 tokens. These fields update through `settings.runtime_config.update` without requiring a restart. Availability and enabled flags remain independent of fixed selection.
