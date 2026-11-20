# Configuration

`cirno --port 8000` starts the complete service and Web interface in the foreground. Configure a connection in Settings → Providers and add its models in Settings → Models. An instance stores configuration in `~/.cirno/config.json`; select another instance root with `cirno --home /path/to/instance`.

## Install from a checkout

Requires uv, Python 3.11+ and Node.js 24. From the repository root:

```sh
npm --prefix sources/cirno-web ci
npm --prefix sources/cirno-web run build
uv venv --python 3.12 .venv
. .venv/bin/activate
uv pip install -e sources/cirno-setup -e sources/cirno-memory -e sources/cirno-usage -e sources/cirno-vault -e sources/cirno-core -e sources/cirno-server -e .
cirno --port 8000
```

The initial local launch creates the default configuration automatically. Open `http://localhost:8000`, register the instance owner, choose a theme and light/dark mode, and configure a provider and model. Theme choices synchronize with Settings and other devices. First-time setup takes place in the browser. Starting the first chat wakes the Router for a short introduction; it asks about its identity, your preferred form of address and whatever background you wish to share. You can skip model setup and introduce yourself later. New instances have no selected model: connect a provider, create a model preset, and select it before chatting. Incomplete setup returns a configuration message without contacting a model service or retrying. Web search defaults to DuckDuckGo and does not require a search API key. Existing instances retain their previous authentication settings. For a server deployment, see [Docker](docker.md).

Settings → Web search sets the maximum wait for one complete search (1–120 seconds, default 30). All providers use this shared deadline, including serial retries, backoff, SDK calls and fallback searches. HTTP adapters use the same setting for their request timeout. A search deadline returns a tool error; stopping the task still cancels it rather than turning cancellation into a normal reply. No extra concurrent search is created.

Search configuration reloads use the instance's captured configuration path,
including searches in task subagents. Switching the process's default path does
not redirect an existing tool to another instance's credentials. Reloading runs
outside the chat event loop and counts toward the search deadline: the last
known timeout bounds the reload, and refreshed settings apply to elapsed time
from the start of the call. A failed reload sends no query. Admission checks
use the current snapshot without rereading files; DDGS retains its shared
serialization lock.

Search error results remove known configured/environment API keys and credential
values from the configured proxy and search endpoint before reaching the model.
They retain their error status and available service/status diagnostics.

For search providers with an optional API key, use **Delete** beside the saved
key to return to keyless access, or explicitly clear an edited key. Opening
the key editor alone keeps the saved value. Required-key providers retain
their existing key when it is omitted; an explicit empty required key is
rejected. Jina and DeepSeek failure diagnostics use the same credential
redaction as search error results, including when Jina falls back to DDGS.

Search dependency installation and autosave share an ordered save queue. Repeated
save requests for the same draft are combined. Switching providers or changing
the draft during installation prevents that older draft from being submitted;
already submitted saves finish before newer saves. A failed older save does not
attach its error to the currently selected draft.

Web settings also expose **Maximum page response (MiB)**, stored as
`tools.web.fetch.maxResponseMb` (default 16, minimum 1; restart to apply).
Web fetch reads page, image and Jina bodies in a stream and rejects responses
whose announced or decoded size exceeds this limit. Chunked and compressed
responses are checked too. This is separate from the tool's returned-text
`maxChars` limit. An oversized response returns an error and is not downloaded
again through another extractor. Increase the setting when larger pages or
images are needed. HTML/JSON extraction and image encoding run outside the
chat event loop, so Stop can still interrupt the waiting tool.

Malformed redirect locations are blocked and their response is closed before
returning an error. They do not trigger another extraction attempt. Valid
redirects retain the existing URL checks and credential-chain protection.

The keyless DuckDuckGo adapter uses DDGS search. A library failure receives at most one serial retry, with a short backoff inside the configured total search timeout, including time spent waiting for another DDGS call. Cancelling the tool prevents a retry from starting. Final failures retain the exception type and available diagnostic text, with configured API/proxy secrets removed. DDGS may suppress an upstream HTTP status or return no parsed results; an unavailable result is not evidence that no matching pages exist. The adapter does not infer a specific HTTP cause when the library has not exposed it.

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

The retry count accepts 3–20 retries. The provider-constructor environment default `CIRNO_PROVIDER_MAX_RETRIES` uses the same bounds; invalid values fail before constructing a retry sequence. Ordinary retry and fallback logs include safe error categories and attempt information, rather than upstream error bodies that may contain credentials or request fragments. The original structured response remains available to the calling error-handling code.

Enabling fallback models preserves the primary model's visual-input declaration and configured network/retry settings on the outer provider chain. Persistent retries of the whole chain follow that configured delay schedule too. A fallback that cannot be constructed is logged with its model and exception class; its exception body is not copied into ordinary logs.

For Python integrations, `from cirno_core.providers import BedrockProvider` resolves to the current `cirno_core.providers.bedrock.provider` implementation. Looking up the exported class does not construct an AWS client; optional SDK setup is required when that client is used.

Bedrock's blocking client creation and non-streaming SDK calls stay attached to their task until they settle, including after repeated cancellation. Stopping may therefore wait for the SDK call's configured timeout rather than leave it running behind a new request. Shutdown attempts both owned clients before reporting a close failure. Large inline-image preparation also finishes its accepted worker before cancellation returns; small requests bypass that worker.

Codex and xAI subscription requests also finish accepted credential-refresh workers before returning cancellation. xAI applies the same ownership to its model-capability lookup and its one refresh after a rejected token. Stopping can therefore wait for the underlying authentication or catalog operation; it does not leave that operation detached behind the next request. xAI's ordinary request-failure log records error metadata without copying the upstream response body.

Inline shared-proxy setup accepts one save at a time. A failed save keeps the
draft available for retry. Switching gateway connections clears that dialog's
draft, including credentials; a late result from its old connection cannot close
or change the replacement dialog.

Azure OpenAI exposes the same shared-proxy switch. Its model-request transport
and AAD SDK HTTP pipeline receive the explicit proxy selection and ignore
ambient proxy environment settings, using the [Azure transport proxy options](https://learn.microsoft.com/en-us/python/api/azure-core/azure.core.pipeline.transport.aiohttptransport?view=azure-python).
AAD token acquisition uses the current configured request timeout. The API URL
may be a resource root or already end in `/openai/v1/`, including a gateway
prefix; Cirno adds that suffix only when needed. Connection shutdown settles the
Responses backend, SDK client and AAD credential cleanup through repeated cancellation.

Disable proxy use in dependent providers, Web tools, MCP connections and channels
before removing the shared proxy address. Network edits validate those saved
switches before saving, including custom providers and environment-variable
addresses. A rejected edit preserves the previous configuration. Disabling the
last Web tool proxy switch and clearing the address in one settings patch is
also supported.

Model failures distinguish server HTTP errors, connection failures, timeouts and invalid model responses. Chat Completions tool streams use call IDs to keep arguments separate, including compatible gateways that reuse a wire index. A reused index without enough identity information to distinguish unfinished calls is rejected before tools execute. Invalid responses and empty choices use the configured serial retry policy; no extra parallel request is started and completed tools are not replayed. Request messages and their stable cache prefix remain unchanged during these retries.

A received finish reason completes the Chat Completions answer. Cirno still collects the following usage packet, including cache-hit counts, with a total grace period of at most five seconds (or the shorter configured stream idle timeout). Empty trailing packets do not extend that deadline. A missing or failed optional trailer is logged and the completed answer is retained without reported final usage; it does not trigger another model request. An HTTP stream cleanup error also does not replace the completed answer with a model failure. Failures before the finish reason remain errors. If retries exhaust, saved history can contain `[Assistant reply unavailable due to model error.]`; this marks an unsuccessful model request, not a successful reply removed by the framework. Server logs record the provider, model, error category and available HTTP status for failed physical requests even without an open Trace tab. Trace error responses also retain structured error metadata.

Malformed optional usage metadata does not discard an otherwise valid complete
or streaming answer. Invalid primary token counts leave reported usage unknown;
invalid optional cache counters leave the valid reported input/output totals
intact. Inconsistent cache partitions are unknown rather than fabricated cache
hits or misses. Explicit zero cache observations remain zero. Invalid timezone
keys use the usage store's UTC fallback.

Usage queries and model-call recording retain the server's configuration-owned
database. Default WebUI access mode and recent/favorite folders also retain
their instance, including save rollback and new-conversation admission. Browser
uploads and signed media share that instance's media root.
Source previews (including metadata and availability probes), local attachment
inspection and message admission use the same owning media root as their
gateway. A channel upload subdirectory does not exclude media from other
channels in that instance, and switching the global instance does not grant
access to another instance's media. A standalone media gateway also captures
its default media directory when created.
Signed local attachments check the current conversation scope again after file
resolution and opening, before sending response headers. If the conversation
was deleted or its workspace/access scope changed during that I/O, the previous
scope cannot authorize the response; reload the attachment under the new scope.

## Settings pages

Overview shows model and web-search status, plus shortcuts to Memory library, Context consolidation, Goals & execution, Personality, Telegram, Nodes, MCP and Tools & CLI Apps.

- Providers: connections, credentials and optional upstream balance queries.
- Models: named presets, call order, context-window capacity and generation parameters.
- Appearance, Text & reading, Execution display: paired color themes, language, text size, code wrapping and independent brief/detailed reasoning and tool steps. These owner preferences are stored by the service and synchronized across connected devices.
- Browser notifications: per-device browser permission, synchronized sound settings and Inbox category mutes.
- Memory library, Context consolidation, Memory retrieval: stored knowledge; unified context thresholds, experience retention and self-improvement; optional embeddings.
- Personality: separate Router and Worker personalities, shared user preferences and agent instructions.
- Agent heartbeat: periodic checks of `HEARTBEAT.md` and wakeups in the Router, separate from service health checks.
- Conversation coordination: concurrent subagents and the per-source outgoing cross-conversation message limit.
- Time & region: automatic or manually selected timezone.
- Goals & execution: default workspace, continuation and execution limits. Router tool time budget is configurable from 1 to 3600 seconds (default 60) and applies after restart. It counts cumulative ordinary tool execution per run, excluding model and native-tool approval waiting, with at most nine ordinary calls; medium and large tasks still require Workers. PTC programs include nested tool waits in their execution deadline. The prompt and native/PTC enforcement share the same configured value; remaining budget does not rewrite prompts between rounds. Repeated-output protection is shared by Router and Workers and applies on the next admitted turn without a restart.
- AI approvals: independent review model, review timeout and the switch for automatic review.
- Tools & CLI Apps, Shell execution, Skills: tool availability, shell settings and skill management. Skills includes Installed, Discover and Validation & history; each installed Skill's details contain its **Always inject** switch. Marketplace and trend failures remain visible alongside usable results.
- Web search and MCP: search services and external tool connections.
- Nodes: enroll SSH credentials from Credentials, test connections, execute remote commands and manage persistent jobs. SSH authentication and Agent visibility are edited in Credentials.
- Telegram: personal account binding and server-side notification preferences. Channel setup configures the Telegram bot token and Web transport.
- Backup & restore: complete instance archives, optional extra directories and import preview.

Catalog and provider icons keep image fallback state tied to the current item.
Switching entries or closing a view ignores older image events; equivalent
refreshes retain an already loaded fallback.

Custom theme edits retain the theme list from when editing began. If another
device changes that list before the edit is saved, the save reports a conflict
and retains the draft; reload the latest themes before trying again. Unrelated
preference updates can still be preserved alongside the edit. Queued theme
changes retain their source list rather than adopting a newer revision for an
older list. Each queued preference change receives its own save result.
Theme creation, editing and removal stay locked while a theme save is pending.
Accepted preference database writes settle before cancellation finishes.

Stopping an already accepted conversation-message send waits for its inbox
admission, live wakeup, outgoing-rate receipt and optional reply timer to
settle. This uses the configured outgoing-message limit and adds no settings
field or model concurrency.

Task subagents retain the configured tool switches and network policy in an
independent configuration snapshot. In particular, disabling CLI Apps does
not re-enable them inside a task. Goal waits validate a representable UTC
deadline before supervisory cancellation; omitted wait/continue recaps retain
existing progress.

Task follow-up messages report when their receipt cannot be saved, including
when the task's private session was removed during the write. Do not resend
solely because of that warning. A failed inbox save keeps the message pending;
a failed completion save retains available output as partial and reports the
persistence failure. Removed task sessions are not recreated by late saves.
Successful task-list refreshes also remove retired tasks from the browser;
clearing a conversation or editing its history clears the former task display
immediately. Older reads and stop replies do not restore that retired display.
An older task also cannot write status or deliver completion into a replaced
private task session. On host restart, saved unfinished observations are marked
interrupted without replaying work. A saved “running” record without a live
execution cannot accept follow-ups or report a successful stop; completed-task
stop requests remain harmless to repeat.

- Account, Network & retries, Permissions, Server: network policy, access controls and service settings.

The **Add MCP server** panel sits above the MCP catalog, with custom connection and JSON import actions. Custom MCP servers can be edited from **MCP → Manage → Connection → Edit MCP configuration**. The JSON editor loads the saved configuration, including arguments, environment variables, request headers, tool scope and timeouts. Saving updates the same server and reloads its connection. A connection edit or import that omits tool scope preserves the existing server’s restrictions. Explicit `enabledTools: []` disables all capabilities; `["*"]` selects all, and an omitted scope on a new server retains the default. A malformed scope is rejected before any part of the import is saved. The tool picker counts only names in the current inventory; a retired tool in a saved allowlist cannot make a partial selection become an all-tools grant. JSON import and configuration editors support indentation with **Format JSON**; invalid JSON is shown as an error without discarding the draft.

If an MCP configuration was saved but cleanup failed, settings reports the partial result and keeps the draft. Saving the same connection or importing it again retries obsolete OAuth credential cleanup while preserving authorization for its current URL. After a connection is removed, leftover managed files or credentials appear under MCP with **Retry cleanup**, including after refresh or restart. This explicit action refuses to clean a name that has since been configured again or is used by an enabled plugin. It does not delete a custom user working directory or add another persistence location.

An MCP server waiting only for OAuth authorization is labelled **Needs sign-in**. When local OAuth credentials are removed, the next connection check, reload or reconnect withdraws that server's tools and closes its connection. Other MCP connections remain available. Sign in again to restore the tools. An interrupted reload retains the desired configuration, so a later connection check does not restore servers removed by that reload.

If reconnect cannot restore an available MCP capability, the call returns an
error without retrying the old connection. A changed tool definition or safety
hint also prevents automatic replay with the old arguments; subsequent calls
must use the current definition. Unchanged definitions retain normal recovery.

MCP tool image results are decoded and saved outside the chat event loop. Stop
waits for an accepted artifact write to settle, including a late write failure,
without repeating the remote call. Model-facing results keep artifact paths
rather than embedding the image's base64 data.

Cancelling a connection test during preparation prevents the connection attempt. Local preparation and connection cleanup already underway finish before cancellation is acknowledged.

If a connection changes while its test is running, the old result is discarded and settings asks you to test again. Its old tool list is cleared so tools discovered from the previous connection cannot be selected for the replacement. Changing only tool permissions or another connection does not discard a valid inspection. A normal connection failure still preserves the last known list.

An explicitly selected HTTP/SSE connection uses its URL even if the configuration still contains an old local command. Settings checks the selected transport's dependencies, matching the runtime. Without an explicit transport, a command selects stdio; otherwise a URL ending in `/sse` selects SSE and other URLs select Streamable HTTP.

Browser sign-in validates the callback address before saving a connection. Cancelling while that save is underway waits for the save to settle and prevents a new authorization flow. If configuration changed before sign-in was interrupted, its pending-runtime indicator remains until successful hot reload or restart. Signing in again without changing the connection does not add a restart requirement; applying the sign-in change does not clear other settings' pending restart indicators.

See [Home and workspaces](home-and-workspaces.md) for file ownership and [memory](architecture/memory.md) for retrieval and maintenance behavior.

Cron schedules with an explicit timezone follow that timezone. Legacy or edited
cron schedules with an empty timezone follow the server's detected IANA timezone,
including daylight-saving changes. The scheduler and settings validation use the
same calculation; an empty timezone does not freeze today's UTC offset. The
Agent's newly created cron tasks continue to default to its configured timezone.
In local-trigger details, **Copied** refers to the command actually copied;
changing the displayed command or receiving a late copy result does not mark the
replacement command as copied.

## Channels and remote browsers

Duplicate filtering preserves exact text, including code indentation. Attachments,
buttons and structured events are not discarded merely because their caption
matches an earlier reply. Telegram splits messages using displayed text after
HTML entity parsing, including table expansion; escaped HTML characters alone
do not require more messages.
Long Telegram replies also keep their line context across message boundaries.
Symbols such as `>`, `#` and list markers exposed by a length cut remain part of
the original line; ordinary newlines still enable Markdown formatting. Streaming
previews and retries keep the same remaining source so later updates do not
silently insert a newline or drop a continuation prefix.
Rendered tables retain empty rows and empty first or last cells. A line that only
resembles a table separator does not turn following text into a table by itself.

Only Telegram and Web (WebSocket) channels are bundled. Authenticated users can install optional support and manage Skills from local or remote browsers, including behind a reverse proxy. Enable and configure them under Settings → Channel setup. Changes save when you finish editing; Enter saves credentials without enabling the channel. Failed saves keep the draft open. Checking a connection does not enable it.

Channel integer fields require whole numbers; floating-point fields require
finite numbers. Boolean values are not accepted as numbers, and fractional port
values are rejected instead of silently rounded or truncated.

Checking a channel uses the current server instance's saved credentials and
proxy, with any edits supplied for that check. Blank secret inputs keep the
saved value; explicitly removing a secret tests the cleared value without saving
it. Switching connection views retires earlier checks and save callbacks, even
if you return to the same connection, so their old results or busy state cannot
take over the current view.

Required channel fields use their declared types: a required switch must be on,
and empty lists, empty JSON objects and whitespace-only text are incomplete.
Optional switches retain explicit off values. A switch without a declared
default starts off; inheritable fields keep their separate default option.
Alternative credential groups point to the group needing the fewest fields, preferring the one already most
complete on a tie. Server checks highlight the full nested field path.

Web listener configuration is checked locally before a settings save or enable.
Invalid values leave the saved file unchanged. Listener ports accept 0–65535;
zero requests an ephemeral port. Public WebSocket URLs must have a usable host
and valid port, and keep the configured WebSocket path. A trusted proxy assertion
header must be a valid HTTP field name; routing headers remain disallowed.
Expanded IPv6 wildcard addresses and an empty bind address require authentication
just like `::` and `0.0.0.0`. Empty numeric drafts keep their saved values in both
connection checks and writes.

An enable or disable response can save configuration while failing to apply the
running channel. Channel setup shows that failure and its reason instead of
reporting success, while retaining the confirmed save. A channel waiting for a
restart is shown as pending; unrelated pending restart settings do not override
a confirmed live application.

Channel status keeps saved enablement separate from the observed runtime. A
failed stop does not turn a still-running adapter into an off switch, and a
partly failed multi-instance channel still shows its live instances. Active
channels remain in the enabled filter so they can be stopped again. Pending
restart settings, incomplete credentials or missing dependencies restrict
enabling, but do not prevent stopping an already loaded adapter. Required WebUI
and in-flight-operation guards still apply. Instance edits acknowledge a saved
configuration even if live reconfiguration fails, while displaying that failure.

Background channel catalog reads cannot replace an acknowledged change from the
catalog or a channel detail panel. Polling pauses during catalog mutations.
Action failures stay visible until dismissed or replaced by a new action;
recovering a read failure only clears the read error. Closing the Settings surface retires
its pending callbacks: an already submitted installation can finish on the
server, but the old page cannot start the next dependency installation or
publish late restart notices. Multi-step installation keeps each confirmed
result if a later step fails. CLI catalog retries also wait for an active
installation instead of reading concurrently with it.

Settings initialization reads also respect accepted saves immediately, including
when a save and an older read finish in the same browser update. The saved
snapshot and the workbench cache keep the confirmed configuration. Usage-only
refreshes do not invalidate configuration reads. Initial-read recovery cannot
hide an explicit settings-save failure; a usable replacement snapshot clears
only an obsolete read error. CLI installation errors remain
separate from catalog-read errors, so a later refresh cannot hide a failed
installation check; dismissing the Apps notice clears both kinds of error.

Installing missing channel dependencies requires a server restart before that
channel can use the newly installed code. This applies to both Install support
and an Enable action that installs dependencies. Saved credentials remain saved;
further enable/configure requests cannot bypass the restart. Disabling an active
channel is still allowed. Channels whose dependencies were already present can
continue to apply supported changes without restarting.

For Telegram, supply a bot token in Channel setup. In Settings → Telegram, generate a PIN and send `/bind <PIN>` to your bot in a private chat. The eight-digit PIN expires after two minutes and can be used once. Pairing checks and PIN renewal run while the page is visible; they pause in the background. A failed check or renewal shows the error and a retry control. Refresh PIN invalidates the previous code; Cancel revokes it. A bound account is the only Telegram account admitted to Cirno; group chats, group commands and group callbacks are ignored. Disconnect revokes the binding and any outstanding PIN. Connection errors appear in channel status.

Telegram private input and Heartbeat use the dedicated Router conversation. Router replies can be mirrored to the bound account, including proactive replies originating in the browser or background work. Inbox Actions, Reports and System notifications use independent server-side switches; browser notification preferences synchronize with the owner profile, while notification permission must be granted separately in each browser. Ordinary replies are not added to Inbox. Pending Inbox notifications enter the existing durable delivery outbox, so a restart does not discard an admitted notification. Notifications are rechecked against the current binding before sending. To include an action button, set the Web UI address to one reachable from your phone; the button opens the corresponding Inbox category and conversation. Unanswered questions include their suggested answers in the Telegram notification. Answer and approve in the authenticated Web UI. For Web, configure the listening address, port, authentication, optional public WebSocket address and TLS certificate paths. A remote browser uses the Cirno server and needs no Cirno client installation.

Authenticated remote sessions can select Full Access. It applies to files and commands on the server host. Stop a running conversation before changing its access mode. Use authentication and the deployment's TLS or reverse-proxy configuration when exposing a server outside the local machine.

Permissions → Default access sets the initial permission for a conversation.
**Use tool policy** follows **Workspace restriction**: enabled confines files and
commands to the working directory; disabled allows Full Access. A conversation's
saved access choice takes precedence over this default.

## Providers, models and balances

Settings → Providers manages connections, credentials and optional balance queries. Settings → Models manages model presets and their call order. A provider can serve several model presets.

Dragging the model call order belongs to the pointer that started the gesture;
another finger cannot finish or replace it. If the saved order changes while
dragging, or another operation locks the controls, the preview is cancelled
without submitting an obsolete order. Equivalent refreshes retain the gesture.

Model-list queries honor the provider's proxy switch. Missing environment
variables in an explicitly configured endpoint or credential stop the query;
they do not redirect it to the default endpoint or submit a partial key. Query
errors show a safe explanation with Retry, including missing addresses and
credentials, while manual model-ID entry remains available.
OAuth model lists keep signed-out sessions separate from stored credentials
that lack an account ID. Refreshing a token for a known account still reuses
that account's catalog cache. The owned OAuth catalog queries and Responses
HTTP/WebSocket transports use their explicit proxy selection, rather than
silently adopting system proxy variables. GitHub Copilot's model requests,
access-token exchange and settings device sign-in all use the provider's saved
proxy switch. Disabling it prevents fallback to system proxy variables. Direct
device-login callers can supply an explicit proxy too. Cancelled device login
stops before opening a connection or beginning the next account request;
an already outstanding request still waits for its HTTP timeout. Other external
SDK sign-in and token refresh retain their separate networking behavior.
Automatic direct-OpenAI routing and inferred OpenRouter headers use the actual
hostname. A vendor name appearing in another hostname, a URL path or username
does not select that vendor's behavior. Explicit provider selections retain
their declared metadata. Absolute local DNS names such as `localhost.` keep the
local connection policy.

OpenAI-compatible custom request headers replace automatically added headers
without regard to capitalization, including attribution and session-affinity
headers. Anthropic requests also honor the provider's shared-proxy switch;
disabling it prevents implicit routing through system proxy variables.
Changing a saved header's capitalization also preserves its masked secret.
Query parameters and JSON body keys retain their exact-key matching rules.
Secret masks retain an existing value at the same setting path. A mask without
an available saved value is rejected before saving, including nested request
bodies, balance keys and the embedding API key; it is not converted to null.
To clear a value, remove its entry or use a supported explicit null. Capability
detection applies the same rule before constructing a provider and restores
masked model fields only when the saved provider/model identity matches.

Per-model request parameter editors keep drafts and save feedback with the
selected preset. Their Save action accepts one submission at a time; failures
retain the current draft for retry. Selecting another preset starts those fields
from that preset's saved values, including when both saved values are empty.

Fast mode and hosted-search switches preserve other request-body parameters.
While the body editor contains invalid JSON or a non-object value, those
switches stay disabled so they cannot replace an unfinished draft. Correcting
the body restores them.

Responses failure events keep the provider's machine-readable cause, retry
delay and reported usage. Known rate-limit and server-error codes receive the
corresponding message even when no HTTP error status was supplied; quota errors
remain separate and do not cause repeated retries. Upstream error messages are
not echoed into the Responses failure notice. A failed response does not advance
the conversation's provider continuation state.

New-preset inputs stay locked while creation and its call-order update are in
progress. Repeated submissions do not start another capability check or creation.
A failed creation keeps the draft available for retry. If creation succeeded but
the call-order update failed, the saved preset remains available; the error
identifies that separate failure. Enable the preset from its list to retry
without creating another one. The update extends the order returned by creation
and skips a second update if that response already enabled the preset. Errors
appear in the model editor while it is open and in the model list when closed.
New drafts initialize generation settings, reasoning-history policy and idle
consolidation overrides from the primary preset, rather than the last preset
viewed. Empty consolidation overrides continue to inherit the global settings.

Image/video detection results belong to the model and request settings being
tested. Leaving that editor retires the pending result and releases its
waiting indicator; it cannot update another preset opened later. A current
detection failure remains visible and can be retried explicitly.
Server detection follows the selected request API, including explicit model
overrides. If one detection fails, its other pending requests are cancelled and
finished before the connection is closed. Repeated cancellation still waits for
connection cleanup. Configuration errors identify the file used for that check.

OpenAI Codex and GitHub Copilot browser sign-ins are stored in `state/providers/<provider-id>/`. They are included in instance backups. New instances start signed out; another application's CLI login does not sign them in automatically. The 0.1.6 importer copies existing SDK login files into this directory.

xAI's loopback callback rejects missing or mismatched OAuth state without consuming the pending sign-in result, so the matching callback can still complete. Remote sign-in accepts either an authorization code or the complete callback URL; a pasted URL must match the current callback address and OAuth state. Correctable pasted-input errors retain the pending settings flow for another submission. A successful token response must include a nonempty access token before it can be committed.

Sign-in polling and pasted authorization responses share one completion queue.
A failed request stays visible with Retry. Closing sign-in cancels its server
flow; if cancellation fails, the dialog stays open for retry. A cleanup failure
after leaving Settings appears as a persistent notification with Retry and Close.

Each provider and model has a stable ID, separate from its display name. Newly created entries receive generated IDs; built-in providers use IDs such as `deepseek`. Configuration dictionary keys are IDs. Model tools and conversation selections reference model IDs, so renaming a model leaves active conversations, fallback order and approval model selections unchanged. The upstream model identifier is a separate field, such as `deepseek-chat`.

Balance queries are disabled until configured. Set a complete balance endpoint and select DeepSeek's balance format or a custom JSON response with a JSON Pointer to the amount (for example `/data/balance`) and currency. The endpoint may use a different host from the model API. A separate balance API key is optional; leaving it blank uses the provider key. Refresh queries manually from the provider's balance panel. Balance settings do not change model routing or invalidate its runtime cache.

Balance queries follow the provider's proxy switch and ignore system proxy
variables when it is off. Endpoints require a valid nonzero port if specified
and cannot include user information, even an empty username. Addresses expanded
from environment variables are checked again before a request; invalid resolved
URLs return a safe error. Numeric JSON amounts retain decimal precision.
Refreshing or saving cannot submit duplicate operations while the same action
is pending. Older reads and save callbacks cannot take over a replacement
configuration or browser login. Saving also retires older reads when a new
secret has the same masked display value. Draft fields stay locked during save;
failed saves keep their draft and error for retry, independently of read errors.

## Saving settings

Runtime settings save automatically. Switching a settings category, leaving the page or closing its workbench tab waits for pending writes, including edits made before the autosave delay expires. A failed save keeps the page open with its draft and error so you can correct, retry or discard it. Switching workbench tabs and browser Back/Forward do not ask whether to restart. Settings keeps its saved-change notice and manual Restart action until the restart requirement is resolved. Restart requirements use the saved configuration: live prompt edits do not keep a restart pending, while rotating an embedding API key does.

Network safety can save the local-service flag and default conversation access
together. It validates existing preference data before writing and restores the
previous file contents after a caught save failure. If restoration also fails,
the error names the affected files and states that some changes may already be
saved. The draft stays available for correction or retry.
If a failed restoration leaves a restart-sensitive value changed on disk,
Settings retains its restart requirement instead of reporting it as unapplied.

Accepted network-safety and web-search saves finish their file work and record
restart requirements before propagating request cancellation. Reconnecting to
Settings therefore retains the saved-change notice. Restoring the local-service
flag to its original value clears its restart requirement; changing the live
default conversation access independently does not keep a restart pending.

Ordinary model/provider edits keep the disk save and live runtime refresh
together through request cancellation. Runtime-setting saves also finish their
restart bookkeeping before releasing the request. Existing admitted turns retain
their captured settings. OAuth sign-in keeps its separate cancellation flow.
Home-file writes finish before cancellation is propagated; a file removed during
reading is treated as missing, and submitting its old revision returns a conflict
instead of overwriting it. Home-file editing rejects directories and named pipes
at lookup rather than reading them as profile text.

Settings → Memory library exposes the shared-memory injection budget and index scan batch alongside the Home memory file and index status. Settings → Tools & CLI Apps includes the CLI Apps master switch, so a disabled tool can be re-enabled from the interface. Idle consolidation trigger and retention percentages accept fractional values.

File edit previews and patch dry runs do not create Skill history versions.
Conflicting edit selectors and ambiguous matches fail explicitly. Edits preserve
untouched mixed LF/CRLF line endings. If a write succeeds but its subsequent
Skill history update fails, the result states that the contents were saved;
inspect the file rather than repeating the write. File preview and Skill-history
work runs outside the service event loop, while cancellation still waits for
accepted file work to settle.

CLI Apps are shown as ready only when their installed command is available.
If installation or update completes but the command is missing, Settings shows
the verification error and retains the installation record for repair or
uninstall. Failed uninstall or command checks also remain visible as errors.
Automatic CLI App Skill installation and removal preserve unrelated user-created
Skill folders, including folders that happen to use the same name.
CLI management controls wait for the current operation to finish before another
is submitted. Background directory refreshes cannot replace a completed action
with an older response, and catalog polling pauses while the page is hidden.
Switching away from a kept-open Settings tab also pauses its periodic reads and
preserves its drafts. The global unread-badge and notification refresh remains
available across tabs. Catalog refresh tasks belong to the running instance:
maintenance reports busy while refresh work is pending, and shutdown drains accepted cache
writes before returning.

Inbox pages keep their notification rows, unread counts and delivery cursor
consistent. Switching notification categories or reconnecting discards older
page responses. Inbox actions also reject duplicate clicks while an operation
is pending. Old approval notices whose source conversation was cleared or
deleted are unavailable; unfinished decisions can be retried only for their
original conversation version.

## Fixed Skills and memory files

Settings → Skills → Installed → open a Skill's details → **Always inject** includes its complete instructions in Router and Worker system prompts, including transient Worker subagents. The switch saves automatically and applies on subsequent turns. Existing selections are retained. Availability and the separate **Use skill** switch still apply: fixed injection does not enable a disabled Skill or install missing requirements. A selected but unavailable Skill can be unselected in its details. Skills declaring `metadata.cirno.always: true` remain automatically included when enabled and available; the injection switch then shows the author declaration and cannot override it. This selection is shared across conversations; internal consolidation and other maintenance do not receive owner-selected Skills.

Settings → Memory library → **Fixed memory files** selects additional UTF-8 text files under Agent Home's `memory/`, for example `memory/workspace/STANDARDS.md`, one relative path per line. `memory/MEMORY.md` already has its own injection and is not added twice. **Fixed memory files budget** controls the combined extra excerpt budget, independently of the MEMORY.md budget, and divides it among selected files. A selected missing, unreadable or escaping symlink produces an explicit error; correct the setting or restore the file. Only select files you want shared with all Router and Worker conversations.

These fields save automatically and apply to the next fresh conversation input without a restart. Unchanged selected Skills have deterministic ordering. Memory snapshots enter fresh input only when contents or selections change; existing messages and the system prefix remain intact. Long files are excerpted within the configured budget; the Agent can read their full contents through file tools. Editing Skill selections intentionally changes the system prefix on the next turn.

The configuration keys are `agents.defaults.always_skills`, `agents.defaults.memory.context_files` and `agents.defaults.memory.context_files_tokens`. Both the shared-memory budget (`agents.defaults.memory.context_tokens`) and the fixed memory files budget accept 256–32768 tokens; each defaults to 2000.

## Context consolidation

Task checkpoints, durable learning and supported Skill improvements are produced in the same model request. Results are saved before task execution continues. There is no separate model, Dream schedule or idle Dream task. Additional references stay at the request tail for cache reuse. Configure learning, maximum updates, reference characters and the shared output/reasoning budget on this page. Disabling learning keeps context checkpoint generation enabled. Older compaction generation settings migrate to `agents.defaults.consolidation`; an old Dream enabled flag becomes `consolidation.learn`, and old scheduling/model/iteration options are retired when configuration is saved. `/consolidate` is the manual command; `/compact` and `/dream` remain hidden compatibility aliases.

Settings → Context consolidation configures inactivity and two percentages of the active model's context window. Defaults are 15 minutes of inactivity, a 20% trigger and 5% recent-context retention. Idle consolidation requires both inactivity and the usage trigger. A zero timeout or trigger disables it. Model preset advanced options can override either percentage; an empty value inherits the global value. Set each model's context-window capacity correctly for meaningful percentages.

Retention must be below a nonzero trigger. Consolidation summarizes older context while retaining complete recent turns and paired tool calls/results within its budget. Counts are estimates until a subsequent provider request reports actual usage. Context-window pressure during execution is a another trigger of the same flow.

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

Changes apply to the next turn without restarting. A running turn keeps its captured prompt, including during compaction. Shared additions precede the role-specific addition, after the built-in instructions and profile context. They customize behavior within the Harness contracts: role permissions, Router delegation and execution budgets remain enforced. Consolidation reuses the captured conversation prefix; heartbeat decision requests do not receive these conversation additions.

The corresponding configuration keys are `agents.defaults.system_prompts.shared`, `agents.defaults.system_prompts.router` and `agents.defaults.system_prompts.worker`. The same settings page also edits `SOUL.md`, `WORKER.md` and `USER.md`; those profile files remain separate from these additions.

## Router heartbeat pause

The Router conversation header includes **Pause heartbeat** / **Resume heartbeat**. Pause takes effect without a service restart and persists across restarts and browser sessions. It prevents new scheduled heartbeats and retires queued heartbeat inputs before model execution. A turn already running can finish. Owner messages, worker reports and separate automations keep their normal behavior. The global Heartbeat switch and interval remain in Settings; disabling that switch also disables the header control.

## Scheduled and local-trigger inputs

Saved automations retain their destination conversation and channel routing, but
not the coordination message identity or work-report markers of the input that
created them. Each cron invocation or local-trigger delivery has its own identity,
so repeated reminder text does not collide with the creating message's receipt.
This normalization also applies when dispatching older saved tasks; recreating
them or changing their reminder text is unnecessary. Previously failed executions
remain in history and are not automatically replayed. Genuine duplicate
coordination messages retain their existing deduplication behavior.

## Command duration

Settings → Shell execution separates the default command duration from **Maximum requested command duration**. Zero in the default means no time limit for commands without an explicit duration. Zero in the maximum removes the ceiling on requested durations, and allows an explicit zero for no time limit. A positive maximum still restricts explicit model requests to 1 through that maximum. These values survive automatic saves and reloads. Local `shell.exec` and remote `nodes.execute` share `tools.exec.max_runtime` (default 3600 seconds) and `tools.exec.max_runtime_limit` (default 86400 seconds). Restart Cirno after changing these settings. Both tools accept `max_runtime` for a single call, with `timeout` as a mutually exclusive compatibility alias. The Nodes command dialog uses the same configured default and waits for the server result instead of imposing a separate 130-second browser deadline. Silence detection, local sandbox/environment settings and `shell.session` are local Shell features; SSH connection timeouts, job polling and detached `nodes.start` jobs retain their own lifecycle. The Router's cumulative small-task tool budget remains separate; increasing command runtime does not extend that delegation boundary.

## Nodes

Settings → Nodes manages SSH connections, host fingerprints, direct commands and persistent jobs. Supply host, port, SSH username, remote working directory and either key or password authentication. A key path refers to a file on the server. A blank password while editing preserves the saved password. SSH credentials are encrypted in the credential vault and omitted from connection listings; Node enrollment and job tracking use instance state. Saved host keys or the server’s `known_hosts` verify the server; compare scanned fingerprints before saving them.

SSH connection details and Agent visibility live in **Credentials**. Enrollment in **Nodes** is optional. The shared SSH startup form stores the remote working directory, an optional initialization script path and environment variables such as `CUDA_VISIBLE_DEVICES=2`. Variables are exported, the shell changes directory, and the initialization script is sourced in that same Bash shell before the command. `~/` resolves on the remote host. A failing directory or initialization step stops execution and reports its error. Direct commands, new interactive Terminals and submitted jobs share this setup; inspecting/stopping jobs does not rerun the initialization script. Updating settings does not retroactively change an already-open Terminal.

Agent Node listings and operation-review evidence expose connection metadata, authentication-presence flags and environment variable names. They omit passwords, private-key paths and environment values. Agent job listings contain status metadata; reading a job's output requires an explicit SSH status operation with the usual access review. Owner forms retain their complete editable settings. Marking a credential Agent-visible permits using it through its ID, managing it and explicitly reading its stored value with `credentials.read`; metadata-only lists never reveal it. Hidden credentials remain unavailable to the Agent. Explicit read results are hidden in activity and durable history, including restart checkpoints and archived evidence; the running Agent can still use the value. After a turn or restart it must read the credential again if needed. Oversized values are rejected without a plaintext spill file; raise the tool result character limit before reading them. If the UI client connection is replaced while a Node operation is pending, the new connection starts with fresh operation and credential state; late responses from the old connection cannot unlock or overwrite the new operation.

Execute command runs a command and returns output without creating a job. The `nodes` tool namespace also lists connections, transfers files and starts, inspects or stops persistent jobs. Job output, PID and exit status stay on the remote host; tracking records stay in `state/instance.sqlite3`. No remote Cirno daemon or client is installed. Remote execution requires Bash and OpenSSH; persistent jobs also require `setsid`. An uncertain submission exposes its job ID for inspection before resubmitting.

## Service lifecycle

Settings retains Restart. There is no in-app upgrade platform or terminal configuration wizard. The CLI Apps catalog remains available for installing command-line integrations. Source installations upgrade by updating the checkout, rebuilding the browser assets and reinstalling the package; container installations rebuild or pull a published image.

## Account password

Settings → Account shows the registered owner and changes the browser-login password. Enter the current password, a new password and confirmation. The same rules apply as registration: at least ten characters, including an uppercase letter and a symbol. Successful changes keep the current browser signed in, revoke other browser sessions, invalidate server access tokens and reconnect Web UI sockets. Other browsers must sign in again. Password hashes and sessions live in `state/webui-auth.sqlite3`; passwords are not saved in `config.json`. Signing out revokes that browser session’s API and unused connection tokens and closes its live sockets, including attachment and backup-transfer capabilities. Other logged-in devices remain connected. Shared-token authentication has no registered browser account and continues to use the existing server authentication settings.

## Conversation controls and access review

Startup recovery ignores unusable saved recovery headers while continuing to
inspect other conversations. Unknown or non-text checkpoint phases enter the
review-only recovery path; they do not run tools or resume a model automatically.

Question navigation excludes display-only supervision, subagent and continuation
inputs; those messages remain visible in the conversation. Navigation retains
answer boundaries across reasoning segments without loading their bodies, so
eligible older questions can still be matched to saved answers.

Completed answer and reasoning snapshots replace their stream's provisional
text, including an explicitly empty snapshot. Older records without a text
snapshot can still use their accumulated fragments. Live projection and paged
replay follow the same rule; a late reasoning snapshot stays on its existing
row after answer text has started.

Late completion records finish only their own turn. Replayed or repeated ends
from an older turn preserve the current answer, reasoning and tool-activity
segment, including the wire markers that reject duplicate answer fragments.

Settings → Goals & execution configures the default workspace, continuation text and its visibility. The workspace setting (`agents.defaults.workspace`) accepts an absolute server path, including `~/…`. Use the Restart action in Settings to apply it to new conversations. Saving this setting does not move existing files or change existing conversations' working directories; projects can still supply their own default directory. A saved conversation continues to show its working directory as a locked selector. Conversation storage is instance-wide and remains available after changing the default workspace and restarting.

Server restart preserves completed model segments and tool observations from all rounds of the in-flight turn, including finished calls in a partly completed batch. They are appended with the recovery checkpoint in the same session transaction. A call still in progress is marked interrupted; its external outcome may need inspection. A model stream interrupted before completion cannot resume its hidden inference state. After restart, Continue resumes from the saved execution boundary; active/waiting Goals respect this recovery state and do not wake or consume continuation rounds before confirmation.

Stop preserves context and suspends a Goal in resumable `stopped` state; it does not mark the objective completed or cancelled. Explicit Goal resume and conversation Continue share interrupted-turn recovery and preserve progress/counts. Repeating an admitted continuation returns `resuming`, `already_queued` or `already_running` without queuing another request. Transient retry/recovery health stays inspectable on the Worker; only terminal failures, results and unresolved questions wake the Router. An interrupted conversation shows Continue in the composer’s primary action button while the input is empty; typing changes the button back to Send. Continue or `/resume` starts another model request from saved progress. Recovery failures remain visible as inline text, without a separate recovery action panel. New conversation drafts accept `/temporary on|off`, `/ptc on|off` and `/model <preset>`. Creation-only commands are omitted from established conversations' command menus. `/access default|review|full` selects the permission mode. Model display names are unique ignoring case. `/model` accepts a model ID or an unambiguous display name; tools use model IDs.

AI review keeps Default restrictions and reviews blocked operations independently of Cirno memory. Settings → AI approvals selects a saved model preset (or the conversation model), sets a 1–300 second review timeout, and enables or disables automatic review. These settings live under `agents.defaults.approval` as `enabled`, `modelOverride` and `timeoutSeconds`. Disabling review sends blocked operations to the owner for approval. Timeouts, unavailable review models and uncertain cases also appear in Inbox → Actions. Each approval covers one exact operation; it does not grant Full Access. AI can make unsafe decisions, so this mode displays an explicit warning. See [operation review](architecture/access-review.md).

Message action buttons and local timestamps remain visible below each message on desktop and mobile. Copy is directly available; edit is available on idle human messages and branch on completed assistant answers. Completed activity keeps a direct **Worked…** disclosure above the answer, without an action menu. Context changes do not undo previous file edits, commands or external actions; tool history triggers a warning. Editing replaces the original message bubble with a multiline input and Cancel / Save and send controls, retaining its attachments. Enter adds a line; Ctrl/Cmd+Enter sends and Escape cancels. The revised request replaces later conversation context. A failed save keeps the draft and shows the error in place. Switching conversations closes the editor. `/clear` resets only the fixed Router context through its dedicated control.

## Mobile keyboard, reconnection and refresh

When the browser needs the legacy clipboard method, copying restores the prior
editor focus and text selection without scrolling it into view. A deliberate
focus change made during copying is retained.

The application fits the visual viewport on touch devices when the on-screen keyboard opens. Login and registration forms scroll within the available height; chat composers move above the keyboard while retaining their draft and focus. Touch text fields use at least 16px text to avoid focus-triggered zoom. Manual pinch zoom remains available.


Returning to the foreground checks the WebSocket connection and reloads the server's conversation state, including reasoning and tool activity missed while the browser was suspended. A stale connection reconnects through the normal authenticated path. The top-right refresh button reloads the page in desktop browsers and installed mobile Web apps, including iPhone Home Screen apps. Reloading the page does not stop the server's task or send the previous prompt again.

Reconnect hydration includes an inactive Goal snapshot when the Goal has finished or no longer exists, clearing any older Goal cached by the browser. Answer and reasoning buffers belong to their individual turn, so a delayed completion from an earlier turn cannot mix with or discard a newer turn's pending transcript. Connection cleanup finishes draining its writer and removing subscriptions even when cancellation is repeated.

Optional background title generation only updates an existing display conversation. If that conversation was removed before the title request starts, the task ends without calling the model or recreating it. Deletion during the request and an owner's manual title remain protected by the destination's current generation and metadata checks.

## Long tasks and embeddings

See [Model context and long-running work](model-context.md) for per-model reasoning replay, active/idle consolidation, checkpoint generation and visible progress. See [Memory retrieval](memory-retrieval.md) for local CPU and external API embeddings. Both vector modes remain optional; BM25 is available without an embedding service.

## Browser file uploads

Composer attachment removal, clearing and draft restoration take effect before
the next attachment operation, including several actions in one browser event.
Removing an attachment or closing its composer before encoding starts avoids
that queued work. Pasting attachments keeps accompanying plain text; dropping
unsupported files does not navigate away from the draft.

Settings → Server → File uploads controls the per-file image/document limit, per-video limit, and combined image/document size per message. Values are in MiB (1,048,576 bytes). Defaults are 6, 20 and 24 MiB respectively; video has its own allowance of one video per message. Local file references do not consume the upload byte allowance. Files are streamed to disk, and staging capacity accommodates the configured batch size.

These settings are stored under `server.uploads` as `maxFileMb`, `maxVideoMb` and `maxTotalMb`. Restart the service and refresh the browser to apply them. A reverse proxy's request-body limits must also permit the intended upload size; increasing Cirno's limits does not change proxy configuration.

Failed workspace admission leaves upload references staged for retry while their
connection and staging lifetime remain valid. Uploads are checked again after
workspace admission, then protected from staging cleanup before their paths are
written into message history. A disconnected or expired upload is rejected;
the message is not dispatched with a missing attachment.

Cancelling while a new conversation's workspace is being saved waits for that
write to settle before cleaning up its unused creation. A failure updating recent
projects retains the draft workspace choice. Cleanup preserves saved history and
later setting changes, including a user-edited conversation title. Current saved
workspace permissions take precedence over older drafts, and private temporary
conversations remain restricted even if the normal default allows full access.

A saved conversation retains its original directory and access mode when that
directory is unavailable; it does not fall back to the default workspace's
permissions. Malformed explicit workspace policy rejects file access and task
admission. An owner can explicitly save a valid access setting for the same
bound project to repair a damaged mode. An attachment-free `/stop` from the
authenticated WebUI remains available without saving or replacing workspace
policy or recent-folder preferences.

File tools constructed with only an explicit `allowed_dir` keep that boundary;
it is not discarded when no default workspace was supplied. Normal
conversation tools still follow the selected workspace and access mode.
Bundled Skill fallback reads must also pass read authorization for their actual
destination. These guards do not add a separate settings option.

`tools.file.enable` also gates Python file discovery and content search. Stop
waits for an already accepted search operation to finish its cleanup; an
individual synchronous document parser call must return before that cleanup
can finish. These operations retain the existing search limits and pagination.

Native ripgrep also requires `tools.exec.enable` and an `rg` executable on the
configured execution PATH. Otherwise Python file search remains available when
file tools are enabled. Standalone native search closes stdin by default;
`stdin="pipe"` is an explicit tool-call option for searches that will receive
input through `shell.session`, not a persisted settings field.

Recent folders, favorite folders and the default access mode merge their changes
under the same in-process file lock, so concurrent saves preserve the other
fields. Folder preference writes run outside the service event loop; cancellation
waits for an already-started write to settle.

If conversation history cannot be saved, the browser retains the draft and the
server rejects that submission instead of dispatching it or confirming receipt.
The `/stop` control intentionally does not create an ordinary user-history entry.

Browser buttons for clearing history, restarting and switching models send
silent control commands that require an open connection. These commands are not
queued for reconnect, including after a socket write fails. If a command was sent
but its result was not confirmed, check the current state before submitting it again.

## Usage chart details

Click or tap an Overview or Usage chart bar to keep its details open. Moving the pointer away does not dismiss them. Click the same bar again, click outside the details, or press Escape to close them. Model legend entries use the same interaction.

The Launcher reuses Conversations, Credentials, Inbox, Automations, and Settings.
Terminal, Files, Browser, and Trace open independent tabs. Opening the same file
again activates its existing editor; its preview has a separate tab. Encoded
filename characters such as `%23` stay part of the filename in preview links;
literal URL queries and anchors are handled separately. The editor and preview
share unsaved text; reloading from either view asks before discarding changes.
The text editor rejects binary content containing null characters before writing,
so a rejected save leaves the original file intact. Drag tabs
or Launcher items to reorder them; on touch screens, hold an item before dragging.
Top tab strips scroll horizontally only. A mouse wheel scrolls tabs left/right;
trackpad horizontal or vertical wheel gestures use the dominant axis without adding
both distances. Touch pans horizontally, while pinch zoom remains available. Each
split group scrolls independently, and reaching a strip edge does not scroll the page.
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

Context consolidation exposes `max_retries` (JSON alias `maxRetries`) in Settings, with default 1 and range 0–10. This is the shared number of additional serial generation attempts, including invalid learning JSON/schema and unwanted tool-call recovery; 0 means one attempt only. It does not control provider-level network retries. Optional learning failures retain their plans and original batches, display incomplete updates and do not veto task-checkpoint persistence. Use `/consolidate retry [source-id]` for explicit recovery, including regeneration of malformed output. Memory's save-retry action replays stored results without making an API request.

### Repeated-output protection

Settings → Goals & execution provides `agents.defaults.output_repetition.enabled` (default `true`), `repeat_count` (default `4`, range 3–20), `max_interventions` (default `2`, range 1–10) and editable `guidance` (1–8000 characters, not blank). New settings apply to subsequent turns; an admitted turn keeps its captured settings.

The guard compares adjacent sentences/lines in model answers and reasoning, and checks `user.message` content before executing a reply batch. Sentence punctuation and newlines delimit blocks; whitespace, case and list markers are normalized. Blocks with fewer than two letters/digits and fenced code are excluded. It checks recent assistant output across automatic continuations; fresh user input resets it. It does not suppress arbitrary similar text or silently discard tool errors.

On repetition, the current model stream closes. Its unexecuted tool calls are discarded, already delivered prose remains, and the configured guidance is appended as an internal system notice. The stable system/history prefix is retained; guidance grants no new user authorization. Only after the interrupted request closes does another request start. Failed correction is bounded across continuations by saved notices. If the correction or execution limit is reached, execution ends visibly, any active/waiting Goal pauses with its existing progress, and its Router receives a blocked report. The owner may inspect the conversation and explicitly continue. Turning the guard off disables these checks.
