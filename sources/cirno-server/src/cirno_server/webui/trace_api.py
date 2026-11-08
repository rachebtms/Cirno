"""Authenticated operations on disposable, per-tab diagnostic recordings."""

import asyncio

from cirno_core.observability.recordings import current_recordings

GROUPS = {
    "input": ["input"],
    "system": ["system_input"],
    "answer": ["answer", "answer_segment", "answer_fragment"],
    "reasoning": ["reasoning", "reasoning_segment", "reasoning_fragment"],
    "tool": ["tool_activity"],
    "compaction": ["compaction"],
    "request": ["request"],
    "file": ["file_activity"],
    "lifecycle": ["progress", "completion", "fork_boundary"],
}


class TraceAPI:
    def __init__(self):
        self.recordings = current_recordings()

    async def action(self, operation, values):
        identifier = values["recording_id"]
        if operation == "create":
            return await asyncio.to_thread(self.recordings.create, identifier)
        if operation == "events":
            group = values.get("kind")
            if group and group not in GROUPS:
                raise ValueError("Unknown event type")
            values = {**values, "kinds": GROUPS.get(group)}
        return await asyncio.to_thread(self.recordings.operation, identifier, operation, values)
