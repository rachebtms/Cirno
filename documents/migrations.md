# Instance upgrades

Cirno 0.2.4 upgrades instances from 0.2.0, 0.2.1, 0.2.2 and 0.2.3 and imports the published 0.1.6 layout at startup. Stop the
old service and keep the same instance volume and external workspace mounts.
The configuration records the last version as `lastRunVersion`; unversioned
configuration is treated as 0.1.6. Later migrations belong to the startup
migration registry, rather than the Agent's runtime storage code.

The 0.2.0 → 0.2.1, 0.2.1 → 0.2.2, 0.2.2 → 0.2.3 and 0.2.3 → 0.2.4 steps update only the configuration version. Conversations,
profiles, credentials and settings keep their existing data. Configuration
originals and resumable journals stay under `state/migrations/<source>-to-<target>/`.
Instances on 0.1.6 run the registered steps in order. First-use introductions
apply to newly registered instances; upgrades do not reset existing profiles.

Version 0.2.4 adds shared, Router and Worker system-prompt settings through configuration defaults. Existing values are retained. Legacy task checkpoints remain readable in their original visibility scope; a new conversation/Project checkpoint slot is created as needed without rewriting old evidence.

## What changes

- Workspace-bound conversation databases are imported into
  `state/sessions/instance/sessions.sqlite3`, including display history,
  checkpoints, queued inputs and delivery receipts. Changing the default
  workspace no longer changes the conversation store.
- Identical copied conversations are deduplicated. If different histories use
  the same ID, the configured workspace's history keeps it and the others receive
  new IDs and an imported-source title. The workspace identity marker selects
  its active store when historical copies point to the same directory. Stored parent, checkpoint and automation
  references follow their imported conversation.
- Workspace-owned `cron/` and `triggers/` state moves into `state/cron/` and
  `state/triggers/`. Recognized workspace identity markers are removed. Project
  instructions and task files stay in place.
- OpenAI Codex and GitHub Copilot SDK credential files are copied into
  `state/providers/<provider-id>/`. Shared originals remain in place. New
  browser sign-ins and sign-outs affect only this instance.
- Generic channel pairing is retired. Its access store is archived and old
  pairing notifications become resolved System records. Pending tool approvals
  and questions remain actionable. Telegram uses Settings → Telegram to bind
  one personal account with an expiring PIN; existing personal bindings remain.
- Conversation catalog preferences retain pinned/archived IDs, display titles
  and sorting. Old chat-only pane groups are retired; tabs and splits use the
  new workspace host. The original preferences file remains in the migration
  backup. Conversations and their histories are unchanged by this layout reset.
- Existing provider/model IDs and their references remain stable. Models receive
  display names when none were stored.
- An empty `home/memory/.dream_cursor` created by the old Git initializer becomes
  `0`. Its original is retained with the other migration replacements.
- Configured service paths gain `/v0/`: `/` becomes `/v0/ws`, `/api/socket`
  becomes `/v0/socket`, and a custom `/socket` becomes `/v0/socket`. Public
  WebSocket URLs and token-issue paths change with them. External clients,
  reverse-proxy path rules and MCP OAuth registrations need matching URLs.

Accounts, Agent Home, memory databases, evidence, Skills, credentials, attachments
and other instance state retain their existing files. Previously released model
context remains available through its retained evidence; migration does not
regenerate missing reasoning or old archive position indexes.

## Recovery and inspection

Migration prepares and validates replacements before installing them. A failed
preparation leaves the live files unchanged. Installation is journaled; an
interrupted startup finishes its pending replacements before loading
configuration or launching the Agent.

Original files, the replacement journal and an import report remain in
`state/migrations/0.1.6-to-0.2.0/`. An Inbox system notice summarizes completion
and gives that location. Conflicting automation IDs or files stop migration
with their paths, leaving the originals available for resolution. Unsupported
configuration or conversation schema versions are reported at startup.

Back up the full instance and external workspaces before upgrading. To run an
older image again, restore that pre-upgrade backup, including its configuration
and conversation databases. Older layouts should first be upgraded to 0.1.6.

Early preview identifiers `websocket:global` and `websocket:cirno` move to the
Router’s reserved UUID route.
Startup stages conversation keys and structured references together, including
checkpoints, pending inputs, receipts, schedules and related instance records.
Original prose is preserved. Originals and the resumable replacement journal
remain in `state/migrations/router-identity-v020/`. A conflicting existing Router
key stops preparation without replacing live databases. Existing registrations
retain `@cirno`; new registrations choose their initial display name in the browser.
The owner can subsequently change the name without changing the conversation ID.

Offline SQLite replacement retains the old WAL, SHM and rollback journal beside
the original database. Those files must not remain at the replacement path:
committed frames from an abnormal shutdown belong to the original database.
An interrupted installation resumes from its saved migration plan before startup.

## SSH credentials

Startup also moves existing SSH Nodes from `state/instance.sqlite3` into the encrypted credential vault. Node IDs and remote job references stay unchanged. Existing enrolled Nodes retain Agent access; new owner-created credentials default to private and unenrolled. Other records in an older vault remain intact and default to private when the visibility field is added.

Each encrypted record commits before its old plaintext row is removed. An interrupted import retries the same ID, and a conflicting existing credential stops startup instead of replacing either record. Deleted SQLite payloads are erased and the old Node store is vacuumed. Existing external backups are not rewritten.
