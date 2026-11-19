# Instance root, Agent Home and workspaces

The instance root defaults to `~/.cirno/`. Select another instance with `cirno --home /path/to/instance`. Agent Home is the `home/` directory inside that instance. A workspace holds task files and defaults to `workspace/` beside Agent Home. Selecting a workspace does not move the instance or Agent Home.

```text
~/.cirno/
├── config.json
├── state/
├── home/
└── workspace/
```

| Path relative to the instance root | Purpose |
| --- | --- |
| `config.json` | Service configuration, managed through Settings |
| `state/webui-auth.sqlite3` | Owner password hash, browser sessions and setup progress |
| `state/instance.sqlite3` | Projects, Nodes and tracked jobs |
| `state/credentials/` | Encrypted credentials and their matching `vault.key` |
| `state/sessions/` | Conversation history and durable execution state |
| `state/security/approvals.sqlite3` | Independent reviews and one-use owner operation approvals |
| `state/notifications/inbox.sqlite3` | Notification records |
| `state/providers/` | Instance-owned Codex and Copilot OAuth credentials |
| `state/telegram.sqlite3` | Personal Telegram binding and expiring PINs |
| `state/cron/`, `state/triggers/`, `state/delivery/` | Scheduler, local triggers and notification delivery queues |
| `state/logs/`, `state/run/` | Logs and service process records |
| `state/media/`, `state/webui/`, `state/cache/` | Attachments, browser service state and caches |
| `home/AGENTS.md` | Agent-wide workflow instructions |
| `home/SOUL.md` | Router personality and communication style |
| `home/WORKER.md` | Ordinary conversation personality |
| `home/USER.md` | Durable user preferences |
| `state/preferences.sqlite3` | Owner interface preferences, selected theme, paired custom palettes and language; synchronized across devices |
| `home/HEARTBEAT.md` | Periodic background instructions |
| `home/memory/MEMORY.md` | Shared long-term overview |
| `home/memory/` | Scoped knowledge, original evidence, revisions and memory databases |
| `home/skills/<name>/SKILL.md` | Installed and learned Skills |
| `home/skills-history/` | Retained Skill versions |
| `home/prompts/dream.md` | Retained legacy prompt; no longer executed by unified consolidation |
| `workspace/` | Default task directory; conversations may select other directories |

A project's own `AGENTS.md` supplies project instructions in addition to Home instructions. Projects have independent IDs and can share a working directory. Conversation histories remain separate when projects or directories change. Conversation storage belongs to the instance under `state/sessions/`; changing, copying or moving the default workspace does not select another conversation database. Workspaces do not need identity markers. The fixed conversation database is `state/sessions/instance/sessions.sqlite3`; startup imports v0.1.6's workspace-bound databases into it. See [instance migration](migrations.md) for ID conflicts, retained originals and recovery.

Large tool outputs are saved under the active workspace’s `.cirno/tool-results/`.
References use immutable content-specific filenames, so reused tool-call IDs
retain their earlier results. These files remain until you remove them; changing
workspaces or starting more conversations does not prune existing references.
Include external workspaces when backing up this evidence.

Bundled Skills are part of the application. Home Skills override or extend them through the loader. File tools expose supported Home resources according to their access policy; consolidation has restricted, evidence-checked document updates, while ordinary execution does not directly rewrite shared profiles. The user can edit profiles through Settings. Directory separation expresses ownership; Full Access can still access files outside the workspace.

Running tools and prompt builders retain their instance ownership. Memory reads,
writes and consolidation use their captured Agent Home. Search reloads its own
configuration file; consolidation notifications use its state directory.
Node tools use the state directory beside their captured
configuration, which need not share a parent with Agent Home. Skill discovery,
validation and retained versions use the same captured Home. Profile instructions,
first-introduction guidance and its recovery completion check also keep that Home.
Selecting another instance later in the same process does not redirect these
existing objects or alter their prompt prefix. Subtasks inherit these paths when
their owner is created rather than selecting the current global instance later.

The WebUI gateway captures Agent Home separately from its configuration path.
Profile editing, memory actions, Skill catalogs, history and marketplace operations
keep that Home even if the process later selects another instance. A configuration
file outside the instance does not relocate Home. Marketplace lookups annotate
installed Skills against the same captured Home after their response arrives.
Plugin enablement is separately bound to the captured configuration. The same
binding reaches main and isolated-task prompts, Skill catalogs and installation
checks, and file-tool reads of plugin resources. A global configuration change
does not add or remove plugin instructions from those existing owners.

The profile and long-term overview editors keep each opening's content and
revision together. Changing connections or files retires their old read/save
callbacks. A failed opening cannot reuse an earlier revision, and a late save
acknowledgement cannot overwrite a newer opening. Text editors admit one save
at a time and retain the draft when a save fails.

Marketplace search drafts and installation confirmations belong to their current
connection and selection. Leaving and returning starts a fresh view; an earlier
confirmation cannot install a different selection, and a retired search action
cannot cancel the current query's debounce. Ordinary rerenders retain the same
service and loaded results.

Installed Skill details and history validation follow the same connection
lifetime. A delete confirmation belongs to one Skill and one confirmation
opening: cancelling it or choosing another Skill retires that confirmation.
An accepted deletion remains locked until its result is known; a failed deletion
keeps its confirmation available for retry. History validation results belong to
the exact submitted name draft, so changing a name away and back does not restore
an older in-flight result. Changing the name does not start an overlapping
validation.

Skill enable/disable and deletion perform their disk work off the gateway event
loop. Accepted state changes finish their commit and publish the matching runtime
state before cancellation returns. Cancelling or timing out a CLI installation
stops and drains its owned process; POSIX installations use a separate process
group so ordinary child processes are stopped with it. These lifecycle changes
do not add model requests.

SkillHub package fingerprint checks, extraction and publication run off the
gateway event loop. Once this archive commit starts, cancellation waits for it
to settle before removing staging files; a cancelled request may therefore have
installed the Skill, which can be checked by refreshing the catalog. Cancelling
during download still removes its incomplete staging directory. An occupied
target that is not a discovered Skill reports a conflict rather than a false
installation success. Existing contents are retained.

Marketplace responses with a non-object JSON root or a non-list catalog field
are reported as upstream failures rather than successful empty catalogs or
internal errors. Combined discovery retains a healthy provider's results and
identifies the failed provider. Invalid boolean counters are not displayed as
install/download counts. Malformed SkillHub version or fingerprint responses
stop installation before a package is downloaded.

Workspace path resolution retains the canonical target that passed its directory
or exact-file permission check. If a file or parent symbolic link is retargeted
before final resolution, the operation is rejected instead of returning that
new target. This applies to existing-file reads and checks that allow a new path.

Skill availability, validation and setup hints share one runtime metadata parser.
Invalid requirement lists are reported as errors; they do not remove a Skill's
requirements. Missing or null optional requirement lists mean no requirements.
Settings keeps unavailable Skills and their readable original instructions visible.
Invalid UTF-8 in a Skill document is reported as an availability/validation error;
it does not stop other Skills from loading or break the Settings catalog. Its
details show the decode failure instead of corrupted instructions. Validation
and deletion can retain its original bytes as an invalid history version.
An unreadable or concurrently removed Skill is likewise reported as unavailable
without stopping other Skills or the Settings catalog. Explicit history capture
still reports incomplete reads and publication failures; it never records a
partial tree as a complete version.

Skill history retains complete regular files and empty directories. Links,
Windows reparse points and special files produce validation errors and are not
followed. A failed read or publication leaves earlier versions available and
reports the failure. Deleting a Home Skill preserves its retained versions.

File tools take their allowed Home resources from the Home captured in their
tool context. The same Home owns the Skill history snapshots before and after
a write. Selecting another instance later does not redirect these captures or
grant the existing tool write access to that instance's Home.

Upgrading from 0.1.6 preserves the instance directory and account. It converts conversation and automation storage once; replacing the container image does not require re-registration. Older layouts should first be upgraded to 0.1.6.

Back up the entire instance root with the service stopped. Copying only Agent Home does not preserve accounts, conversations or task queues. Copying only Markdown does not preserve memory scopes, revisions, links or consolidation evidence and processing state. Workspaces outside the instance root require their own backups. See [memory storage](architecture/memory.md) for authoritative and rebuildable databases.

The credential database and its `state/credentials/vault.key` belong together.
First access publishes a complete, synchronized key through an atomic rename;
failed key generation or file synchronization leaves no partial live key. An
existing nonempty vault without its key refuses further access or writes: restore
its original key from backup. Cirno does not generate a second key for that vault.
Credential tools and the browser workbench retain their selected configuration's
state directory. Accepted local initialization, reads and writes settle before
cancellation returns; a first read may also initialize storage or migrate its schema.

The credential editor hides the previous connection's records and revealed values
as soon as its owner changes. Pending work from that owner cannot block or clear
a new owner's save. Leaving and returning to the tab retires an in-flight reveal,
even when an edited draft remains available.

## First introduction and profile changes

New owner registration creates `home/BOOTSTRAP.md` for the Router’s first introduction. Agreed assistant identity and personality go to `SOUL.md`; user names, preferred forms of address, background and lasting communication preferences go to `USER.md`. Explicit changes are applied during the conversation through file tools, without waiting for context consolidation or only saving a memory record. Workers use `WORKER.md` for their own personality and share `USER.md`. Existing profile content is preserved when adding details.

When the introduction is finished or skipped, the Router empties `BOOTSTRAP.md`. Login, restart and clearing conversation history do not recreate it. These files remain editable in Settings → Personality and are included in instance backups. The first wake is a durable system input, visibly identified as First awakening; it is not a fabricated user message.
