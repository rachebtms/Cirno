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
| `home/prompts/dream.md` | Optional Dream prompt override |
| `workspace/` | Default task directory; conversations may select other directories |

A project's own `AGENTS.md` supplies project instructions in addition to Home instructions. Projects have independent IDs and can share a working directory. Conversation histories remain separate when projects or directories change. Conversation storage belongs to the instance under `state/sessions/`; changing, copying or moving the default workspace does not select another conversation database. Workspaces do not need identity markers. The fixed conversation database is `state/sessions/instance/sessions.sqlite3`; startup imports v0.1.6's workspace-bound databases into it. See [instance migration](migrations.md) for ID conflicts, retained originals and recovery.

Large tool outputs are saved under the active workspace’s `.cirno/tool-results/`.
References use immutable content-specific filenames, so reused tool-call IDs
retain their earlier results. These files remain until you remove them; changing
workspaces or starting more conversations does not prune existing references.
Include external workspaces when backing up this evidence.

Bundled Skills are part of the application. Home Skills override or extend them through the loader. File tools expose supported Home resources according to their access policy; Dream has additional maintenance permissions, while ordinary execution does not directly rewrite shared profiles. The user can edit profiles through Settings. Directory separation expresses ownership; Full Access can still access files outside the workspace.

Skill availability, validation and setup hints share one runtime metadata parser.
Invalid requirement lists are reported as errors; they do not remove a Skill's
requirements. Missing or null optional requirement lists mean no requirements.
Settings keeps unavailable Skills and their original instructions visible.

Skill history retains complete regular files and empty directories. Links,
Windows reparse points and special files produce validation errors and are not
followed. A failed read or publication leaves earlier versions available and
reports the failure. Deleting a Home Skill preserves its retained versions.

Upgrading from 0.1.6 preserves the instance directory and account. It converts conversation and automation storage once; replacing the container image does not require re-registration. Older layouts should first be upgraded to 0.1.6.

Back up the entire instance root with the service stopped. Copying only Agent Home does not preserve accounts, conversations or task queues. Copying only Markdown does not preserve memory scopes, revisions, links or Dream processing state. Workspaces outside the instance root require their own backups. See [memory storage](architecture/memory.md) for authoritative and rebuildable databases.

## First introduction and profile changes

New owner registration creates `home/BOOTSTRAP.md` for the Router’s first introduction. Agreed assistant identity and personality go to `SOUL.md`; user names, preferred forms of address, background and lasting communication preferences go to `USER.md`. Explicit changes are applied during the conversation through file tools, rather than waiting for Dream or only saving a memory record. Workers use `WORKER.md` for their own personality and share `USER.md`. Existing profile content is preserved when adding details.

When the introduction is finished or skipped, the Router empties `BOOTSTRAP.md`. Login, restart and clearing conversation history do not recreate it. These files remain editable in Settings → Personality and are included in instance backups. The first wake is a durable system input, visibly identified as First awakening; it is not a fabricated user message.
