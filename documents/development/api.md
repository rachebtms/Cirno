# API versions

All Cirno service endpoints use a major-version prefix. The current prefix is
`/v0/`. Cirno 0.2.9 still uses `/v0/`; a minor or patch release does not change
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

Versioning does not change access rules. Browser account changes use HTTP POST;
Web UI mutations use allowlisted actions over an authenticated WebSocket. Binary
uploads and downloads retain their dedicated authenticated transport.

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

## Model and provider identities

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

## Skill catalog and detail

`GET /v0/webui/skills` lists Skill availability separately from the saved enabled
state. Sources are `home`, `builtin` and `plugin`. Home Skills are independent of
the conversation workspace.

`GET /v0/webui/skills/<name>` includes the original `raw_markdown`, requirements
and supported installation hints. Invalid runtime declarations return
`available: false`, a specific `unavailable_reason` and `requirements: null`;
they are not represented as a successful empty requirements list. Filesystem
read failures remain request errors.
