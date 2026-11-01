# Home and workspaces

Home owns durable assistant state. It defaults to `~/.cirno/`; select another instance using the global `--home` option. A workspace is the working directory for a conversation's task files. Selecting a workspace does not move Home.

| Path inside Home | Purpose |
| --- | --- |
| `config.json` | Instance configuration |
| `webui-auth.sqlite3` | Instance owner password hash, browser sessions and setup progress |
| `AGENTS.md` | Agent-wide workflow instructions |
| `SOUL.md` | Personality and communication style |
| `USER.md` | Durable user preferences |
| `HEARTBEAT.md` | Flexible periodic background checks |
| `memory/MEMORY.md` | Brief shared long-term overview |
| `memory/` | Scoped records, original evidence, revisions and separate memory databases |
| `skills/<name>/SKILL.md` | Installed and learned Home Skills |
| `skills-history/` | Retained Skill versions |
| `prompts/dream.md` | Optional Dream prompt override |
| `instance.sqlite3` | Instance records, including Projects, Nodes and tracked jobs |
| `notifications/inbox.sqlite3` | Notification records |
| `cron/`, `logs/`, `media/`, `webui/` | Scheduler, logs, attachments and browser service state |

Conversation history and runtime state use the configured session storage. They remain separate from memory and notification databases.

Cirno initializes profiles, memory and user Skills in Home, not in task workspaces. The default workspace may be `Home/workspace`, but remains a separate task directory. A project's own `AGENTS.md` supplies project instructions in addition to Home instructions. Projects have independent IDs and can share a working directory. Conversation histories remain separate when projects or directories change.

Bundled Skills are part of the application. Home Skills override or extend them through the loader. File tools expose supported Home resources according to their access policy; Dream has additional maintenance permissions, while ordinary execution does not directly rewrite shared profiles. The user can edit profiles through Settings.

Back up the entire Home with the service stopped. Copying only Markdown does not preserve database metadata, scopes, queue receipts or runtime state. See [memory storage](architecture/memory.md) for authoritative and rebuildable databases.
