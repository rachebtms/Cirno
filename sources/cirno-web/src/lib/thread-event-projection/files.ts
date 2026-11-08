import { implementationToolName } from "@/lib/tool-names";
import { toolTraceLinesFromEvents } from "@/lib/tool-traces";
import type { ThreadProjectionEvent } from "@/lib/contracts/events";
import type { ToolProgressEvent, UIFileEdit } from "@/lib/contracts/activity";
import type { UIMessage } from "@/lib/contracts/messages";
import type {
  UIMessageTurnFields,
  ThreadProjectionState,
  ThreadProjectionEffects,
  ThreadProjectionOptions,
} from "./contracts";
import { matchesTurn, positionedTurnFields, replaceMessageAt } from "./turns";
import {
  closeThreadProjectionAnswer,
  projectionCreatedAt,
  projectionMessageId,
  turnFieldsForProjection,
  detachedProjectionActivitySegment,
} from "./state";

const FILE_EDIT_TOOL_NAMES = new Set(["write_file", "edit_file", "apply_patch"]);

function fileEditKey(edit: Pick<UIFileEdit, "call_id" | "tool" | "path">): string {
  if (edit.call_id && edit.path) return `${edit.call_id}|${edit.tool}|${edit.path}`;
  if (edit.call_id) return `${edit.call_id}|${implementationToolName(edit.tool)}`;
  return `${edit.tool}|${edit.path}`;
}

function fileEditToolEventKey(
  edit: Pick<UIFileEdit, "call_id" | "tool" | "path">,
): string {
  if (edit.call_id) return `${edit.call_id}|${edit.tool}`;
  return fileEditKey(edit);
}

function toolEventFileEditKey(event: ToolProgressEvent): string | null {
  const fn = (event as { function?: { name?: unknown } }).function;
  const name = typeof event.name === "string"
    ? event.name
    : typeof fn?.name === "string"
      ? fn.name
      : "";
  const callId = typeof event.call_id === "string" ? event.call_id : "";
  const implementation = implementationToolName(name);
  if (!name || !callId || !FILE_EDIT_TOOL_NAMES.has(implementation)) return null;
  return `${callId}|${implementation}`;
}

function hasFileEditForToolEvent(messages: UIMessage[], event: ToolProgressEvent): boolean {
  const key = toolEventFileEditKey(event);
  if (!key) return false;
  return messages.some((message) =>
    message.fileEdits?.some((edit) => fileEditToolEventKey(edit) === key),
  );
}

export function filterCoveredFileEditToolEvents(
  messages: UIMessage[],
  events: ToolProgressEvent[],
): ToolProgressEvent[] {
  if (events.length === 0) return events;
  return events.filter((event) => !hasFileEditForToolEvent(messages, event));
}

function stripCoveredFileEditToolHints(message: UIMessage, edits: UIFileEdit[]): UIMessage {
  const incomingKeys = new Set(edits.map(fileEditToolEventKey));
  const events = message.toolEvents ?? [];
  if (!events.length || incomingKeys.size === 0) return message;

  const removedTraceLines = new Set<string>();
  const keptEvents: ToolProgressEvent[] = [];
  let changed = false;
  for (const event of events) {
    const key = toolEventFileEditKey(event);
    if (key && incomingKeys.has(key)) {
      changed = true;
      for (const line of toolTraceLinesFromEvents([event])) {
        removedTraceLines.add(line);
      }
      continue;
    }
    keptEvents.push(event);
  }
  if (!changed) return message;

  const previousTraces = message.traces?.length
    ? message.traces
    : message.content
      ? [message.content]
      : [];
  const nextTraces = previousTraces.filter((line) => !removedTraceLines.has(line));
  return {
    ...message,
    traces: nextTraces,
    content: nextTraces[nextTraces.length - 1] ?? "",
    toolEvents: keptEvents.length ? keptEvents : undefined,
  };
}

function traceMessageIsEmpty(message: UIMessage): boolean {
  const traces = message.traces;
  const hasTrace = traces?.length
    ? traces.some((line) => line.trim().length > 0)
    : (message.content ?? "").trim().length > 0;
  return (
    message.kind === "trace"
    && !hasTrace
    && !message.toolEvents?.length
    && !message.fileEdits?.length
    && !message.media?.length
  );
}

function stripCoveredFileEditToolHintsFromMessages(
  messages: UIMessage[],
  edits: UIFileEdit[],
  turn: UIMessageTurnFields,
  effects?: ThreadProjectionEffects,
): UIMessage[] {
  if (edits.length === 0) return messages;
  let next = messages;
  for (let i = next.length - 1; i >= 0; i -= 1) {
    const candidate = next[i];
    if (candidate.role === "user") break;
    if (candidate.kind !== "trace") continue;
    if (!matchesTurn(candidate, turn)) continue;
    const cleaned = stripCoveredFileEditToolHints(candidate, edits);
    if (cleaned === candidate) continue;
    effects?.bodyWrites.add(candidate.id);
    if (next === messages) next = [...messages];
    if (traceMessageIsEmpty(cleaned)) {
      effects?.consumed.add(candidate.id);
      next.splice(i, 1);
    } else {
      next[i] = cleaned;
    }
  }
  return next;
}

function normalizeFileEdit(edit: UIFileEdit): UIFileEdit | null {
  if (!edit || !edit.tool || (!edit.path && !edit.pending)) return null;
  const inferredStatus =
    edit.phase === "error"
      ? "error"
      : edit.phase === "end"
        ? "done"
        : "editing";
  const normalized: UIFileEdit = {
    ...edit,
    call_id: edit.call_id || `${edit.tool}:${edit.path}`,
    added: Number.isFinite(edit.added) ? Math.max(0, Math.round(edit.added)) : 0,
    deleted: Number.isFinite(edit.deleted) ? Math.max(0, Math.round(edit.deleted)) : 0,
    status: edit.status === "error" || edit.status === "done" || edit.status === "editing"
      ? edit.status
      : inferredStatus,
  };
  if (edit.pending && !edit.path) normalized.pending = true;
  return normalized;
}

function mergeFileEdits(
  existing: UIFileEdit[] | undefined,
  incoming: UIFileEdit[],
): UIFileEdit[] {
  const next = [...(existing ?? [])];
  const indexByKey = new Map(next.map((edit, index) => [fileEditKey(edit), index]));
  for (const raw of incoming) {
    const edit = normalizeFileEdit(raw);
    if (!edit) continue;
    const key = fileEditKey(edit);
    let existingIndex = indexByKey.get(key);
    if (existingIndex === undefined && edit.path) {
      const eventKey = fileEditToolEventKey(edit);
      const pendingIndex = next.findIndex((existing) =>
        !existing.path && existing.pending && fileEditToolEventKey(existing) === eventKey,
      );
      if (pendingIndex >= 0) existingIndex = pendingIndex;
    }
    if (existingIndex === undefined) {
      indexByKey.set(key, next.length);
      next.push(edit);
      continue;
    }
    const merged = { ...next[existingIndex], ...edit };
    if (edit.path && !edit.pending) delete merged.pending;
    next[existingIndex] = merged;
    indexByKey.set(key, existingIndex);
  }
  return next;
}

function findFileEditTraceIndex(
  prev: UIMessage[],
  segmentId: string | null,
  incoming: UIFileEdit[],
): number | null {
  const incomingKeys = new Set(incoming.map(fileEditKey));
  const incomingToolEventKeys = new Set(incoming.map(fileEditToolEventKey));
  for (let i = prev.length - 1; i >= 0; i -= 1) {
    const candidate = prev[i];
    if (candidate.role === "user") break;
    if (candidate.kind !== "trace") continue;
    if (segmentId && candidate.activitySegmentId === segmentId) return i;
    for (const existing of candidate.fileEdits ?? []) {
      if (
        incomingKeys.has(fileEditKey(existing))
        || (
          !existing.path
          && existing.pending
          && incomingToolEventKeys.has(fileEditToolEventKey(existing))
        )
      ) return i;
    }
  }
  return null;
}

export function projectFileEdits(
  state: ThreadProjectionState,
  event: Extract<ThreadProjectionEvent, { event: "file_edit" }>,
  options: ThreadProjectionOptions,
): void {
  Object.assign(state, closeThreadProjectionAnswer(state));
  const normalized = mergeFileEdits(undefined, event.edits);
  if (normalized.length === 0) return;
  const turn = turnFieldsForProjection(state, event, "activity");
  const opensPhase = normalized.some(
    (edit) => edit.status === "editing" || edit.phase === "start",
  );
  let segmentId = state.fileEditSegmentId;
  if (!segmentId && opensPhase) {
    segmentId = detachedProjectionActivitySegment(state);
    state.fileEditSegmentId = segmentId;
  }
  const base = stripCoveredFileEditToolHintsFromMessages(state.messages, normalized, turn, options.effects);
  const targetIndex = findFileEditTraceIndex(base, segmentId, normalized);
  if (targetIndex !== null) {
    const target = base[targetIndex];
    segmentId = target.activitySegmentId ?? segmentId ?? detachedProjectionActivitySegment(state);
    if (opensPhase) state.fileEditSegmentId = segmentId;
    state.messages = replaceMessageAt(base, targetIndex, {
      ...target,
      fileEdits: mergeFileEdits(target.fileEdits, normalized),
      activitySegmentId: segmentId,
      ...positionedTurnFields(target, turn, options),
    });
    options.effects?.bodyWrites.add(target.id);
    return;
  }
  segmentId = segmentId ?? detachedProjectionActivitySegment(state);
  if (opensPhase) state.fileEditSegmentId = segmentId;
  const id = projectionMessageId(event, options);
  state.messages = [
    ...base,
    {
      id,
      role: "tool",
      kind: "trace",
      content: "",
      traces: [],
      fileEdits: normalized,
      activitySegmentId: segmentId,
      ...positionedTurnFields(undefined, turn, options),
      createdAt: projectionCreatedAt(event, options),
    },
  ];
  options.effects?.bodyWrites.add(id);
}
