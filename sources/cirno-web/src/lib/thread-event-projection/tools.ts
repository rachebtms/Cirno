import {
  mergeToolProgressEvents,
  mergeToolProgressTraceLines,
  normalizeToolProgressEvents,
  toolTraceLinesFromEvents,
} from "@/lib/tool-traces";
import type { ThreadProjectionEvent } from "@/lib/contracts/events";
import type { ThreadProjectionState, ThreadProjectionOptions } from "./contracts";
import { positionedTurnFields } from "./turns";
import { filterCoveredFileEditToolEvents } from "./files";
import {
  closeThreadProjectionAnswer,
  projectionCreatedAt,
  projectionMessageId,
  turnFieldsForProjection,
  ensureProjectionActivitySegment,
} from "./state";

export function projectToolActivity(
  state: ThreadProjectionState,
  event: Extract<ThreadProjectionEvent, { event: "message" }>,
  options: ThreadProjectionOptions,
): void {
  Object.assign(state, closeThreadProjectionAnswer(state));
  const structuredEvents = normalizeToolProgressEvents(event.tool_events);
  const visibleEvents = filterCoveredFileEditToolEvents(state.messages, structuredEvents);
  const structuredLines = toolTraceLinesFromEvents(visibleEvents);
  const lines = structuredLines.length > 0
    ? structuredLines
    : structuredEvents.length > 0
      ? []
      : event.text
        ? [event.text]
        : [];
  if (lines.length === 0) return;

  const deferredDetail = event.trace_detail;
  const segmentId = ensureProjectionActivitySegment(state);
  const turn = turnFieldsForProjection(state, event, "activity");
  const last = state.messages[state.messages.length - 1];
  if (
    last
    && last.kind === "trace"
    && !last.isStreaming
    && !last.traceDetail
    && !deferredDetail
    && (!last.activitySegmentId || last.activitySegmentId === segmentId)
  ) {
    const previousTraces = last.traces?.length
      ? last.traces
      : last.content
        ? [last.content]
        : [];
    const mergedEvents = visibleEvents.length > 0
      ? mergeToolProgressEvents(last.toolEvents, visibleEvents)
      : last.toolEvents;
    const mergedLines = visibleEvents.length > 0
      ? mergeToolProgressTraceLines(
          previousTraces,
          last.toolEvents,
          structuredLines,
          visibleEvents,
        )
      : null;
    state.messages = [
      ...state.messages.slice(0, -1),
      {
        ...last,
        traces: mergedLines ?? [...previousTraces, ...lines],
        content: mergedLines
          ? mergedLines[mergedLines.length - 1]
          : lines[lines.length - 1],
        toolEvents: mergedEvents,
        activitySegmentId: last.activitySegmentId ?? segmentId,
        ...positionedTurnFields(last, turn, options),
      },
    ];
    options.effects?.bodyWrites.add(last.id);
    return;
  }
  const id = projectionMessageId(event, options);
  state.messages = [
    ...state.messages,
    {
      id,
      role: "tool",
      kind: "trace",
      content: lines[lines.length - 1],
      traces: lines,
      ...(visibleEvents.length ? { toolEvents: visibleEvents } : {}),
      ...(deferredDetail ? { traceDetail: deferredDetail } : {}),
      activitySegmentId: segmentId,
      ...positionedTurnFields(undefined, turn, options),
      createdAt: projectionCreatedAt(event, options),
    },
  ];
  options.effects?.bodyWrites.add(id);
}
