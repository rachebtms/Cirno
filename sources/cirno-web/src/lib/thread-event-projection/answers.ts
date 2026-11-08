import type { ThreadProjectionEvent } from "@/lib/contracts/events";
import type { UIMessage } from "@/lib/contracts/messages";
import type { ThreadProjectionState, ThreadProjectionOptions } from "./contracts";
import { matchesTurn, positionedTurnFields, replaceMessageAt, isReasoningOnlyPlaceholder } from "./turns";
import {
  clearThreadProjectionActivity,
  closeThreadProjectionAnswer,
  projectionCreatedAt,
  projectionMessageId,
  turnFieldsForProjection,
  ensureProjectionActivitySegment,
  activeAssistantIndex,
  answerStreamKey,
  answerStreamIndex,
} from "./state";

export function appendAnswerText(
  state: ThreadProjectionState,
  event: Extract<ThreadProjectionEvent, { event: "delta" }>,
  options: ThreadProjectionOptions,
): void {
  const turn = turnFieldsForProjection(state, event, "answer");
  const streamKey = answerStreamKey(turn, event.stream_id);
  if (streamKey && state.closedAnswerStreamIds.has(streamKey)) return;
  let targetIndex = answerStreamIndex(state, turn, event.stream_id);
  if (targetIndex !== null && state.closedAssistantIds.has(state.messages[targetIndex].id)) targetIndex = null;
  if (targetIndex === null) {
    Object.assign(state, closeThreadProjectionAnswer(state));
    const id = projectionMessageId(event, options);
    state.messages = [
      ...state.messages,
      {
        id,
        role: "assistant",
        content: "",
        isStreaming: true,
        createdAt: projectionCreatedAt(event, options),
      },
    ];
    targetIndex = state.messages.length - 1;
  }
  const target = state.messages[targetIndex];
  const merged: UIMessage = {
    ...target,
    content: target.content + event.text,
    isStreaming: true,
    ...positionedTurnFields(target, turn, options),
    ...(event.stream_id ? { streamId: event.stream_id } : {}),
    ...(event.source ? { source: event.source } : {}),
    ...(event.response_sources !== undefined ? { responseSources: event.response_sources } : {}),
  };
  state.closedAssistantIds.delete(merged.id);
  state.activeAssistantId = merged.id;
  state.mergeReasoning = false;
  state.messages = replaceMessageAt(state.messages, targetIndex, merged);
  options.effects?.bodyWrites.add(merged.id);
}

export function attachProjectedReasoning(
  state: ThreadProjectionState,
  event: Extract<ThreadProjectionEvent, { event: "reasoning_delta" | "reasoning_end" }>,
  text: string,
  options: ThreadProjectionOptions,
): void {
  const turn = turnFieldsForProjection(state, event, "reasoning");
  const streamIndex = event.stream_id ? state.messages.findIndex((message) => (
    message.reasoningStreamId === event.stream_id && matchesTurn(message, turn)
  )) : -1;
  if (streamIndex >= 0) {
    const target = state.messages[streamIndex];
    const continues = state.mergeReasoning && state.activeAssistantId === target.id;
    if (event.event === "reasoning_delta" && !target.reasoningStreaming && !continues) return;
    const separator = target.reasoning && !target.reasoningStreaming ? "\n\n" : "";
    state.messages = replaceMessageAt(state.messages, streamIndex, {
      ...target,
      reasoning: event.event === "reasoning_end" ? text : (target.reasoning ?? "") + separator + text,
      reasoningStreaming: event.event === "reasoning_delta" || target.reasoningStreaming,
      ...(!target.content ? positionedTurnFields(target, turn, options) : {}),
    });
    options.effects?.bodyWrites.add(target.id);
    return;
  }
  const activeAssistantBeforeContinuation = state.activeAssistantId;
  const continuationIndex = state.mergeReasoning
    ? activeAssistantIndex(state, turn)
    : null;
  if (continuationIndex !== null) {
    const target = state.messages[continuationIndex];
    const separator = target.reasoning && !target.reasoningStreaming ? "\n\n" : "";
    state.messages = replaceMessageAt(state.messages, continuationIndex, {
      ...target,
      reasoning: (target.reasoning ?? "") + separator + text,
      reasoningStreaming: true,
      ...(event.stream_id ? { reasoningStreamId: event.stream_id } : {}),
    });
    options.effects?.bodyWrites.add(target.id);
    return;
  }

  if (state.fileEditSegmentId || activeAssistantBeforeContinuation) {
    if (activeAssistantBeforeContinuation && !state.activeAssistantId) {
      state.closedAssistantIds.add(activeAssistantBeforeContinuation);
    }
    const closed = closeThreadProjectionAnswer(state);
    Object.assign(state, clearThreadProjectionActivity(closed));
  }
  for (let index = state.messages.length - 1; index >= 0; index -= 1) {
    const candidate = state.messages[index];
    if (candidate.role === "user" || candidate.kind === "trace") break;
    if (candidate.role !== "assistant") continue;
    if (!matchesTurn(candidate, turn) || candidate.content.length > 0
      || (event.stream_id && candidate.reasoningStreamId && event.stream_id !== candidate.reasoningStreamId)) break;
    if (candidate.reasoningStreaming || (candidate.isStreaming && candidate.reasoning === undefined)) {
      const activitySegmentId = candidate.activitySegmentId
        ?? ensureProjectionActivitySegment(state);
      state.messages = replaceMessageAt(state.messages, index, {
        ...candidate,
        reasoning: (candidate.reasoning ?? "") + text,
        reasoningStreaming: true,
        activitySegmentId,
        ...positionedTurnFields(candidate, turn, options),
        ...(event.stream_id ? { reasoningStreamId: event.stream_id } : {}),
      });
      options.effects?.bodyWrites.add(candidate.id);
      return;
    }
    break;
  }

  const activitySegmentId = ensureProjectionActivitySegment(state);
  const id = projectionMessageId(event, options);
  state.messages = [
    ...state.messages,
    {
      id,
      role: "assistant",
      content: "",
      isStreaming: true,
      reasoning: text,
      reasoningStreaming: true,
      activitySegmentId,
      ...positionedTurnFields(undefined, turn, options),
      ...(event.stream_id ? { reasoningStreamId: event.stream_id } : {}),
      createdAt: projectionCreatedAt(event, options),
    },
  ];
  options.effects?.bodyWrites.add(id);
}

export function absorbProjectedAssistantMessage(
  state: ThreadProjectionState,
  event: Extract<ThreadProjectionEvent, { event: "message" }>,
  message: Omit<UIMessage, "id" | "role" | "createdAt">,
  options: ThreadProjectionOptions,
): void {
  const last = state.messages[state.messages.length - 1];
  if (last && isReasoningOnlyPlaceholder(last) && matchesTurn(last, message)) {
    state.messages = [
      ...state.messages.slice(0, -1),
      {
        ...last,
        ...message,
        projectionStartSeq: last.projectionStartSeq ?? last.turnSeq ?? message.projectionStartSeq,
        isStreaming: false,
        reasoningStreaming: false,
      },
    ];
    options.effects?.consumed.add(last.id);
    options.effects?.bodyWrites.add(last.id);
    return;
  }
  const id = projectionMessageId(event, options);
  state.messages = [
    ...state.messages,
    {
      id,
      role: "assistant",
      createdAt: projectionCreatedAt(event, options),
      ...message,
    },
  ];
  options.effects?.bodyWrites.add(id);
}
