import type { ToolProgressEvent } from "@/lib/contracts/activity";
import type { UIMessage } from "@/lib/contracts/messages";
import { canonicalToolTrace, formatToolCallTrace, mergeToolProgressEvents } from "@/lib/tool-traces";
import { traceLines } from "./activity-entries";

export interface ActivityToolEntry {
  key: string;
  line: string;
  event?: ToolProgressEvent;
}

/** Call identity and order come from structured events; old traces fill gaps. */
export function activityToolEntries(message: UIMessage): ActivityToolEntry[] {
  const structured: ActivityToolEntry[] = [];
  const byTrace = new Map<string, { positions: number[]; next: number }>();
  for (const event of mergeToolProgressEvents(undefined, message.toolEvents ?? [])) {
    const line = formatToolCallTrace(event);
    if (!line) continue;
    const trace = canonicalToolTrace(line);
    const group = byTrace.get(trace) ?? { positions: [], next: 0 };
    group.positions.push(structured.length);
    byTrace.set(trace, group);
    structured.push({ key: event.call_id ? `call:${event.call_id}` : `event:${trace}`, line, event });
  }
  const entries: ActivityToolEntry[] = [];
  let cursor = 0;
  traceLines(message).forEach((line, index) => {
    const group = byTrace.get(canonicalToolTrace(line));
    if (!group) {
      entries.push({ key: `legacy:${index}`, line });
      return;
    }
    while (group.next < group.positions.length && group.positions[group.next] < cursor) group.next += 1;
    const position = group.positions[group.next];
    if (position === undefined) return;
    while (cursor <= position) entries.push(structured[cursor++]);
  });
  while (cursor < structured.length) entries.push(structured[cursor++]);
  return entries;
}
