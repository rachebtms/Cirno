import { parseQuestionCancellation, parseUserQuestion } from "@/lib/user-question";
import { toMediaAttachment } from "@/lib/media";
import type { ThreadProjectionEvent } from "@/lib/contracts/events";
import type { UIMessage } from "@/lib/contracts/messages";
import type { ThreadProjectionState, ThreadProjectionOptions } from "./contracts";
import {
  turnFieldsFromEvent,
  matchesTurn,
  positionedTurnFields,
  replaceMessageAt,
  closeReasoningStream,
  stampLastAssistantCompletion,
  finalizeStreamedTurn,
} from "./turns";
import { projectFileEdits } from "./files";
import {
  createThreadProjectionState,
  resetThreadProjectionCursor,
  closeThreadProjectionAnswer,
  projectionCreatedAt,
  projectionMessageId,
  turnFieldsForProjection,
  answerStreamKey,
  answerStreamIndex,
} from "./state";
import { appendAnswerText, attachProjectedReasoning, absorbProjectedAssistantMessage } from "./answers";
import { projectToolActivity } from "./tools";

/** Canonical UI-message reducer shared by WebSocket delivery and transcript replay. */
export function projectThreadEvent(
  previous: ThreadProjectionState,
  event: ThreadProjectionEvent,
  options: ThreadProjectionOptions,
): ThreadProjectionState {
  const state: ThreadProjectionState = {
    ...previous,
    closedAssistantIds: new Set(previous.closedAssistantIds),
    closedAnswerStreamIds: new Set(previous.closedAnswerStreamIds),
    closedTurnIds: new Set(previous.closedTurnIds),
    turnAliases: new Map(previous.turnAliases),
  };

  if (event.event === "user_message") {
    if (event.provenance?.input_origin?.id && state.messages.some(message => message.inputOrigin?.id === event.provenance?.input_origin?.id)) return state;
    if (event.provenance?.session_message) {
      const messageId = event.provenance.session_message.message_id?.trim();
      if (!messageId || state.messages.some(
        (message) => message.sessionMessage?.message_id === messageId,
      )) return state;
    } else if (event.turn_id && state.messages.some(
      (message) => message.role === "user" && message.turnId === event.turn_id,
    )) return state;
    if (state.activeAssistantId) {
      state.messages = state.messages.map((message) => (
        message.id === state.activeAssistantId ? { ...message, isStreaming: false } : message
      ));
    }
    state.messages = closeReasoningStream(
      state.messages,
      options.persisted ? undefined : options.now,
    );
    Object.assign(state, resetThreadProjectionCursor(state, state.messages));
    const media = event.media_urls?.map((item) => toMediaAttachment(item));
    const turn = turnFieldsFromEvent(event, "user");
    const row: UIMessage = {
      id: projectionMessageId(event, options),
      role: "user",
      content: event.text,
      createdAt: projectionCreatedAt(event, options),
      ...turn,
      ...(!options.persisted ? { deliveryStatus: "accepted" as const } : {}),
      ...(media?.length ? { media } : {}),
      ...(event.cli_apps?.length ? { cliApps: event.cli_apps } : {}),
      ...(event.mcp_presets?.length ? { mcpPresets: event.mcp_presets } : {}),
      ...(event.session_mentions?.length ? { sessionMentions: event.session_mentions } : {}),
      ...(event.provenance?.input_origin ? { inputOrigin: event.provenance.input_origin } : {}),
      ...(event.provenance?.session_message
        ? { sessionMessage: event.provenance.session_message }
        : {}),
    };
    if (media?.length && media.every((item) => item.kind === "image")) {
      row.images = media.map(({ url, name }) => ({ url, name }));
    }
    state.messages = [...state.messages, row];
    options.effects?.bodyWrites.add(row.id);
    return state;
  }

  if (event.event === "delta") {
    if (!state.suppressUntilTurnEnd && event.text) {
      state.activitySegmentId = null;
      state.fileEditSegmentId = null;
      appendAnswerText(state, event, options);
    }
    return state;
  }

  if (event.event === "stream_end") {
    if (state.suppressUntilTurnEnd) return state;
    const turn = turnFieldsForProjection(state, event, "answer");
    const mergeNext = event.resuming === true && event.merge_next === true;
    const streamKey = answerStreamKey(turn, event.stream_id);
    const wireClosed = streamKey !== undefined && state.closedAnswerStreamIds.has(streamKey);
    if (streamKey && !mergeNext) state.closedAnswerStreamIds.add(streamKey);
    let targetIndex = answerStreamIndex(state, turn, event.stream_id);
    let text = event.text;
    // Older completed records can span a hosted tool. Their snapshots already
    // use rewritten text; live streams now end before the tool starts.
    if (options.persisted && event.stream_id && typeof text === "string") {
      let offset = 0;
      for (let index = 0; index < (targetIndex ?? state.messages.length); index++) {
        const row = state.messages[index];
        if (row.streamId === event.stream_id && matchesTurn(row, turn)) offset += row.content.length;
      }
      if (targetIndex !== null && state.closedAssistantIds.has(state.messages[targetIndex].id)
        && !wireClosed && text.length > offset + state.messages[targetIndex].content.length) {
        offset += state.messages[targetIndex].content.length;
        targetIndex = null;
      }
      text = text.slice(offset);
    }
    if (targetIndex === null && typeof text !== "string") return state;
    const wasClosed = targetIndex !== null && state.closedAssistantIds.has(state.messages[targetIndex].id);
    if (targetIndex === null && typeof text === "string") {
      const id = projectionMessageId(event, options);
      state.messages = [...state.messages, {
        id,
        role: "assistant",
        content: text,
        isStreaming: true,
        ...positionedTurnFields(undefined, turn, options),
        ...(event.stream_id ? { streamId: event.stream_id } : {}),
        ...(event.source ? { source: event.source } : {}),
        ...(event.response_sources !== undefined ? { responseSources: event.response_sources } : {}),
        createdAt: projectionCreatedAt(event, options),
      }];
      options.effects?.bodyWrites.add(id);
      targetIndex = state.messages.length - 1;
    } else if (targetIndex !== null && (typeof text === "string" || event.source || event.response_sources !== undefined)) {
      const target = state.messages[targetIndex];
      state.messages = replaceMessageAt(state.messages, targetIndex, {
        ...target,
        ...(typeof text === "string" ? { content: text } : {}),
        ...positionedTurnFields(target, turn, options),
        ...(event.stream_id ? { streamId: event.stream_id } : {}),
        ...(event.source ? { source: event.source } : {}),
        ...(event.response_sources !== undefined ? { responseSources: event.response_sources } : {}),
      });
      if (typeof text === "string") options.effects?.bodyWrites.add(target.id);
    }
    if (wasClosed || wireClosed) return state;
    if (targetIndex !== null) state.activeAssistantId = state.messages[targetIndex].id;
    state.mergeReasoning = mergeNext && state.activeAssistantId !== null;
    if (!mergeNext) Object.assign(state, closeThreadProjectionAnswer(state));
    return state;
  }

  if (event.event === "reasoning_delta") {
    if (!state.suppressUntilTurnEnd && event.text) {
      attachProjectedReasoning(state, event, event.text, options);
    }
    return state;
  }

  if (event.event === "reasoning_end") {
    if (state.suppressUntilTurnEnd) return state;
    if (event.text) attachProjectedReasoning(state, event, event.text, options);
    state.messages = closeReasoningStream(
      state.messages,
      options.persisted ? undefined : options.now,
      turnFieldsForProjection(state, event, "reasoning"),
      event.stream_id,
    );
    return state;
  }

  if (event.event === "context_compaction") {
    Object.assign(state, closeThreadProjectionAnswer(state));
    const id = `compaction-${event.compaction_id}`;
    const existing = state.messages.findIndex((message) => message.id === id);
    const message: UIMessage = {
      id,
      role: "assistant",
      content: "",
      kind: "compaction",
      createdAt: projectionCreatedAt(event, options),
      compaction: {
        id: event.compaction_id,
        phase: event.phase,
        reason: event.reason,
        ...(event.error !== undefined ? { error: event.error } : {}),
        ...(event.context_tokens !== undefined ? { context_tokens: event.context_tokens } : {}),
        ...(event.context_window_tokens !== undefined ? { context_window_tokens: event.context_window_tokens } : {}),
        ...(event.evidence_checkpoint ? { evidence_checkpoint: true } : {}),
        ...(event.learning_failure ? { learning_failure: event.learning_failure } : {}),
        ...(event.learning_retry ? { learning_retry: event.learning_retry } : {}),
        ...(event.context_estimated !== undefined ? { context_estimated: event.context_estimated } : {}),
        ...(!options.persisted ? { announce: true } : {}),
      },
      ...positionedTurnFields(state.messages[existing], turnFieldsForProjection(state, event, "activity"), options),
    };
    if (existing < 0) state.messages = [...state.messages, message];
    else state.messages = replaceMessageAt(state.messages, existing, {
      ...message,
      createdAt: state.messages[existing].createdAt,
    });
    options.effects?.bodyWrites.add(id);
    state.activitySegmentId = null;
    state.fileEditSegmentId = null;
    return state;
  }

  if (event.event === "message") {
    if (
      state.suppressUntilTurnEnd
      && (event.kind === "tool_hint" || event.kind === "progress" || event.kind === "reasoning")
    ) return state;
    if (event.kind === "reasoning") {
      if (event.text) {
        attachProjectedReasoning(state, {
          ...event,
          event: "reasoning_delta",
        }, event.text, options);
        state.messages = closeReasoningStream(
          state.messages,
          options.persisted ? undefined : options.now,
        );
      }
      return state;
    }
    if (event.kind === "tool_hint" || event.kind === "progress") {
      projectToolActivity(state, event, options);
      return state;
    }

    const questionCancellation = parseQuestionCancellation(event.agent_ui);
    if (questionCancellation) {
      const id = `question-cancelled-${questionCancellation.id}`;
      if (!state.messages.some(message => message.id === id)) {
        state.messages = [...state.messages, { id, role: "assistant", content: "", questionCancellation,
          createdAt: projectionCreatedAt(event, options) }];
        options.effects?.bodyWrites.add(id);
      }
      return state;
    }
    const media = event.media_urls?.map((item) => toMediaAttachment(item))
      ?? event.media?.map((url) => toMediaAttachment({ url }));
    const latencyMs = typeof event.latency_ms === "number" && event.latency_ms >= 0
      ? Math.round(event.latency_ms)
      : undefined;
    const userQuestion = parseUserQuestion(event.agent_ui);
    const projected = {
      content: event.text,
      ...(userQuestion ? { userQuestion } : {}),
      ...(event.render_as === "text" ? { renderAs: event.render_as } : {}),
      ...(media?.length ? { media } : {}),
      ...(latencyMs !== undefined ? { latencyMs } : {}),
      ...(event.source ? { source: event.source } : {}),
      ...(event.response_sources !== undefined ? { responseSources: event.response_sources } : {}),
      ...positionedTurnFields(
        options.sideChannel ? undefined : state.messages.find((message) => message.id === state.activeAssistantId),
        turnFieldsForProjection(state, event, "answer"),
        options,
      ),
    };
    if (userQuestion) {
      Object.assign(state, closeThreadProjectionAnswer(state));
      absorbProjectedAssistantMessage(state, event, projected, options);
      state.activitySegmentId = null;
      state.fileEditSegmentId = null;
      return state;
    }
    if (options.sideChannel) {
      absorbProjectedAssistantMessage(state, event, projected, options);
      return state;
    }
    const activeId = state.activeAssistantId;
    Object.assign(state, closeThreadProjectionAnswer(state));
    if (activeId) {
      state.messages = state.messages.filter((message) => {
        if (message.id !== activeId) return true;
        options.effects?.consumed.add(message.id);
        return false;
      });
    }
    absorbProjectedAssistantMessage(state, event, projected, options);
    state.activitySegmentId = null;
    state.fileEditSegmentId = null;
    if (media?.length) state.suppressUntilTurnEnd = true;
    return state;
  }

  if (event.event === "file_edit") {
    projectFileEdits(state, event, options);
    return state;
  }

  const turn = turnFieldsForProjection(state, event, "complete");
  state.suppressUntilTurnEnd = false;
  state.activitySegmentId = null;
  state.fileEditSegmentId = null;
  state.messages = finalizeStreamedTurn(state.messages);
  const latencyMs = typeof event.latency_ms === "number" && event.latency_ms >= 0
    ? Math.round(event.latency_ms)
    : undefined;
  state.messages = stampLastAssistantCompletion(
    state.messages,
    {
      ...(latencyMs !== undefined ? { latencyMs } : {}),
      ...(event.usage ? { usage: event.usage } : {}),
      ...(event.round_usages?.length ? { roundUsages: event.round_usages } : {}),
      ...(typeof event.context_window_tokens === "number"
        ? { contextWindowTokens: event.context_window_tokens }
        : {}),
      ...(!options.persisted ? { completedAt: options.now } : {}),
    },
    turn.turnId,
  );
  state.activeAssistantId = null;
  state.closedAssistantIds.clear();
  state.closedAnswerStreamIds.clear();
  state.mergeReasoning = false;
  if (event.turn_id) {
    if (state.turnAliases.has(event.turn_id)) state.turnAliases.delete(event.turn_id);
    else state.closedTurnIds.add(event.turn_id);
  }
  return state;
}

export function projectThreadEvents(events: ThreadProjectionEvent[]): UIMessage[] {
  let state = createThreadProjectionState();
  events.forEach((event, index) => {
    state = projectThreadEvent(state, event, {
      createId: () => `history-${index}`,
      now: 0,
      persisted: true,
    });
  });
  return state.messages.map((row) => {
    const message = { ...row };
    delete message.isStreaming;
    delete message.reasoningStreaming;
    return message;
  });
}
