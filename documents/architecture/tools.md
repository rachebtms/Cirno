# Tool namespaces

Cirno keeps one implementation per capability. The shared catalog in
`sources/cirno-core/src/cirno_core/agent/tools/names.json` defines model-facing operation names;
Python execution, PTC, activity rendering and persisted calls use the same map.

Node catalog initialization and Skill inspection run local storage work outside
the event loop. Cancellation waits for an already accepted initialization or
Skill-history write to settle before the tool exits, including repeated stop
requests and local write failures. This does not replay remote SSH operations.

Authenticated Node settings actions use the same local initialization rule and
the state directory beside their request's configuration file. Node setup runs
outside the event loop. Accepted Node enrollment/removal, monitoring-policy,
memory-maintenance and Skill-history writes settle before request cancellation
finishes; remote commands keep their separate transport/outcome handling.

| Namespace | Operations |
| --- | --- |
| `files` | Read, view image, write, edit, list, find, search, ripgrep, patch |
| `shell` | Execute, continue a process, list running processes |
| `web` | Search and fetch |
| `memory` | Search, read, original evidence, revisions, tags, save, update, link, checkpoint, status |
| `goals` | Create, update, inspect; Router-only control of other conversations' Goals |
| `conversations` | Create, title, search, read, send, report; Router-only stop and continue |
| `user` | Asynchronous questions and withdrawal; Router-only visible messages |
| `agents` | Create, check, send, cancel subtasks |
| `automations` | Add, list, update, enable, disable, remove, history |
| `nodes` | SSH execution, file transfer and durable job control |
| `projects` | Router-only catalog management and conversation assignment |
| `credentials` | List metadata; explicitly read, store or delete Agent-visible credentials |
| `skills` | Validate and read retained versions |
| `runtime` | Inspect or change allowed runtime settings |
| `apps` | Run installed CLI Apps |
| `ptc` | Execute a program using the available tools |

## Naming and validation

Native function-calling APIs restrict characters in tool names, so native calls
use `memory__search`. The PTC SDK uses `await tools.memory.search(query="...")`.
Activity labels display the dotted logical name or a localized description.
MCP calls use provider-safe names. Names requiring character normalization receive a stable hash suffix so distinct upstream names remain distinct. Very long names are capped at 64 characters. MCP allowlists accept the original upstream tool name or the exact exposed name; repeated exposed names fail discovery before registration.

Python implementation identifiers connect tool classes to the shared namespace
catalog. They are internal dispatch details, not a second advertised tool API.
When adding or renaming an operation, update the shared catalog and its schema,
then check native execution, PTC dispatch and activity rendering together.

Action-based implementations expose separate operations with their action
bound by the registry. Memory and Node schemas contain only the relevant
parameters. Skill inspection, subagent, automation and runtime operations also declare only their own inputs and per-operation required fields. The registry validates the public operation's schema after shared safe casts and before execution, in both native and PTC paths; a caller cannot override the bound action. Memory writes accept only session/project/user scope and event/knowledge layers; `all` remains a retrieval filter. Context consolidation acknowledges only supplied, explicitly reviewed and unchanged pending input revisions. Ordinary turns do not receive `memory.confirm`.

## Result status and diagnostics

Deleting a protected or missing automation is a tool error, not a successful removal. CLI App timeouts and MCP resource/prompt failures retain error status through execution hooks and activity rendering. A timed-out CLI may already have produced effects; inspect its output files before another run. A search configuration refresh failure is reported without sending the query to a stale provider. Conversation reads preserve code indentation and line breaks; search snippets remain compact excerpts. Web fetch selects its JSON, HTML and image extractors using case-insensitive media types, while preserving case-sensitive media parameters.

Search errors redact known service keys and proxy credentials before shortening
diagnostics or stripping markup. Truncation therefore cannot expose a partial
credential that the final tool-result filter would no longer recognize.

Tool-result error guidance retains structured status and sensitivity markers.
Sensitive errors remain available to the executing model, while activity,
boundary diagnostics and durable copies hide their contents. An oversized
sensitive error is rejected by the same result limit as a credential read;
it is never offloaded to a plaintext result file.

## Network destination safety

Search-source links and browser activity share a display-only HTTP URL filter.
IPv6 private-prefix checks apply to IPv6 literals, not ordinary DNS names that
happen to begin with `fc` or `fd`. Local hostname checks recognize a trailing DNS
root dot, and link-local IPv6 filtering covers `fe80::/10`. This presentation
filter does not replace request-time network validation.

URL safety resolution for web fetch, redirects, pinned HTTP transport and MCP
connections runs outside the server event loop. Slow DNS cannot prevent other
conversations or Stop from being handled. Cancellation while a safety lookup
is pending does not send the subsequent request; the read-only resolver may
finish in its worker, but its result is discarded. Redirect responses are
closed even when cancellation interrupts the next target's validation. The
same protection applies to browser MCP authorization URLs and Telegram remote
attachments; Telegram local attachment reads also run off the event loop.
URL allowlists, private-address checks and per-request IP pinning are retained.
These changes do not alter prompts, tool schemas or model request concurrency.

An accepted cross-conversation send settles its durable inbox entry, live
wakeup, rolling-rate receipt and optional reply-timeout registration before
propagating Stop. It retains the send lock through settlement; it does not
start another model request. History excerpts locate matches in the original
text after Unicode case folding, and search previews normalize the query's
whitespace along with the displayed text. Read excerpts still preserve line
breaks, while search previews remain compact.

## Settings and channel receipts

Channel validation reads the settings endpoint's explicit configuration owner,
including saved credentials and selected proxy. A process-default configuration
cannot supply another instance's token to that probe. Draft overrides retain the
existing blank-secret/explicit-clear behavior and validation does not persist
them.
Required-field checks and feature readiness share the setup contract's field
types. Draft strings for switches, comma-separated lists and JSON objects are
interpreted consistently with saved values; empty required values cannot become
ready merely through stringification. Snapshot presence remains separate from
requirement satisfaction so an optional `false` override is retained. The form
defaults an ordinary boolean without a declared value to `false`, matching
runtime defaults; an inheritable field does not acquire an explicit override.
The form and server select the same closest alternative group and match missing nested
fields by their full declared path, without marking sibling fields of the same
name.
Channel setup can declare a pure local `validate_config` callback. Settings
writes and enablement run it before persisting the selected instance, and draft
checks run it before platform probes. WebSocket uses its runtime configuration
model through this callback, reporting field errors without input or secret
values. Disabling a broken channel does not require repairing its configuration
first. Empty optional numeric/JSON/enum drafts keep the same saved value as a
write that skips those fields. Proxy assertion names obey HTTP token syntax;
listener ports include ephemeral zero but reject values outside 0–65535, and
public WebSocket URLs validate their authority and port. Authentication policy
recognizes equivalent unspecified IPv6 addresses and empty bind addresses.
Channel setup acknowledges saved drafts separately from live application:
`last_action.ok=false` remains a visible failure, while channel-specific restart
requirements are informational. A successful `hot_reload` receipt is not
overridden by unrelated global restart requirements.
Channel runtime projection preserves `enabled` as persisted intent and `running`
as adapter liveness. Health can remain `failed` while an old or sibling adapter
is live; the running count and stop controls retain that fact. Disabled inactive
instances use the same stopped-state projection as their parent, and a fresh
runtime snapshot clears obsolete runtime errors. Source payloads remain
unchanged. The catalog retains actual live channels even when saved enablement
is false. Restart/install/credential prerequisites gate enablement, not stopping
a live adapter; the required WebUI and serialized-operation guards remain.
Catalog and multi-instance action receipts publish confirmed saved state before
displaying a failed live action. A persisted edit is not retried automatically
merely because its subsequent runtime application failed.
Settings catalog mutation and child-panel receipts invalidate older feature
reads through a shared revision. The actual channel-section publication binding
uses that receipt path; ordinary poll results do not become mutation receipts.
Catalog mutations pause their polling, and action errors are held separately
from transient read errors so a healthy read cannot erase a failed action.
Feature, dependency-install and CLI action entry/completion paths verify the
Settings lifetime before starting follow-up work, notifying other surfaces or
updating restart state. A sequential capability install publishes each accepted
receipt before continuing, retains partial progress and stops on an explicit
failed receipt. CLI retry timers remain owned by their effect and defer reads
while an installation is active. Admitted CLI actions take over the initial-load
indicator even if an older read is still pending.
The root Settings snapshot uses a synchronous receipt revision as well as the
parent-prop identity check. A model-order save invalidates an earlier bootstrap
read before React commits the parent's cache update; an accepted snapshot also
releases initial loading. Telemetry-only usage updates do not advance that
configuration revision. Bootstrap-read errors are separate from explicit
settings-action errors: accepted snapshots clear obsolete read failures without
erasing a rejected save reason. CLI catalog errors and explicit CLI action errors have
separate ownership, matching channel feedback, and the Apps dismissal binding
clears both without changing the last saved catalog.
Shared activation, local-state, read-ordering and write-acknowledgement rules are
defined in [Frontend resources](frontend-resources.md), including settings action
gates and their regression suites. Feature-specific receipts and authorization
workflows remain subject to those rules.

## Outbound presentation and delivery

Outbound duplicate filtering applies only to ordinary text replies with the
same known upstream message identity and identical text. It preserves whitespace
because indentation and line breaks can change code and document meaning.
Attachments, buttons, explicit reply targets, presentation payloads and typed
lifecycle events keep their separate delivery identities; a repeated caption
cannot establish that a file or action is a duplicate.

Telegram ordinary replies and stream commits bound displayed text after entity
parsing, matching the [Bot API text contract](https://core.telegram.org/bots/api#sendmessage).
HTML tags, link attributes and escaped entity spellings do not consume extra
text characters. Table alignment can expand actual displayed text and triggers
additional Markdown-safe chunks. Tool-hint blockquotes use the same accounting;
reply markup remains on the final chunk.
Chunk iteration carries the original remaining Markdown and whether its first
line continues the previous fragment. Preview edits, commits, definite-rejection
retries and finalization retain that state instead of joining pre-split chunks
with synthetic newlines. A hard-cut `>`, heading or list prefix remains literal;
genuine newlines still start Markdown blocks. Adaptive text-budget recuts use
the original remainder, avoiding repeated synthetic code fences.
Rich-message continuation tails retain native Markdown, protecting only a newly
exposed structural marker with a numeric character reference, consistent with
[GFM character-reference rules](https://github.github.com/gfm/#entity-and-numeric-character-references)
and Telegram's [rich Markdown contract](https://core.telegram.org/bots/api#rich-message-formatting-options).
Fragments are consumed lazily so retained resume tails do not accumulate into
a second copy of every suffix of a long response.
Table rendering requires a header followed by its matching delimiter row.
Delimiter-looking lines without a header remain literal, and empty data rows or
empty boundary cells retain their positions instead of being discarded or shifted.

## Web fetch limits

Web fetch bounds response bodies before extraction, using
`tools.web.fetch.max_response_mb` (16 MiB by default). The setting is available
on the Web page and is independent of returned-text truncation. Announced
sizes can reject a response before its body is read; streams without a size
and decoded compressed bodies are counted as they are read. Oversized image,
local-extractor or Jina responses close their stream and return an error rather
than retrying the download. Decoded responses are not decompressed a second
time when handed to the local extractor.

## Automation scheduling and state

Automation schedule edits verify the next occurrence before changing the live
job. A syntactically valid cron expression with no next occurrence is rejected
without changing the task name, instruction or schedule, including while a run
is executing. Ordinary instruction edits preserve the existing due time; valid
rescheduling during execution preserves the replacement occurrence.

Enabling or disabling a job is idempotent: repeating its current state does not
postpone the next occurrence or rewrite its action log. A running callback
records its outcome without replacing a newer enable/disable decision, including
one-shot jobs that would otherwise delete themselves on completion. Instruction
updates through the Web UI preserve their exact indentation and surrounding
newlines while still rejecting blank instructions. Startup reconciliation keeps
system jobs' creation time, last outcome and bounded execution history; changing
their interval recomputes only the next occurrence.

Re-enabling an expired one-shot is rejected before any state is changed; both
the tool and Web UI explain that its execution time must first be updated.
Naive one-shot datetimes use the configured default timezone, and nonexistent
wall times during a daylight-saving jump are rejected rather than silently
shifted. Valid local times and explicitly offset ISO timestamps retain their
normal interpretation.
Cron schedules without an explicit timezone use the detected host IANA timezone,
including its seasonal offset rules, rather than freezing the host's current
UTC offset. Explicit schedule timezones take precedence. Web UI schedule
validation and create/edit/restart execution share the same next-occurrence
calculation.
Creation and schedule changes also recheck the next occurrence at the final
storage boundary. A time that expires after request parsing is rejected without
creating an inert job or partially applying its new name and instructions.
Unchanged past schedules remain editable without replacing the due occurrence.

The automation manager serializes local mutations and fences both periodic and
explicit reads across those mutations. Older successes or errors cannot replace
an acknowledged edit, enable/disable decision or chat change. Overlapping reads
publish only the newest request's result and loading state. Chat-binding choices,
review drafts and pending save callbacks belong to their authenticated task view;
switching credentials or tasks retires the old view without publishing its late
completion into the replacement view.
Closing the automation settings cancels its delayed post-run refresh timers and
retires saved callbacks. A mutation already accepted by the server may finish,
but its late acknowledgement cannot start new refreshes for the closed view.
Automatic post-run refreshes also skip hidden settings surfaces; reopening the
automation section resumes its normal status polling.
The per-conversation automation panel applies the same acknowledgement and read
ordering rules. It filters mutation receipts to that conversation before updating
its list and detail, so another conversation's tasks cannot appear in the panel.
The optional `webui_session_key` in automation rows identifies their bound Web UI
conversation independently of the delivery address; external session keys remain
unexposed. Older hosts fall back to the existing origin key.
Changing the conversation or credentials closes the old overlay and retires its
pending callbacks.

Saved cron and local-trigger routing snapshots exclude the creating turn's
history generation, turn owner, recovery/continuation identity, delivery run ID
and quoted runtime context. Each invocation receives fresh execution identities
and binds to the current history through ordinary admission. Existing saved
payloads are filtered again at dispatch, so a reset or edit does not leave their
replies attached to discarded history. Channel thread addresses remain in the
saved routing context. Workspace and access policy are resolved from the bound
conversation at execution time; a saved Full Access snapshot cannot override a
later restriction. This changes neither
the reusable model prompt prefix nor model concurrency.

If recovery or Goal admission rejects a queued automation before model work,
its waiting scheduler or trigger receives an explicit execution error and its
pending entry is released. A skipped turn is not recorded as successful and
cannot leave its submitter waiting indefinitely.

Cancelling a submission that is still deferred removes that submission from the
shared cron/local-trigger queue. Cleanup is scoped to its coordinator and run ID,
preserving other automation kinds and their FIFO order; retrying the cancelled
submission cannot leave a second deferred copy behind.

Local trigger execution outcomes are committed before updating trigger history
or deleting queue files. Once a terminal receipt exists, retries and startup
recovery finish only those storage steps and never submit the instructions
again. History settlement uses the delivery ID to avoid duplicate entries.
Distinct deliveries keep distinct history entries even when their creation
timestamps match; explicitly stored zero timestamps are retained.
Retry status updates replace that delivery's history entry, so a transient
transport failure and its successful retry do not appear as conflicting runs.
Run history exposes an optional `run_id`, using the cron run ID or local delivery
ID. Result requests send that ID along with the timestamp and validate it against
the task's saved history before reading a record. Explicit local delivery lookups
read only the selected receipt, so unrelated damaged files cannot block it.
Older history without IDs keeps the unique-timestamp fallback and rejects
ambiguous matches. The result dialog distinguishes same-timestamp IDs, reloads
when an outcome changes, and follows the current outcome while open in the
calendar. Local-trigger recognition also supports the older payload/schedule
fields when a top-level task kind is absent.
An interrupted gateway's `processing` receipt is an unconfirmed outcome: its
delivery is retained in the failed queue and the trigger exposes an error asking
the owner to inspect the session before resubmitting. Unstarted queued deliveries
and explicitly interrupted submissions retain their existing retry behavior.
If a known outcome cannot be saved, its delivery is also retained for inspection;
an atomic replacement that succeeded before a sync error reuses the committed
receipt. Malformed, oversized or mismatched receipts are preserved and rejected
before any execution rather than treated as missing results.

Heartbeat journal admission checks pause state and pending heartbeat ownership
inside the same transaction. Concurrent ticks reserve one pending entry;
ticks racing a pause or history reset are skipped before bus delivery. Live
ticks and recovered ticks carry their destination history generation. Cleanup
of rejected approvals and paused heartbeats acknowledges only the generation
that was inspected, so later replacement histories keep their own pending inputs.

## CLI installation and readiness

Installed CLI App execution and local help checks read their durable installation record without refreshing an external catalog. Installed apps remain in Settings even after their catalog entries disappear. New install/update records retain the package definition for offline uninstall. Legacy records can also be removed offline when their bundled strategy or exact Python distribution is retained; unknown older recipes keep their previous catalog lookup rather than guessing a removal target. Catalog capitalization changes preserve one installed identity across listing, install, update and removal. Catalog outages or an entry disappearing upstream do not stop a locally installed tool from running. Relative working directories resolve under the current project and retain workspace-boundary checks. Command discovery uses the execution environment’s PATH, including the persistent tools Python environment; Python package identity is read from that environment rather than the server’s packages. Attachment catalog/Skill reads run outside the service event loop. CLI App management commands use the same owned process-group cleanup and bounded output capture as app execution; an install/update timeout cannot leave ordinary same-group children running. Updating a pinned or tagged npm package replaces its old selector with `@latest`, including scoped names. Generated CLI Skill headers are rewritten as YAML without modifying body fields and are published atomically.

Catalog refreshes may update display information, but installed entries keep
their saved executable and known package definition in both status and
manifests. Replacing that identity requires an explicit install/update operation.
A successful package-manager exit alone does not make an app ready: install and
update verify executable availability in the resulting catalog snapshot. A
missing executable produces `last_action.ok: false` and
`verification_failed: ["entry_point_available"]`, while preserving the installed
record for repair or removal. The browser displays failed action results as
errors and requires both installed and available state for its Ready filter and
ready panel.

One Settings view submits one CLI management operation at a time, including
command checks. Duplicate or overlapping clicks do not submit another action,
and CLI controls become available again after the current result settles.
Catalog reads started before or during that operation cannot replace its result
or error; hidden pages pause catalog polling. This is a browser-view policy,
not a package-manager lock shared by different clients.

CLI artifact discovery bounds directory enumeration and sorting by its scan
budget, rather than loading a complete large directory before checking the
limit. Reports include only files resolving below the selected working
directory; in-tree aliases remain usable, while escaping or unresolved symbolic
links are skipped. A cancelled asynchronous catalog refresh drains an already
accepted cache write before completing cancellation.

## Catalog refresh and view visibility

The settings runtime owns its detached catalog refresher and its retry throttle;
different runtimes do not share a module-global refresh task. The owner registers
pending work with runtime admission, refuses new refreshes during maintenance,
and cancels then drains refresh cleanup before shutdown completes. Repeated
close requests do not cancel that cleanup again. Cached reads remain available
during maintenance without launching a writer. The local-read helper requires
an explicit runtime refresh callback to start detached work; without one, it
returns only the cached snapshot. The first refresh can start even when the
monotonic clock is below the retry interval.

Kept-mounted Settings tabs combine workbench-surface and browser-document
visibility for polling. Switching to another tab pauses those polls while
preserving the mounted editors and drafts; returning resumes them. The global
Inbox provider continues to update unread badges and notifications across
workbench tabs.

## Notification views

Notification pages read their rows, unread counts and latest delivery cursor in
one SQLite snapshot. A notification arriving between those reads remains beyond
the returned cursor and can be observed on the next poll. Inbox pagination and
manual refresh responses belong to the specific category/connection view that
started them, including category A→B→A changes and disconnect/reconnect cycles.
Old results and errors cannot replace the new view. A synchronous action guard
also prevents duplicate or conflicting approval/Inbox actions before the UI's
busy state has rendered; accepted actions keep their busy state until they
settle.

## Managed Skills

Generated Skill names use bounded, stable suffixes when normalization could
collide (including underscores), exceed the name limit or create invalid hyphen
sequences. Ownership metadata distinguishes apps with different registry names.
Older generated notes also establish ownership, so updates preserve those legacy
folders and existing fixed-injection selections. Lookup, attachments, manifests,
updates and removal use the same path resolution. Path selection and publication
or removal share a file lock, so concurrent management cannot claim another app's
published folder.
An existing folder with no recognized generated ownership is kept intact.
Install uses a separate stable path when a user-created Skill occupies the old
name; an occupied unowned fallback directory returns a conflict instead of
overwriting it. Removal skips unowned or unreadable Skills, and such files are
not reported as an installed managed Skill. Recognized legacy generated notes
still establish ownership and retain their original paths.
Uninstall removes the installation record only after managed Skill cleanup
succeeds. A cleanup failure retains the record so the owner can inspect and
retry the unfinished removal.

## SSH host-key checks

SSH host-key fingerprint calculation has a bounded subprocess lifetime. Cancelling or timing out that check terminates and drains its subprocess before returning, just like SSH execution cleanup.

## MCP lifecycle and configuration

MCP tool calls are automatically replayed after transport interruptions only when their server declarations explicitly mark them read-only or idempotent. Missing annotations do not authorize replay. For other calls, a disconnect, SDK cancellation or timeout reports an unconfirmed outcome because remote effects may have completed. A terminated session may reconnect for a later explicit operation, but that does not repeat the uncertain call. MCP resource and prompt reads retain their bounded reconnect/retry behavior. External cancellation remains cancellation. MCP structured results are retained even without text blocks. Matching JSON already present in text is included once; distinct explanatory text is retained alongside the structured result. Image artifacts keep their metadata and Router delivery instructions use `user.message` with its `media` array.

MCP settings serialize configuration, tool-scope and browser-authorization
changes for the mounted settings surface. An older catalog success or error
cannot overwrite an accepted change. A mutation receipt that reports a
connecting server starts the same status polling used for initial
catalog loads; it does not require leaving and reopening settings.
Accepted MCP configuration and plugin changes retain request ownership through
the disk write, runtime reload and restart bookkeeping, including repeated
cancellation. A cancelled browser request therefore cannot leave an untracked
background write whose runtime application was skipped. Catalog and inspection
metadata reads finish accepted filesystem work before propagating cancellation.
Inspection transports remain cancellable, with accepted connection cleanup
retained until it settles.
Settings catalog discovery, inspection config/command checks and result
projection run on I/O workers. Runtime-status callbacks stay on their owning
event loop and are observed after catalog discovery, so a status change during
discovery is reflected in the returned rows. Default-instance reads capture the
selected configuration before scheduling their worker. Maintenance admission
remains busy until accepted metadata work has finished, including on repeated
cancellation or a filesystem error; cancelled preparation does not dial a server.
Removing a managed MCP connection saves its configuration removal before
deleting runtime files; a failed configuration save preserves those files.
If credential or managed-file cleanup fails after the commit, the response
reports `last_action.persisted=true` and lists the failed verification checks.
The runtime reload and restart bookkeeping still run, and imports attempt
cleanup for every affected connection. The settings view retains its editor
draft on an incomplete result while publishing the committed catalog and any
restart requirement. A cleanup failure does not mean that the configuration
change was rolled back.
Repeated custom saves and imports reconcile obsolete OAuth entries against the
desired connection, even after its configuration was committed by an earlier
failed attempt. The credential-store lock covers both the URL check and
deletion; authorization already obtained for the desired URL is preserved,
including its generation and write lease.
The catalog rediscovers removed connections' leftover runtime entries and
credential identities in the existing instance stores as `cleanup_pending`.
Only server names are exposed. The MCP page offers **Retry cleanup**; it uses
the normal remove operation with `cleanup_only=true`. The server refuses that
request if the name is configured again or belongs to an enabled plugin.
Cleanup remains explicit, and a refreshed catalog can recover the list without
a separate journal, persistence root or background task. Managed links are
unlinked without following their targets; user-selected working directories
remain outside managed cleanup.
An inspection projects its tool inventory, count, timestamp and scrubbed failure
onto the inspected server row. A successful zero-tool result replaces the
previous inventory; an ordinary uninspected catalog row does not. During a
reinspection or after its failure, the panel keeps its last known inventory and
counts selections against that displayed list. Untouched permission selections
follow new saved settings, while explicit drafts remain available to save.
Changing the managed server retires the previous server's inventory and drafts.
Agent Plugin discovery and enable/disable actions use the configuration file
that owns the settings request. Activation markers, plugin runtime directories
and Skills cache entries use that same instance, including when multiple
configurations share a workspace. MCP runtime loading carries the configuration
owner through environment expansion into plugin loading. Disabling one instance
invalidates its plugin Skills cache without revoking another instance's access.
Skill catalogs, details, marketplace installation checks, prompt builders and
file-tool read permissions carry this configuration owner into discovery rather
than consulting the process default later. Home paths remain independent: Skill
availability snapshots are retained under the loader's captured Home.
Cached plugin read roots also recheck their owning activation marker. Removing
or invalidating that marker outside the process revokes the cached grant;
ordinary project-file reads still avoid package fingerprint scans. Enabling a
plugin publishes a complete marker atomically, so a simultaneous catalog read
cannot consume a truncated marker and undo activation.
Cached grants recheck their package location and activation-data directory
against the owning boundaries before reading the marker. Retargeting a cached
directory outside those boundaries cannot preserve its previous read grant.
Plugin fingerprints now encode path and content lengths to distinguish file
contents from file-tree boundaries. Previously stored hash-based activations
use the old fingerprint format and require explicit re-enabling after this
change; they are not silently accepted as approval of the new fingerprint.
Plugin classification and activation-marker updates use the same config-owner
lock as connection edits and orphan cleanup. A plugin cannot be enabled in the
middle of an accepted cleanup that already found it inactive. Without a runtime
reload callback, the committed plugin receipt explicitly requires restart.
The default MCP reload source stays bound to the configuration used to create
the provider; it does not switch to another process-default configuration later.
An explicitly supplied reload source remains authoritative.
The MCP management checkbox list saves an exact allowlist even when every
currently visible tool is selected. Only the explicit all-tools control requests
`["*"]`, which also allows resources, prompts and future tools. Retained callbacks
from a closed or busy management dialog cannot start a new operation, and an
earlier Save callback cannot submit an obsolete tool draft.
MCP imports validate optional container types before persistence; missing/null
argument, environment and header containers retain their empty defaults, while
booleans, numbers or the wrong container type are rejected. Connection fields
are not coerced from objects into strings. Server identities must match in full,
and entries whose names normalize to the same identity reject the whole import
instead of silently overwriting one another. Malformed shell-style argument
quoting is likewise returned as a form validation error.
Custom forms and imports share the MCP tool-timeout parser: missing/empty values
use 30 seconds, integer values and integer strings retain the 5–600 second
bounds, and booleans, fractional/non-finite numbers or malformed values are
rejected before saving.

Stdio dependency checks locate the executable using that connection's working
directory and PATH, including relative PATH entries and explicitly empty PATH.
Configured environment references are resolved without treating an unset
reference as a default directory. An explicitly set empty reference stays valid.
The runtime uses the same locator off the event loop and passes the located
executable to the transport. A missing executable fails before transport startup;
it does not fall back to a same-named program in another search context. These
checks inspect paths and executable permissions without running the program.
Remote proxy validation follows the selected HTTP/SSE transport, so an ignored
legacy stdio command does not prevent enabling its proxy.
Preset credential fields match HTTP header names without regard to letter case.
Updating a header replaces every case variant of its name. HTTP/SSE connection
setup also merges headers by this identity, with configured values overriding
defaults and transport-supplied values overriding configuration, so old and new
authentication headers are not sent together.
When a credential field is left blank, re-enabling preserves the complete saved
header, including its authentication scheme spelling or whole-header environment
reference. The preset's value prefix is added to new field input, not to an
already complete saved header.
Editing a configured preset's nonblank connection fields uses the configuration
save action before reconnecting. Its Save changes button includes a simultaneous
proxy edit; blank fields continue to preserve saved credentials. A plain reconnect
with no field changes retains its existing behavior.
Retained connection and proxy callbacks cannot submit a draft after the input
or the associated connection configuration has changed.
New MCP activity events carry the wrapper's explicit server and capability
identity, including resource/prompt prefixes. Regular and PTC nested calls use
the same display metadata, so underscore-containing server names and sanitized
or truncated wire names do not need to be split heuristically. The identity
survives durable transcript serialization and replay; old name-only records keep
their legacy fallback. Tool declarations and model input omit these display
fields. Browser action labels accept underscore, dot and hyphen separators in
original MCP names.
Durable tool activity merges phases with the live UI's ordering: error, then
completion, then start. A delayed start cannot regress a terminal call, and a
partial finish retains identity/argument fields supplied by its start event.
The browser applies that merge to the first incoming batch too. Structured
timeline entries keep each distinct call ID and its own result/status even when
the same tool runs repeatedly with identical arguments. Their call order is
retained when old text trace lists contain only one copy of a repeated line;
legacy-only text remains visible, and generic tool grouping retains each call's
details. Object field order is ignored when matching text traces to structured
events, including nested objects, while array order stays significant. These
matching keys affect presentation only and do not rewrite execution arguments
or model requests.
Canonical trace matching and the legacy CLI, MCP, generic and web/shell activity
parsers accept multiline JSON arguments as one call. Pretty-printed persisted
arguments therefore match their compact structured event without adding a
second row or losing the tool's label and target.
MCP OAuth credentials and refresh locks use that same configuration owner.
The SDK/browser flow in `agent/tools/mcp_oauth.py` consumes the durable storage
contract in `mcp_oauth_storage.py`. Existing public storage imports remain
available through the flow module. The storage module owns token-file parsing,
atomic writes, write generations, authorization claims and refresh leases;
provider OAuth remains a separate workflow. Invalid saved token, client or
metadata fields are ignored independently, without erasing valid neighboring
fields or logging their secret values.
Storage objects retain their owner for their entire lifetime, even if the
process-default configuration changes. Catalog checks, connection, reload,
reconnection, inspection and browser authorization all pass the owner through;
removing or replacing a connection revokes only that instance's credentials.
Browser authorization validates its callback before materializing configuration.
Accepted configuration preparation drains on cancellation before releasing request
admission; cancellation at this stage never starts a new browser flow. Configuration
changes, including a replacement that subsequently reports a write error, retain
their own pending-runtime reason. Successful hot reload clears only that reason
and only if no newer authorization preparation changed configuration during reload.
Unchanged reauthorization does not invent a restart requirement. Remote HTTP
callbacks retain their manual-paste mode after preflight validation.
Connection inspections bind discovered tools to the tested server configuration.
Projection compares it against one current configuration snapshot and builds the
catalog from that same snapshot. Removal or changes to the endpoint, credentials,
command or selected proxy discard the old inventory and request a fresh test;
changes only to the tool allowlist or unrelated connections do not invalidate it.
The browser retires cached tools for an explicitly stale inventory while retaining
the last inventory after an ordinary connection failure.
Settings availability checks, connection summaries and inspection preparation
share the runtime transport selector: an explicit transport takes precedence,
otherwise a command selects stdio, followed by URL-based SSE/HTTP inference.
An unused command on an explicit remote connection cannot turn it into a missing
local dependency or replace its endpoint in the connection summary.
Readiness, reload and reconnect recheck local OAuth authorization even for live
connections. Missing credentials withdraw that server's capabilities and cached
tool definitions, close its connection and leave it waiting for authorization;
unrelated servers remain live. Reload receipts list `authorization_required`
separately from connection failures. Reauthorizing makes the server eligible
for the next connection check.
Reload publishes its desired server/proxy snapshot and withdraws all obsolete
capabilities before awaiting any close. Accepted closes drain on cancellation,
including repeated cancellation, so the next readiness check cannot reconnect
a server from the previous snapshot after an interrupted reload.
Configuration/plugin snapshot loading and provider credential checks run on an
I/O worker rather than blocking the event loop. Synchronous reload callbacks
follow the same worker contract. Accepted reload preparation retains ownership
through loader completion, desired-snapshot publication and obsolete-connection
cleanup before propagating cancellation. It does not connect new servers after
cancellation. Readiness and reconnect recheck shutdown after awaited metadata
or close operations before starting a connection.
Credential-presence and stored-server-name probes read the atomically replaced
token-store snapshot; they do not acquire its writer lock or create an SDK write lease.
Metadata probes also leave a missing instance state directory absent. Full SDK
storage reads, authorization claims and token updates retain their separate
lease and refresh-lock rules.
Accepted OAuth credential writes and authorization claims settle before
cancellation is acknowledged. Token refresh retains its refresh lock until the
rotated credentials have finished persisting, including when the request is
cancelled repeatedly. This prevents a replacement flow or another refresh from
overtaking an unfinished write. Credential reads remain cancellable.
Preset-created stdio directories use the same configuration owner. Their
runtime root cannot be redirected through a symbolic link, including to another
directory inside the instance; creation also rejects a symbolic-link entry.
Removal checks the configured parent and server name before touching a
managed entry. A managed leaf link is unlinked without following its target,
and an ordinary user directory is preserved even if a runtime link points to it.
Browser flows own their popup, poll timer and callback submission. Closing the
settings surface retires those callbacks and closes the popup; switching to
another tab while settings remains mounted retains the active authorization.
A status response issued before a pasted callback cannot regress the callback
acknowledgement. Concurrent duplicate starts and callback completions are not submitted.
Cancelling retains the flow until the server acknowledges it; a failure remains
visible and allows an explicit cancellation retry. A callback already in flight
stays single-flight while that cancellation is unresolved.
On the server, replacing an authorization flow serializes through the previous
flow's cleanup. Cancelling a replacement waits for that cleanup and propagates
cancellation instead of starting an unwanted new flow. These guards do not
introduce model calls or additional model concurrency.

Chat Completions choices are alternative answers. Complete and streamed responses select one choice; tools, reasoning and finish status from other choices are never mixed into the selected answer or executed as additional steps. Usage remains the provider's total for the response. Complete responses also accept the legacy `function_call` field when no modern tool list is present. Text-format tool calls receive distinct result IDs even if the provider reused an ID; their arguments stay separate and unchanged.

Only the Router conversation receives `user.message`. Ordinary conversations
reply through normal assistant output. The same selection is used for turns,
compaction and context accounting. PTC wraps that selection rather than
reintroducing tools excluded from the conversation.

## Router replies and execution policy

Visible replies use short, complete `user.message` calls. Invalid JSON is rejected
without delivery; the tool error asks for a complete replacement argument object,
not a continuation of the broken string. Earlier successful messages remain
delivered and must not be replayed. The framework does not silently repair live
arguments, trim repeated text or impose a separate reply-length cap. Chat stream
slots cannot combine different call IDs into one argument string. Reused wire
indices are separated by call ID when attribution is unambiguous; ambiguous
continuations return a classified protocol error for the configured serial recovery.

The Router receives ordinary execution tools plus coordination controls and
`user.message`, but excludes transient `subagent` execution. Worker catalogs
exclude Router-only messaging, cross-conversation controls and Project management.
Both native and nested PTC execution check the same role policy. Within each run,
the Router may make at most nine ordinary calls within its configured cumulative
time budget (1–3600 seconds, default 60); overlapping calls count elapsed time once. Model waiting is not
charged. PTC programs share the same cumulative wall-time allowance across model
rounds, including Python computation; nested ordinary calls count once. In PTC
mode, coordination tools, `runtime.check` and `memory.checkpoint` are also exposed
directly, so supervision does not require another execution program. Replies,
coordination, runtime snapshot inspection and task-checkpoint saves do not consume
ordinary calls or their direct execution time and remain available after exhaustion.
The PTC wrapper itself still consumes wall time; use the direct supervision tools
after exhaustion. Runtime changes and other memory operations remain budgeted.
Read-only task execution such as file reading, web search and remote checks also
remains budgeted; being read-only does not make an investigation a small task.
The budget starts fresh for each run, not each model round or each PTC program,
and is not a conversation-lifetime quota. Limits are returned as explicit tool-policy
decisions with `router_budget_exhausted` or `router_execution_timeout`, rather than
an implementation `ValueError`. A timed-out operation may
have completed effects; its error instructs the model to inspect before retrying.

The Router prompt requires paper analysis, literature reviews, development,
debugging, experiments and uncertain-size tasks to start in a durable Worker
before substantive work. Brief CPU/GPU checks can qualify as direct work. Task
classification is a model responsibility; the runtime enforces the execution
limit and tool permissions. Workers do not inherit the Router's small-task budget.
Access and approval policies apply equally to both roles. Unavailable or already
exhausted work is rejected before asking the owner to approve it; admission is
checked again after approval without charging native approval waiting time.

## Task-subagent ownership and receipts

Transient subagent tasks receive an independent deep copy of the complete
tool configuration, then apply their task workspace restriction. Disabled CLI
Apps, network allowlists and local-service access settings are retained.
Changing a task's nested configuration does not mutate its parent. Scope and
role filtering still decide which capabilities are registered.

New task-subagent sessions bind to the parent's generation in the same
transaction that creates the child. Results and task-change events carry that
identity. Resetting or replacing parent history invalidates these tasks for
current check/list/history access and queued result admission, while retaining
the old child records. A normal metadata revision retains ownership. Existing
historical children without generation bindings keep their legacy declared
parent ownership until that parent's history is reset or edited. The replacement
atomically requires generation bindings, so old unbound children cannot enter
it. Temporary parents use their in-memory identity.

Terminal task history and status saves settle independently. A save failure
retains the output in the live terminal snapshot, reports `persistence_failed`
instead of success, and identifies the history/status data that could not be
saved. Background tasks still send an error report; inline tasks return a tool
error with retained output. A history failure does not skip the status save.
These failures do not retry model execution or repeat completed tool work;
output that could not be saved is not guaranteed to survive a host restart.

A task follow-up already accepted into the live inbox remains accepted if
saving its receipt fails. The send result then includes `persisted: false`
and a warning to check receipts before resending. Inbox draining retains the
accepted message bodies until its save completes and execution is still open;
failed or cancelled saves leave those messages available for an `undelivered`
terminal receipt. New arrivals stay in the next FIFO snapshot. The live
`delivered` update is saved by subsequent observations or terminal settlement,
and a late save after task cleanup does not publish a retired status event.

## Runtime inspection and changes

`runtime.check` reads the allowlisted runtime snapshot, not arbitrary configuration
paths such as `agents.defaults.heartbeat`. Omit `key` to discover its available
runtime fields. It retains its access and secret-field restrictions even when
ordinary execution has exhausted its budget. Runtime changes validate supported retry modes and require a positive tool-result character limit before mutation, matching the settings controls; invalid values return tool errors and preserve the previous value.

Scratchpad values written with `runtime.set` can be read with the returned path,
for example `runtime.check(key="scratchpad.progress.step")`. Those reads retain
the same protected-field restrictions. JSON values must contain finite numbers;
rejected writes preserve the earlier value. Mutable inputs are copied on write
and snapshots are copied on read, so modifying a caller's list or dictionary
cannot silently change accepted scratchpad state. Scratchpad remains in memory
and does not survive a server restart.

Changing `max_tool_result_chars` through `runtime.set` updates the main loop
and task-subagent result limits together. Next-turn synchronization also keeps
that limit aligned, so delegated tool results and terminal output use the same
configured character limit. The existing positive-integer validation applies
before either value changes.

Session model-preset changes from `runtime.set` carry the requesting turn's
generation through runtime control to the metadata transaction. Retired turns
cannot change a replacement history's preset, and deleted/replaced session
conflicts return a tool error. Explicit administrative selection without a turn
generation retains its existing create-if-missing behavior.

## Shell process ownership

Shell execution returns a process-session ID when its initial observation ends
before the command finishes. `shell.session` reads output, writes or closes
stdin, waits for text or exit, and terminates the process. Observation waits do
not extend the command's runtime budget. Process sessions belong to their
execution runtime and conversation; another runtime cannot read or close them.
Listing and interaction use the same exact owner match, including unbound host
sessions: knowing an ID does not let a conversation access a host-owned process.
Cancelling a multi-poll `shell.session` wait returns its already-consumed,
unreported output to that same session's bounded memory buffer. A later poll
receives it before newer output, with the original truncation count, without
resending stdin. This does not recreate closed or expired sessions.
Text waits match only continuous retained output. A truncated head and tail
cannot combine to create a match across omitted text; discontinuities also
survive cancelled waits and later polls. A real target can still match within
either retained region or across successive reads with no intervening gap.
Their output is retained in memory until consumed or expired, and service
shutdown terminates them. Agent shutdown closes new foreground and background admission before capturing active workers; requests waiting on a control lock or journal cannot start a replacement worker afterward. Optional title generation is skipped when admission is closed and cannot fail an otherwise completed turn. Existing archival cleanup remains drainable. Execution diagnostics retain the starting request's
content-logging policy when another caller performs cleanup.

## Project membership

The Router manages explicit Projects with `projects.list`, `projects.get`,
`projects.create`, `projects.update`, `projects.assign` and `projects.delete`.
Assignment accepts a conversation handle and a Project ID, or null to remove
membership. It does not change the working directory. Deleting a Project keeps
its conversations and files. Web UI actions use the same project service and
broadcast catalog updates to connected clients.

Project assignment requires an explicit Project ID or null; only null removes
membership. Missing, blank, boolean and numeric IDs are rejected without changing
membership. Saving with an invalid explicit ID cannot silently create a new
Project. Tool and authenticated Settings actions share these checks.

Project deletion checks membership in each conversation's metadata transaction.
A concurrent history reset can retain membership in a new generation, which is
still detached from the deleted Project. A conversation already removed is
skipped without recreating it or aborting deletion; different current membership
is preserved. Accepted cleanup still settles before cancellation returns.

## Reports, Goals and coordination

`conversations.report` records the worker's latest structured state, factual
summary, artifact paths and optional `human_action` question. Progress and waiting
are passive records, available to the coordinator on its next turn. Results,
failures, blockers and new questions enter its durable inbox. Omit `human_action`
to retain a question; an empty string clears it. Reporting `ready` never completes
a Goal; `goals.update(action="complete")` remains explicit. Delegated Goal
completion uses the same report path and reuses a previously queued ready report. Pause/stop accept unfinished Goals, including paused or blocked work, and save any supplied recap. Repeating pause/stop may refresh or explicitly clear that recap without resuming the Goal or resetting its identity and continuation count. Completed/cancelled Goals remain terminal. Scheduler wake decisions recheck recovery ownership and the latest continuation count inside the metadata transaction. Rejected or cancelled queue admission returns its reserved round only if no newer control or accepted worker owns it. Limit pauses retain verified progress in `recap` and record `pause_reason=continuation_limit`; resuming clears the reason. Post-model limit handling also checks the current Goal before writing, so it cannot overwrite a newer stop or replacement.

Automatic continuation slices bind to the history generation that produced
them and require that conversation to still exist. Goal and approval checks
read one current header without creating missing history; a deleted or replaced
conversation rejects the old input even if its Goal identifier was restored.
Discarded approval inputs cannot acknowledge follow-ups in the replacement
history. These admission checks add no model call or prompt-prefix change.

Conversation stop changes the current Goal inside its metadata transaction,
retaining the latest progress and any already-completed state. Journal cleanup
and the resulting recovery notice stay bound to the inspected history
generation; they cannot overwrite a reset or replacement history. Stopping an
already idle, completed conversation does not create a new interruption.
Stopping an active or scheduled Goal still retains its explicit continuation.

Conversation sends mean **queued**, not read or finished. Stable message IDs and
SQLite inbox receipts prevent replay of already-consumed coordination inputs,
including after restart; pending inputs remain recoverable. Receipts live with
session runtime state, separate from memory databases. A consumed receipt means
the input was committed into the turn's context, not that the task succeeded.
They are scoped to the destination session generation and deleted with the
conversation. A reused ID with a different payload is rejected.

## Workspace admission and media

WebUI message intake completes workspace admission before consuming upload
references. The final attachment check detects expiry or disconnect during that
admission, and committing attachments precedes the asynchronous history write
so cleanup cannot delete files already referenced by history. Failed admission
rolls back only its still-unused session generation. The same SQLite write
transaction checks the initial journal revision, canonical/display history,
pending inputs, recovery/inbox records and children before deleting; another
accepted use, including a metadata-only setting change, prevents rollback.
An obsolete rollback cannot delete a replacement generation. Workspace opening
retains its journal result through cancellation before cleaning up, including
repeated cancellation. A later recent-project preference failure retains the
draft workspace and releases only its unused creation.

Workspace authority reads prefer the current persisted scope over an obsolete
draft. Once a persisted scope is observed, its old draft no longer authorizes
media after deletion. Both synchronous and asynchronous reads keep transient
private conversations restricted, including when the ordinary default is full access.

Loading a saved scope validates its structure without requiring its directory to
exist, preserving the original boundary if the directory disappears. Selecting a
new directory still requires an existing directory. An invalid explicit saved
policy fails closed; indexed sidebar fallback is presentation only. Only an
explicit owner access-setting action can repair an invalid mode, while retaining
the bound project. File previews return a policy error (availability probes
return unavailable), and trusted attachment-free stop controls bypass workspace
admission without changing saved policy.

Workspace preference mutations hold one shared in-process file lock across
reading, merging and atomic replacement. Recent-project recording, favorites and
default access updates therefore preserve each other's fields. Slow preference
writes and folder resolution run in a worker thread and are drained on
cancellation before admission cleanup continues.

Live assistant Markdown images and videos resolve relative to the conversation's
current project, using the same workspace boundary as history replay. A file with
the same relative name in the default workspace cannot replace that project's
file. Invalid URLs, unavailable user-home paths and unavailable optional media
remain literal Markdown; they do not discard the textual answer. An invalid
saved scope never authorizes media from a default-workspace fallback. History
and subagent-history requests report invalid scope explicitly.

Completed stream records retain the original Markdown paths, rather than
instance-secret signed URLs. Delivery and replay sign those paths for the
current server instance, allowing new streamed records to render after a
restart. Existing URL-only records without recoverable source paths are not
rewritten. Live Markdown media staging runs outside the service event loop;
cancellation waits for that owned copy to settle.

## Delegation provenance

Delegation keeps the source conversation, turn/message identifiers and a bounded
verbatim original-request excerpt. Workers read the source when it is incomplete;
neither routing notes nor reports grant new user authorization. Worker creation checks that the owning conversation still exists and matches the request’s session generation; an already cleared or deleted source cannot create new work.

## File operations

Directory listing runs in a cancellable file worker. Recursive listing prunes
ignored directories before entering them, keeps deterministic ordering and
does not follow directory symlinks. Writing a Skill also performs its history
snapshot in the file worker before the transactional write; neither operation
performs the directory scan on the chat event loop.

When ripgrep is available and execution is enabled, `files.rg` replaces the
Python find/search tools. It also requires `tools.file.enable`; initialization
failure retains the Python fallback. Its argument vector is passed without
shell interpolation. Standalone `files.rg` calls default to `stdin="closed"`,
so a pathless search does not wait for an unused pipe. To intentionally search
stdin or read patterns from it, request `stdin="pipe"` and send input, then
close stdin through `shell.session`. `shell.exec` also accepts these explicit
input policies; omitting the option retains its existing behavior. Input mode
is independent of the initial wait and the command's runtime limit.

A standalone file tool's explicit `allowed_dir` remains a fixed boundary even
without a default workspace. Normal shared workspace tools continue following
the current conversation's access mode. A fallback read of a bundled Skill
checks the resolved bundle path against the same read permissions; the normal
tool factory explicitly grants bundled Skills access.

An atomic write or edit can report an error after replacing the file. Such an
error reports an unconfirmed write outcome and asks the caller to read the
destination before retrying. Office reads check Stop between extracted lines,
including lines skipped for an offset; PDF reads check between pages and close
their reader on completion, failure or Stop. A parser operation already running
must return before its file worker can finish stopping.

The Python file-search backend shares directory scanning, filters and paging
between path discovery and content search. Their model-facing contracts reject
unknown options before execution rather than silently ignoring misspelled filters.
Stopping either search retains its file worker until the accepted scan has
settled. PDF and XLSX line streams close their parser/workbook on exhaustion,
failure or early close, including a stream closed before its first line.
Text search uses an atomic snapshot and checks the bytes actually read against
the file limit. If a document fails partway through a directory count search,
its partial count is excluded from successful-file totals and its failure is
reported separately.
UTF-8 BOMs are treated as encoding
markers rather than first-line content, so anchored patterns match the same
text with or without a BOM. Unreadable directories and failed
file reads return errors. Content search checks symlink targets against the
workspace policy and skips non-regular files such as named pipes; it does not
wait for a pipe writer. Document parse failures identify the failed document.
Regex evaluation shares the scan deadline and releases the Python interpreter
lock, so a pathological pattern cannot stall other conversations indefinitely.

File reads scan text in chunks, retaining only the selected page and its snapshot
hash. A page contains at most 128,000 characters; text files may be up to 100 MiB
and inline images up to 6 MiB. Long individual lines are explicitly marked when
clipped. PDF and Office documents use their page or extracted-line readers.

Text editing and patching retain bounded originals for validation and diffs:
2 MiB per file and 8 MiB across a patch's original and updated snapshots. Use
targeted shell commands for larger data files. Match preparation runs outside the
service event loop. Stop settles that worker before returning and cannot commit
its abandoned edit. If another operation changed a prepared file, the edit fails
and asks the model to read it again.

File writes and edits share atomic replacement, preserving existing permissions.
Patches validate the whole batch before writing. If a later commit fails, already
attempted files are restored; any restoration failure names the affected files.

File edit selection guards apply before either creation or replacement. With
empty `old_text`, `occurrence` and `line_hint` are unavailable and an explicit
`expected_replacements` must be one. Conflicting selection options are rejected
before path resolution. Multiple unselected matches are a structured tool error,
so the activity ends as failed rather than claiming a successful edit.
Text edits and patch replacements retain untouched LF/CRLF bytes. New line breaks
inside a replacement use the target line's style; patch append operations use
the destination's ending style. Patches retain their existing final-newline
behavior.

Patch dry runs authorize and read targets without capturing Skill versions or
writing content. Built-in activity path lookup is likewise observational.
Activity snapshots recheck their byte limit after bounded atomic-snapshot reads,
including files that grow after the preliminary size check. Snapshot reading,
diff generation and pre/post Skill history capture run in owned file workers,
with accepted work drained before cancellation returns. A post-write history
failure retires all committed files' read receipts and explicitly says their
contents were saved; it instructs the Agent to inspect them instead of repeating
the write. These changes do not alter tool names or their schema ordering.

## Credential visibility and persistence

Credential read results reach the executing model only in its live context. Tool activity, durable conversation history, recovery checkpoints, archived evidence and serialized native provider state replace these results with a hidden-value notice while retaining the credential and call IDs. Oversized credential results fail explicitly instead of spilling to a plaintext file; increase the tool result character limit to read them. A later turn or a restarted execution must explicitly read the credential again when needed. Normal non-sensitive request prefixes remain unchanged. This protects the explicit credential channel; it cannot undo secrets previously pasted into messages or copied by an Agent into other outputs.

Credential tools operate only on Agent-visible records. Agent writes mark a record visible; owner writes default to private. SSH enrollment belongs to the owner, and Node tools require both enrollment and visibility. Settings, credential tools, direct Node commands and terminals share the credential service instead of storing separate authentication copies.
Once a credential store or delete has entered its background worker, tool
cancellation waits for that accepted operation to settle before acknowledging
the stop. It does not cancel or replay the database mutation. Read-only
credential calls retain ordinary cancellation behavior.

## Model capability checks

The `files.view_image` operation uses the shared `files.read` implementation for path authorization, bounded reads and visual content blocks. Both entry points reject image injection when the selected model explicitly disables image input; ordinary text reads remain available. Model configurations record image/video input declarations separately from request API routing. Setup probes use the chosen endpoint with no fallback chain, so another model cannot produce a misleading capability result.
The model capability editor serializes probe admission and binds completion to
the mounted editor, client, preset and request configuration. Retired results do
not write into the shared model draft. Editor cleanup releases the parent's
probe-busy state, and current errors allow an explicit retry. New-preset fields
remain disabled through both creation and the subsequent call-order receipt;
ordinary existing-preset autosave still retains its newer-draft behavior.
Server capability checks resolve the actual preset request API before deciding
whether video has native transport; the automatic-API preview does not override
an explicit selection. The existing image/video probe batch owns every child
request: one failure or cancellation cancels and drains peers before propagating
the outcome. Repeated cancellation cannot interrupt that drain or the subsequent
provider close. Environment-resolution errors retain the check's config path.

## Provider balance queries

Provider balance queries remain independent of inference routing and its cache
signature. They pass `trust_env=False` for both direct and explicitly proxied
HTTP requests, disable redirects, preserve JSON decimal amounts, and translate
invalid resolved URLs into a safe query error. Endpoint validation checks ports
and the presence of user information, including a final check after environment
expansion and before HTTP submission. Environment errors retain the gateway's
config path. The balance editor binds reads and saves to the client, browser
token, provider and balance configuration activation. Reads admit one current
request; writes use the shared mutation owner. Accepted writes fence earlier
reads even when secret masking leaves the configuration signature unchanged.
Pending read state remains visible until the physical read settles, without
reviving its discarded result. Save errors remain separate from read failures,
and fields stay disabled during an explicit save.

## Provider discovery and transports

Non-OAuth model discovery also disables environment proxy routing and suppresses
raw transport/parser exception text in its response. It resolves all declared
environment references before choosing a destination or credential: a missing
explicit base never falls back to the built-in host, and an unresolved declared
key is not downgraded to an unauthenticated or partial-key request. Only an
omitted optional key permits anonymous catalog access. The browser surfaces
`not_configured` and `missing_api_base` as retriable configuration failures.
The locality and inferred-header classifiers tolerate malformed URLs. Local DNS names strip a
terminal dot for locality matching; inferred attribution and direct-OpenAI API
selection compare hostnames rather than URL substrings. Explicit provider
metadata retains precedence. These checks do not rewrite stored endpoints or
change prompt/cache prefixes.

OAuth model discovery keys distinguish unauthenticated state from legacy
credentials without account IDs. Known accounts use a stable digest, so token
refresh preserves fresh catalog hits; legacy credentials use an access-token
digest, preventing one anonymous key from sharing models across logins or logout.
The owned Codex, xAI and Copilot catalog HTTP clients, xAI OAuth HTTP helper,
Responses SSE client and Responses WebSocket handshake honor only their explicit
proxy argument. The external Codex OAuth SDK refresh and other interactive
sign-in transports remain separate; this does not claim to change their routing.
Responses WebSocket close drains its accepted transport close before propagating
cancellation. Pool shutdown also drains all captured sessions before reporting
the first close failure, even after repeated caller cancellation. Requests must
already be stopped before provider shutdown, as before. Prompt prefixes,
continuation fingerprints and model-call concurrency are unchanged.

The OpenAI-compatible adapter merges automatic headers with configured headers
case-insensitively, preserving the owner's value rather than sending duplicate
fields with different casing. Anthropic always receives an explicitly configured
HTTP client, including `trust_env=False` when its proxy switch is off.
OpenAI-compatible initialization remains lazy and serialized: failed SDK
construction drains the unaccepted HTTP transport before releasing the client
lock. Its SDK-client close also drains through repeated cancellation. Model
runtime shutdown drains all retained provider closes before returning or
propagating cancellation and preserves the existing grouped failure result.
These changes do not alter message prefixes, prompt-cache boundaries or model
retry counts.

Responses SSE/SDK failure parsing uses a typed `ResponsesAPIError` rather than
flattening the event into an unstructured message. OpenAI-compatible, Azure,
Codex and xAI error projections preserve its safe code/type, optional HTTP
status, retry decision/delay and reported usage. Native failed/cancelled output
does not produce a continuation or a tool batch. Public failure categories also
retain known rate-limit/server kinds when an HTTP status is absent. Quota codes
remain non-retryable; legacy text retry hints and native-compaction rejection
classification are interpreted without persisting the upstream message.
SDK-intercepted stream errors with an error body pass through this same
projection; bodyless SDK connection and timeout errors keep their transport
classification. This normalization does not construct an SDK client or replay
the interrupted request.
OpenAI-compatible streaming tracks text, reasoning and tool progress before
forwarding callbacks. Compatibility fallback to Chat Completions is allowed
only before this output begins; progress is tracked even without a UI callback.
Normal request bodies, cache-prefix boundaries and continuation fingerprints
are unchanged. Existing bounded retry settings still govern serial retries,
and each failed stream closes before the next attempt.
