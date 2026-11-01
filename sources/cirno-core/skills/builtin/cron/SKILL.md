---
name: cron
description: Schedule reminders and recurring tasks.
---

# Cron

Use the `automations` tool namespace to schedule reminders or recurring tasks. New tasks run in the current chat. Cirno sends the agent's final reply to that chat. The user can change the task's chat in WebUI.

Write what to do in `message`. For a normal reminder or report, do not copy the current channel, chat ID, or instructions to call `user__message` into the task. For example, use "Remind me to drink water", not "Call message to send to this chat".

If the user requests communication with another conversation, preserve the destination in the task instructions and use `conversations__send`. Only the Cirno coordination conversation has `user__message` for visible replies and attachments. Ordinary conversations reply with assistant text; changing an automation's chat does not grant tools that its destination role excludes.

Choose by timing and notification behavior, not repetition. A specified time or interval uses `automations`, even when it repeats: "every day at 8am, remind me to drink water" is a cron task. Use `HEARTBEAT.md` for background checks with flexible timing that should notify only on actionable changes. Heartbeat does not guarantee a requested time or interval; do not substitute it for an explicit schedule.

## Task Types

1. **Reminder** - the agent replies with the reminder when the task runs
2. **Task** - the agent follows the instructions and replies with the result
3. **One-time** - runs once at a specific time, then auto-deletes

## Examples

Fixed reminder:
```
automations__add(message="Time to take a break!", every_seconds=1200)
```

Dynamic task (agent executes each time):
```
automations__add(message="Check the configured repository for new releases", every_seconds=600)
```

One-time scheduled task (compute ISO datetime from current time):
```
automations__add(message="Remind me about the meeting", at="<ISO datetime>")
```

Timezone-aware cron:
```
automations__add(message="Morning standup", cron_expr="0 9 * * 1-5", tz="America/Vancouver")
```

List/remove:
```
automations__list()
automations__remove(job_id="abc123")
```

Pause and resume an existing task without deleting its schedule or run history:
```
automations__disable(job_id="abc123")
automations__list(include_disabled=True)
automations__enable(job_id="abc123")
```

Disabling a task stops future runs; it does not cancel a running task or recall a queued reply. System-managed jobs such as heartbeat and Dream are protected; change their configuration instead.

## Time Expressions

| User says | Parameters |
|-----------|------------|
| every 20 minutes | every_seconds: 1200 |
| every hour | every_seconds: 3600 |
| every day at 8am | cron_expr: "0 8 * * *" |
| weekdays at 5pm | cron_expr: "0 17 * * 1-5" |
| 9am Vancouver time daily | cron_expr: "0 9 * * *", tz: "America/Vancouver" |
| at a specific time | at: ISO datetime string (compute from current time) |

## Timezone

Use `tz` with `cron_expr` to schedule in a specific IANA timezone. New tasks use the runtime default timezone when `tz` is omitted. Updates retain the task's existing cron timezone.

## Update a Task

Use `automations__update(job_id="...", cron_expr="0 10 * * *")` to change an existing task. Supply only the fields to change: `name`, `message`, or exactly one of `every_seconds`, `cron_expr`, and `at`. Omitted fields keep their values; empty names and instructions are rejected. A cron edit retains the existing timezone unless `tz` is supplied with `cron_expr`. Naive `at` values use the runtime default timezone.

Updates preserve the task ID, linked chat, history, enabled state, and automatic-deletion setting. Changing only the name or instruction does not move the next run. System-managed tasks cannot be edited.

## Run History

Use `automations__history(job_id="...", limit=5)` to inspect recent executions, newest first. Each entry includes its time, status, duration in milliseconds, and any error. `job_id` is required; `limit` defaults to 5 and accepts 1–20. Listing jobs still shows only the last run.

History can be inspected for disabled jobs too. The scheduler retains at most 20 runs per job; deleted jobs, including automatically deleted one-time tasks, cannot be queried. This reads execution records, not task output or delivery receipts.
