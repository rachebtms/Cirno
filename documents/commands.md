# Conversation input commands

The backend catalog owns names, aliases, argument support and turn lifecycle metadata. WebUI menus, highlighting, sending, help and Telegram share that catalog. The slash menu scrolls through every available command; it does not discard entries after the first eight. Loading errors display a Retry action.

Command names are case-insensitive. Spaces, tabs and newlines separate names from arguments; a Telegram `@bot` suffix is transport syntax. Internal spaces/newlines in arguments are preserved. Unknown slash-prefixed text and absolute paths remain normal Agent input. Invalid arguments to a registered command receive a control error without entering the model or ending an active turn.

| Input | Behavior | Comparison with v0.1.6 |
| --- | --- | --- |
| `/temporary on\|off`, `/ptc on\|off` | Choose temporary/PTC mode before the first WebUI message. | Preserved; creation-only. |
| `/access default\|review\|full` | Select access mode through existing workspace controls. | Preserved. |
| `/resume` | Continue the saved stopped request through the UI's recovery action. | Preserved. |
| `/clear` | Reset Router context. Other conversations use `/new`. | Preserved with Router terminology. |
| `/new` | Stop work and reset this conversation's generation; prior side effects remain. | Preserved. |
| `/consolidate [retry [source-id]]` | Serial checkpoint/learning, or retry retained learning. | Unified replacement for compact/Dream. |
| `/compact`, `/dream` | Aliases of `/consolidate`, including retry arguments. | Preserved without duplicate menu entries. |
| `/stop` | Cancel this conversation's work and queued follow-ups. | Preserved. |
| `/restart` | Restart Cirno after a direct human request. | Preserved; Agent/system inputs are rejected. |
| `/status` | Runtime, usage and tasks; uses the execution budget's reserve and threshold. | Preserved; obsolete percentage formula fixed. |
| `/model [preset]` | Inspect/change the preset by ID or unambiguous display name. | Preserved, including internal spaces in names. |
| `/history [n]` | Recent visible messages; default 10, maximum 50. | Preserved. |
| `/goal <task>` | Expand a human request into Goal-mode input. | Preserved. |
| `/trigger <name>` | Create a local CLI trigger bound to this conversation. | Preserved. |
| `/dream-log [commit]` | Inspect a saved legacy memory Git change. | Restored to menu/help. |
| `/dream-restore [commit]` | List/undo a legacy memory Git change after a direct human request. | Restored to menu/help. |
| `/skill`, `/help` | List enabled skills or visible commands. | Preserved. |
| `/dream-prompt [init]` | Explain retirement of the separate Dream override. | Transition reply; no unused file or model call. |
| `/pairing ...` | Explain personal Telegram owner-PIN binding in Settings. | Transition reply; generic pairing stays retired. |
| `!command` | Trusted local WebUI shell input through the existing execution/permission policy. | Preserved; remote text cannot impersonate it. |

Legacy Git commands concern saved `dream:` versions of tracked profile/memory files. Current catalog revisions are in the Memory inspector; checkpoint/learning results are in consolidation reports. Restore undoes the selected legacy change toward its parent. Extra commit arguments are rejected and replies retain transport correlation metadata.

Control input such as `/help`, `/model`, usage errors and retired-command guidance is sendable before model setup. Operations needing a model, such as consolidation/recovery, still require a valid runtime. `/goal <task>` and ordinary prompts retain the model-setup requirement. Control errors do not become queued guidance.

Temporary conversations intentionally expose only `/model` and `/stop`; the server rejects other registered commands under their privacy policy. Creation-only options disappear after a durable conversation is created. Telegram menus omit WebUI creation controls and advertise `/consolidate`, while accepting `/compact` and `/dream`. Hyphenated menu names use underscores, such as `/dream_log`.
