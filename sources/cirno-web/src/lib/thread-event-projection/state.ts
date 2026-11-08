import type { ThreadProjectionEvent } from "@/lib/contracts/events";
import type { UIMessage, UITurnPhase } from "@/lib/contracts/messages";
import type { UIMessageTurnFields, ThreadProjectionState, ThreadProjectionOptions } from "./contracts";
import {
  turnFieldsFromEvent,
  matchesTurn,
  findStreamingAssistantIndex,
  findActiveAssistantPlaceholderIndex,
} from "./turns";

export function createThreadProjectionState(
  messages: UIMessage[] = [],
): ThreadProjectionState {
  return {
    messages,
    activeAssistantId: null,
    closedAssistantIds: new Set(),
    closedAnswerStreamIds: new Set(),
    mergeReasoning: false,
    activitySegmentId: null,
    fileEditSegmentId: null,
    activitySegmentCounter: 0,
    suppressUntilTurnEnd: false,
    closedTurnIds: new Set(),
    turnAliases: new Map(),
  };
}

export function resetThreadProjectionCursor(
  state: ThreadProjectionState,
  messages: UIMessage[] = state.messages,
): ThreadProjectionState {
  return {
    ...createThreadProjectionState(messages),
    activitySegmentCounter: state.activitySegmentCounter,
    closedTurnIds: new Set(state.closedTurnIds),
    turnAliases: new Map(state.turnAliases),
  };
}

export function clearThreadProjectionActivity(
  state: ThreadProjectionState,
): ThreadProjectionState {
  return {
    ...state,
    activitySegmentId: null,
    fileEditSegmentId: null,
  };
}

export function closeThreadProjectionAnswer(
  state: ThreadProjectionState,
): ThreadProjectionState {
  if (!state.activeAssistantId) return state;
  const closedAssistantIds = new Set(state.closedAssistantIds);
  closedAssistantIds.add(state.activeAssistantId);
  return {
    ...state,
    activeAssistantId: null,
    closedAssistantIds,
    mergeReasoning: false,
  };
}

export function projectionCreatedAt(event: ThreadProjectionEvent, options: ThreadProjectionOptions): number {
  return typeof event.created_at_ms === "number" && Number.isFinite(event.created_at_ms) && event.created_at_ms >= 0
    ? event.created_at_ms
    : options.persisted ? 0 : options.now;
}

export function projectionMessageId(
  event: ThreadProjectionEvent,
  options: ThreadProjectionOptions,
): string {
  return typeof event.projection_id === "string" && event.projection_id.length > 0
    ? event.projection_id
    : options.createId();
}

export function turnFieldsForProjection(
  state: ThreadProjectionState,
  event: ThreadProjectionEvent,
  fallbackPhase?: UITurnPhase,
): UIMessageTurnFields {
  const fields = turnFieldsFromEvent(event, fallbackPhase);
  const rawTurnId = fields.turnId;
  if (!rawTurnId || !state.closedTurnIds.has(rawTurnId)) return fields;
  let alias = state.turnAliases.get(rawTurnId);
  if (!alias) {
    const suffix = event.projection_id || event.created_at_ms || state.messages.length;
    alias = `${rawTurnId}:replay:${suffix}`;
    state.turnAliases.set(rawTurnId, alias);
  }
  return { ...fields, turnId: alias };
}

export function ensureProjectionActivitySegment(state: ThreadProjectionState): string {
  if (state.activitySegmentId) return state.activitySegmentId;
  state.activitySegmentCounter += 1;
  state.activitySegmentId = `activity-${state.activitySegmentCounter}`;
  return state.activitySegmentId;
}

export function detachedProjectionActivitySegment(state: ThreadProjectionState): string {
  state.activitySegmentCounter += 1;
  return `activity-${state.activitySegmentCounter}`;
}

export function activeAssistantIndex(
  state: ThreadProjectionState,
  turn: UIMessageTurnFields,
): number | null {
  if (!state.activeAssistantId) return null;
  const index = state.messages.findIndex((message) => message.id === state.activeAssistantId);
  if (index < 0) {
    state.activeAssistantId = null;
    state.mergeReasoning = false;
    return null;
  }
  const message = state.messages[index];
  if (
    message.role !== "assistant"
    || message.kind === "trace"
    || !message.isStreaming
    || !matchesTurn(message, turn)
  ) {
    state.activeAssistantId = null;
    state.mergeReasoning = false;
    return null;
  }
  return index;
}

export function answerStreamKey(turn: UIMessageTurnFields, streamId?: string): string | undefined {
  return streamId ? JSON.stringify([turn.turnId ?? "", streamId]) : undefined;
}

export function answerStreamIndex(
  state: ThreadProjectionState,
  turn: UIMessageTurnFields,
  streamId?: string,
): number | null {
  if (streamId) {
    for (let index = state.messages.length - 1; index >= 0; index--) {
      const message = state.messages[index];
      if (message.role === "assistant" && message.streamId === streamId && matchesTurn(message, turn)) return index;
    }
  }
  const active = activeAssistantIndex(state, turn);
  if (active !== null && (!streamId || !state.messages[active].streamId || state.messages[active].streamId === streamId)) {
    return active;
  }
  const placeholder = findActiveAssistantPlaceholderIndex(state.messages, turn);
  if (placeholder !== null && (!streamId || !state.messages[placeholder].streamId || state.messages[placeholder].streamId === streamId)) {
    return placeholder;
  }
  return findStreamingAssistantIndex(state.messages, state.closedAssistantIds, turn, streamId);
}
