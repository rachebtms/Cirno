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
| `state/telegram.sqlite3` | Personal Telegram binding and expiring PINs |
| `state/cron/`, `state/delivery/` | Scheduler and notification delivery queues |
| `state/logs/`, `state/run/` | Logs and service process records |
| `state/media/`, `state/webui/`, `state/cache/` | Attachments, browser service state and caches |
| `home/AGENTS.md` | Agent-wide workflow instructions |
| `home/SOUL.md` | Personality and communication style |
| `home/USER.md` | Durable user preferences |
| `home/HEARTBEAT.md` | Periodic background instructions |
| `home/memory/MEMORY.md` | Shared long-term overview |
| `home/memory/` | Scoped knowledge, original evidence, revisions and memory databases |
| `home/skills/<name>/SKILL.md` | Installed and learned Skills |
| `home/skills-history/` | Retained Skill versions |
| `home/prompts/dream.md` | Optional Dream prompt override |
| `workspace/` | Default task directory; conversations may select other directories |

A project's own `AGENTS.md` supplies project instructions in addition to Home instructions. Projects have independent IDs and can share a working directory. Conversation histories remain separate when projects or directories change. Workspaces contain a small `.cirno/workspace-id` identity marker; conversation databases remain under `state/sessions/`.

Bundled Skills are part of the application. Home Skills override or extend them through the loader. File tools expose supported Home resources according to their access policy; Dream has additional maintenance permissions, while ordinary execution does not directly rewrite shared profiles. The user can edit profiles through Settings. Directory separation expresses ownership; Full Access can still access files outside the workspace.

Versions 0.1.3, 0.1.4 and 0.1.5 use the same layout. Upgrading between them preserves the existing instance directory; replacing the container image does not require re-registration or moving files. Layouts from before 0.1.3 are not automatically imported or migrated. Keep any earlier instance separately.

Back up the entire instance root with the service stopped. Copying only Agent Home does not preserve accounts, conversations or task queues. Copying only Markdown does not preserve memory scopes, revisions, links or Dream processing state. Workspaces outside the instance root require their own backups. See [memory storage](architecture/memory.md) for authoritative and rebuildable databases.
