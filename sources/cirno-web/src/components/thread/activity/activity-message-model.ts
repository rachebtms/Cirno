import {
  canonicalToolTrace,
  formatToolCallTrace,
  toolTraceLinesFromEvents,
  mergeToolProgressEvents,
  mergeToolProgressTraceLines,
  mergeUniqueToolTraceLines,
} from "@/lib/tool-traces";
import type { UIMediaAttachment, UIMessage } from "@/lib/contracts/messages";

/**
 * Live tool progress is already folded into one trace message. Persisted
 * transcripts can contain the same progress as adjacent start/end rows, so
 * normalize both paths before rendering the activity timeline.
 */
export interface ActivityEntry { message: UIMessage; sourceMessageCount: number; hidden?: boolean }

export function coalesceActivityMessages(messages: UIMessage[]): UIMessage[] {
  return coalesceActivityEntries(messages).filter(entry => !entry.hidden).map(entry => entry.message);
}

/** Coalesce before answer/activity segmentation so a delivered reply is not a
 * second tool invocation. Counts retain the original transcript fork offsets. */
export function coalesceActivityEntries(messages: UIMessage[]): ActivityEntry[] {
  const rows: ActivityEntry[] = [];
  const calls = new Map<string, { latest: number; byTurn: Map<string, number> }>();
  for (const message of messages) {
    const index = rows.length;
    rows.push({ message, sourceMessageCount: 1 });
    if (message.kind !== "trace" || message.traceDetail) continue;
    const events = message.toolEvents ?? [];
    if (!events.some(event => event.call_id)) {
      const previous = rows[index - 1];
      if (previous && !previous.hidden && canMergeAdjacentProgress(previous.message, message)) {
        previous.message = mergeTraceMessages(previous.message, message);
        rows[index].hidden = true;
      }
      continue;
    }
    const groups = new Map<number, typeof events>();
    for (const event of events) {
      const call = event.call_id ? calls.get(event.call_id) : undefined;
      const target = call
        ? message.turnId
          ? Math.max(call.byTurn.get(message.turnId) ?? -1, call.byTurn.get("") ?? -1)
          : call.latest
        : -1;
      const owner = target < 0 ? index : target;
      groups.set(owner, [...(groups.get(owner) ?? []), event]);
      if (event.call_id) {
        const registered = call ?? { latest: owner, byTurn: new Map<string, number>() };
        registered.latest = Math.max(registered.latest, owner);
        registered.byTurn.set(message.turnId || "", owner);
        calls.set(event.call_id, registered);
      }
    }
    // A transport batch can complete an earlier call and start a different one.
    // Move only matching invocations, never the rest of that batch or its files.
    const eventLines = new Set(events.flatMap(event => {
      const line = formatToolCallTrace(event);
      return line ? [canonicalToolTrace(line)] : [];
    }));
    const extraLines = messageTraces(message).filter(line => !eventLines.has(canonicalToolTrace(line)));
    if (!groups.has(index) && (extraLines.length || message.fileEdits?.length || message.media?.length)) groups.set(index, []);
    rows[index].hidden = !groups.has(index);
    for (const [owner, group] of groups) {
      const local = owner === index;
      const traces = [...(local ? extraLines : []), ...toolTraceLinesFromEvents(group)];
      const part: UIMessage = groups.size === 1 && group.length === events.length
        ? message
        : { ...message, toolEvents: group, traces, content: traces.at(-1) ?? "",
            fileEdits: local ? message.fileEdits : undefined, media: local ? message.media : undefined };
      rows[owner].message = local ? part : mergeTraceMessages(rows[owner].message, part);
    }
  }
  return rows;
}

function canMergeAdjacentProgress(
  previous: UIMessage | undefined,
  incoming: UIMessage,
): previous is UIMessage {
  if (!previous || previous.kind !== "trace" || previous.traceDetail || incoming.traceDetail) return false;
  if (!sameTurn(previous, incoming)) return false;
  if (
    previous.activitySegmentId
    && incoming.activitySegmentId
    && previous.activitySegmentId === incoming.activitySegmentId
  ) {
    return true;
  }
  return hasSharedTrace(previous, incoming) && completesPreviousProgress(previous, incoming);
}

function mergeTraceMessages(previous: UIMessage, incoming: UIMessage): UIMessage {
  const toolEvents = mergeToolProgressEvents(previous.toolEvents, incoming.toolEvents ?? []);
  const traces = incoming.toolEvents?.length
    ? mergeToolProgressTraceLines(
        messageTraces(previous),
        previous.toolEvents,
        messageTraces(incoming),
        incoming.toolEvents ?? [],
      )
    : mergeUniqueToolTraceLines(messageTraces(previous), messageTraces(incoming)).traces;
  const fileEdits = [...(previous.fileEdits ?? []), ...(incoming.fileEdits ?? [])];
  const media = uniqueMedia([...(previous.media ?? []), ...(incoming.media ?? [])]);

  return {
    ...previous,
    content: traces[traces.length - 1] ?? incoming.content ?? previous.content,
    traces,
    ...(toolEvents.length ? { toolEvents } : { toolEvents: undefined }),
    ...(fileEdits.length ? { fileEdits } : { fileEdits: undefined }),
    ...(media.length ? { media } : { media: undefined }),
    isStreaming: incoming.isStreaming,
    turnPhase: incoming.turnPhase ?? previous.turnPhase,
    turnSeq: incoming.turnSeq ?? previous.turnSeq,
  };
}

function messageTraces(message: UIMessage): string[] {
  if (message.traces?.length) return message.traces;
  return message.content.trim() ? [message.content] : [];
}

function hasSharedTrace(previous: UIMessage, incoming: UIMessage): boolean {
  const previousTraces = new Set(messageTraces(previous).map(canonicalToolTrace));
  return messageTraces(incoming).some((trace) => previousTraces.has(canonicalToolTrace(trace)));
}

function completesPreviousProgress(previous: UIMessage, incoming: UIMessage): boolean {
  const previousPhases = new Set((previous.toolEvents ?? []).map((event) => event.phase));
  const incomingPhases = new Set((incoming.toolEvents ?? []).map((event) => event.phase));
  return previousPhases.has("start") && (incomingPhases.has("end") || incomingPhases.has("error"));
}

function sameTurn(previous: UIMessage, incoming: UIMessage): boolean {
  return !previous.turnId || !incoming.turnId || previous.turnId === incoming.turnId;
}

function uniqueMedia(media: UIMediaAttachment[]): UIMediaAttachment[] {
  const seen = new Set<string>();
  return media.filter((item) => {
    const key = `${item.kind}:${item.url ?? ""}:${item.name ?? ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
