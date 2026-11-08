import type { UIMessage, UITurnPhase } from "@/lib/contracts/messages";
import type { UIMessageTurnFields, ThreadProjectionOptions } from "./contracts";

export function turnFieldsFromEvent(
  ev: { turn_id?: string; turn_phase?: UITurnPhase; turn_seq?: number },
  fallbackPhase?: UITurnPhase,
): UIMessageTurnFields {
  const fields: UIMessageTurnFields = {};
  if (typeof ev.turn_id === "string" && ev.turn_id.length > 0) {
    fields.turnId = ev.turn_id;
  }
  const phase = ev.turn_phase ?? fallbackPhase;
  if (phase) fields.turnPhase = phase;
  if (typeof ev.turn_seq === "number" && Number.isFinite(ev.turn_seq)) {
    fields.turnSeq = ev.turn_seq;
  }
  return fields;
}

export function matchesTurn(message: UIMessage, turn: UIMessageTurnFields): boolean {
  return !turn.turnId || !message.turnId || message.turnId === turn.turnId;
}

export function positionedTurnFields(
  target: UIMessage | undefined,
  turn: UIMessageTurnFields,
  options: ThreadProjectionOptions,
): UIMessageTurnFields & Pick<UIMessage, "projectionStartSeq"> {
  const start = target?.projectionStartSeq ?? target?.turnSeq ?? options.startSeq ?? turn.turnSeq;
  return { ...turn, ...(start !== undefined ? { projectionStartSeq: start } : {}) };
}

/** Find a still-open streamed assistant turn. Closed stream segments stay visible
 * as streaming until ``turn_end`` for visual continuity, but they must not
 * receive later delta segments. */
export function findStreamingAssistantIndex(
  prev: UIMessage[],
  closedStreamIds: ReadonlySet<string>,
  turn: UIMessageTurnFields = {},
  streamId?: string,
): number | null {
  for (let i = prev.length - 1; i >= 0; i -= 1) {
    const m = prev[i];
    if (m.kind === "trace") continue;
    if (
      m.role === "assistant"
      && m.isStreaming
      && !closedStreamIds.has(m.id)
      && (!streamId || !m.streamId || m.streamId === streamId)
      && matchesTurn(m, turn)
    ) return i;
    if (m.role === "user") break;
  }
  return null;
}

/**
 * Find the most recent assistant placeholder that an incoming answer
 * delta should adopt instead of spawning a parallel row.
 */
export function findActiveAssistantPlaceholderIndex(
  prev: UIMessage[],
  turn: UIMessageTurnFields = {},
): number | null {
  const last = prev[prev.length - 1];
  if (!last) return null;
  if (last.role !== "assistant" || last.kind === "trace") return null;
  if (last.content.length > 0) return null;
  if (!last.isStreaming) return null;
  if (!matchesTurn(last, turn)) return null;
  return prev.length - 1;
}

export function replaceMessageAt(
  prev: UIMessage[],
  index: number,
  message: UIMessage,
): UIMessage[] {
  const next = prev.slice();
  next[index] = message;
  return next;
}

/** Close the active reasoning stream segment. ``now`` is supplied by the caller
 * so the projection remains deterministic for replay and fixture tests. */
export function closeReasoningStream(prev: UIMessage[], now?: number, turn: UIMessageTurnFields = {}, streamId?: string): UIMessage[] {
  const identifiedIndex = streamId ? prev.findIndex((message) => (
    message.reasoningStreamId === streamId && matchesTurn(message, turn)
  )) : -1;
  for (let i = prev.length - 1; i >= 0; i -= 1) {
    if (identifiedIndex >= 0 && i !== identifiedIndex) continue;
    const candidate = prev[i];
    if (!candidate.reasoningStreaming || !matchesTurn(candidate, turn)
      || (streamId && candidate.reasoningStreamId && streamId !== candidate.reasoningStreamId)) continue;
    const latencyMs =
      now !== undefined
      && candidate.latencyMs === undefined
      && Number.isFinite(candidate.createdAt)
      && candidate.createdAt > 1_000_000_000_000
        ? Math.max(0, Math.round(now - candidate.createdAt))
        : candidate.latencyMs;
    const merged: UIMessage = {
      ...candidate,
      reasoningStreaming: false,
      ...(latencyMs !== undefined ? { latencyMs } : {}),
    };
    return [...prev.slice(0, i), merged, ...prev.slice(i + 1)];
  }
  return prev;
}

export function isReasoningOnlyPlaceholder(message: UIMessage): boolean {
  return (
    message.role === "assistant"
    && message.kind !== "trace"
    && message.content.trim().length === 0
    && !!message.reasoning
    && !message.reasoningStreaming
    && !message.media?.length
  );
}

export function stampLastAssistantCompletion(
  prev: UIMessage[],
  completion: Pick<
    UIMessage,
    "latencyMs" | "completedAt" | "usage" | "roundUsages" | "contextWindowTokens"
  >,
  turnId?: string,
): UIMessage[] {
  for (let i = prev.length - 1; i >= 0; i -= 1) {
    const m = prev[i];
    if (
      m.role === "assistant"
      && m.kind !== "trace"
      && (!turnId || !m.turnId || m.turnId === turnId)
    ) {
      const merged: UIMessage = { ...m, ...completion, isStreaming: false };
      return [...prev.slice(0, i), merged, ...prev.slice(i + 1)];
    }
  }
  return prev;
}

export function finalizeStreamedTurn(
  prev: UIMessage[],
  turn: UIMessageTurnFields = {},
): UIMessage[] {
  return prev.map((m) =>
    m.isStreaming && matchesTurn(m, turn)
      ? { ...m, isStreaming: false, reasoningStreaming: false }
      : m,
  );
}
