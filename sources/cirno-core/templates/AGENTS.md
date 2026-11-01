# Agent Instructions

## Workspace Guidance

This file stores agent-wide workflow conventions in Cirno Home. Project-specific instructions belong in the project’s own `AGENTS.md`. User preferences, personality and memory live beside this file in Home.

## Scheduled Reminders

- Before scheduling reminders, check available skills and follow skill guidance first.
- Use the built-in `automations__add`, `automations__list` and `automations__remove` operations for scheduled work. Do not substitute shell commands for the scheduling tools.
- Use `automations__add` for a specified time or interval, including recurring reminders such as "every day at 8am". Repetition alone does not make a task a heartbeat task.
- The tool captures the current chat. Task instructions need only say what to do; Cirno sends the final reply to the saved chat. Include other recipients only when the user requests separate sends.

**Do NOT just write reminders to MEMORY.md** — that won't trigger actual notifications.

## Heartbeat Tasks

`HEARTBEAT.md` is checked periodically by the protected heartbeat cron job that `cirno gateway` registers when `gateway.heartbeat.enabled` is true. Do not create a duplicate heartbeat job unless the user has disabled the built-in one and explicitly wants a custom schedule.

- Use `files__patch` for normal task-list updates, especially when adding, removing, or changing multiple lines.
- Use `files__edit` only for small exact replacements copied from the current `HEARTBEAT.md`.
- Use `files__write` for first creation or intentional full-file rewrites.

Use `HEARTBEAT.md` for background checks with flexible timing that should notify only on actionable changes. Heartbeat does not guarantee a requested time or interval. For example, "keep an eye on open issues and tell me if one needs attention" fits heartbeat; "send me an issue report every day at 8am" needs `automations__add`.
