The scheduled time has arrived. Execute this scheduled cron job now and report the result to the user in the same session.

Rules:
- Follow the destination conversation's reply contract: ordinary conversations return assistant text; the Router conversation calls `user__message`.
- Only the Router has `user__message` for attachments. Use `conversations__send` for explicitly requested communication with another conversation. Preserve recipients requested in the task; do not invent them.
- Speak directly to the user in their language.
- Do not narrate internal progress.
- Do not include user IDs.
- Do not add status reports like "Done" or "Reminded" unless they are the natural response.

Cron job: {{ message }}
