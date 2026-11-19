# Frontend resource ownership

Browser state belongs to one activation of a view, account, conversation or
resource. An owner key identifies that resource. Leaving owner A for B and
returning to A creates a new activation; callbacks from the first visit must
remain invalid. Updating data within the same activation must preserve selection
and other local state.

## Scope and local state

`ui/resources/useResourceScope.ts` owns activation identity. A scope becomes
current at layout commit; committing a replacement invalidates the previous scope
before passive effect cleanup. A suspended or abandoned render does not retire
the still-committed view. Suspense may also temporarily hide a mounted view;
that view keeps ownership of accepted writes. Actual unmount retires it in
passive cleanup. Same-owner renders and React StrictMode replay retain a usable
scope. `useLifetime` exposes the same predicate for existing callers. Start
external operations from committed effects or event handlers, never during render.

`useScopedState(scope, initialize)` owns the corresponding local state. It returns
fresh state in the first render of a replacement scope. Retained setters from a
retired scope are ignored, including functional updates queued before replacement.
The initializer and updater must be pure, as with React state. Keep related local
fields in one domain state object instead of resetting independent fields in a
view-specific owner-change branch.

These setters protect local state only. Check `scope.isCurrent()` before starting
an external operation or changing shared caches. They do not cancel a network
request, undo a server write or protect another component's state. For example,
logo fallback checks both the URL-list scope and individual image-attempt scope
before changing its shared cache; conversation deletion checks its selection
scope before opening an external confirmation.

The provider-balance editor and directory browser also use scoped domain state.
Their retained field setters cannot modify a replacement account or workspace.
Balance loading separately tracks physical read settlement: saving a new secret
invalidates old data without pretending that the outstanding HTTP read finished.
Directory path/filter changes retain their debounce and per-request cancellation;
an equivalent workspace snapshot preserves the current path and filters.

## Reads and writes

| Helper | Operation contract | State on owner replacement |
| --- | --- | --- |
| `useRequest<T>` | Latest read wins; `assign` and `clear` invalidate outstanding reads. Loading and errors retain the current value. | Idle, no value or error. Old loaders and responses are ignored. |
| `useMutation` | One pending write per scope. Only its acknowledgement may call `onSuccess`; ownership is checked again after that callback. | Not busy, no error. A replacement view may write while an old request settles. |

A write is not automatically retried or replayed by these helpers. A stale
acknowledgement cannot prove that its server operation did not happen. Consumers
that need cancellation, reconciliation or cross-view serialization must define
those semantics at their service boundary.

## Settings workflows

`createSystemSettingsActions` composes the MCP, CLI, feature-installation and
automation domains. Each domain owns its API calls, feedback and restart receipts.
MCP authorization has a separate flow controller because callback completion,
cancellation and polling share an authorization identity.

The domains use `createSettingsActionGate` for synchronous admission and read
fencing. Beginning a write claims its action key and advances the catalog
revision; settling it advances the revision again before releasing the key.
Catalog effects discard a read captured at an older revision. Recreating an
action facade on render must reuse the state's action/revision refs, so two
same-frame clicks still admit only one write. MCP additionally excludes writes
while its authorization flow is active. Workflows keep their ownership checks
before publishing acknowledgements or scheduling follow-up reads.

Catalog reads use `createSettingsReadGate` with the same action/revision refs.
Every admitted read captures its browser token and advances the revision. Only
the newest read for the still-active effect and account may publish data or an
error. Its `isLatest()` settlement predicate is separate: an old account's final
response may end its own loading indicator, but cannot overwrite a newer read's
indicator. Automatic and explicit automation refreshes share one load body.
CLI retry limits, MCP connecting-status timers, channel polling and hidden-tab
policies remain domain-specific.

## Client delivery and subscriptions

`CirnoClient` coordinates connection generations, inbound event ordering,
conversation transcripts, queued frames and the run ledger. Its message-delivery
owner handles acceptance deadlines and rejection receipts without changing those
policies: attachment upload must finish on the starting socket and upload
capability, expired text loses its queued frame, and shell commands are never
queued or replayed. A shared failure-receipt wrapper does not authorize retries.

The notification owner shares observer isolation through `ClientListeners`.
Status and run-status subscriptions receive their current snapshots; other
channels receive live events only. Pure run-observation projection is separate
from the connection, so prompt history and transcript display can recognize
system-command turns without importing the transport coordinator. Public client
methods and message type exports keep their existing entry points.

## Regression coverage

`resource-lifetime.test.ts` covers scope replacement, unmount, returning to an old
owner, StrictMode replay, suspended/abandoned renders, temporary hiding, read
ordering, write serialization and an acknowledgement
that synchronously switches views. `logo-fallback-lifetime.test.tsx` checks that
retired image events cannot poison shared caches.
`conversation-selection-ownership.test.tsx` checks archive/delete confirmations
across owner changes and selection retention during same-owner refreshes.
The settings ownership suites for MCP, CLI, features and automations retain the
cross-domain cases for duplicate clicks, stale polls, late acknowledgements,
restart receipts, authorization and unmounted views.
`settings-read-ownership.test.tsx` checks account-token changes and overlapping
MCP reads in both completion orders. Balance and file-browser ownership suites
check scoped editors, pending reads and retired field setters.
