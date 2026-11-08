
import type {
  ComposerContextUsage,
  ComposerRoundUsage,
} from "@/components/thread/ComposerUsagePopover";
import type { StreamError } from "@/lib/cirno-client";
import type { RoundUsage, UIMessage } from "@/lib/contracts/messages";

export function latestComposerContextUsage(messages: UIMessage[]): ComposerContextUsage | null {
  for (let index = messages.length - 1;index >= 0;index -= 1) {
    const message = messages[index];
    if (message.kind === "compaction" && message.compaction?.phase === "succeeded") {
      return message.compaction.context_tokens === undefined ? null : {
        contextTokens: message.compaction.context_tokens,
        contextWindowTokens: message.compaction.context_window_tokens,
        estimated: message.compaction.context_estimated,
      };
    }
    const contextTokens = message.usage?.context_tokens;
    if (
      message.role !== "assistant"
      || message.kind === "trace"
      || message.isStreaming
      || typeof contextTokens !== "number"
      || !Number.isFinite(contextTokens)
      || contextTokens < 0
    ) {
      continue;
    }
    return {
      contextTokens,
      ...(typeof message.contextWindowTokens === "number"
        ? { contextWindowTokens: message.contextWindowTokens }
        : {}),
    };
  }
  return null;
}

export function recentComposerRoundUsage(messages: UIMessage[]): ComposerRoundUsage[] {
  const recent: ComposerRoundUsage[] = [];
  const seenTurns = new Set<string>();
  for (let index = messages.length - 1;index >= 0 && recent.length < 8;index -= 1) {
    const message = messages[index];
    const turnKey = message.turnId || message.id;
    if (
      message.role !== "assistant"
      || message.kind === "trace"
      || message.isStreaming
      || seenTurns.has(turnKey)
    ) {
      continue;
    }

    seenTurns.add(turnKey);
    const rounds: RoundUsage[] = message.roundUsages ?? [];
    for (let roundIndex = rounds.length - 1;roundIndex >= 0;roundIndex -= 1) {
      const round = rounds[roundIndex];
      const inputTokens = round.prompt_tokens;
      if (
        recent.length >= 8
        || typeof inputTokens !== "number"
        || !Number.isFinite(inputTokens)
        || inputTokens <= 0
      ) {
        continue;
      }
      const outputTokens = round.completion_tokens;
      const cachedTokens = round.cached_tokens;
      const estimatedTokens = round.estimated_tokens;
      const generationMs = round.generation_ms;
      const measuredOutputTokens = round.measured_completion_tokens;
      const ttftMs = round.ttft_ms;
      const timedRequests = round.timed_requests;
      recent.push({
        id: `${turnKey}:${roundIndex}`,
        timestamp: message.completedAt ?? message.createdAt,
        inputTokens,
        ...(typeof outputTokens === "number" && Number.isFinite(outputTokens)
          ? { outputTokens }
          : {}),
        ...(typeof cachedTokens === "number" && Number.isFinite(cachedTokens)
          ? { cachedTokens }
          : {}),
        ...(typeof estimatedTokens === "number" && Number.isFinite(estimatedTokens)
          ? { estimatedTokens }
          : {}),
        ...(typeof generationMs === "number" && Number.isFinite(generationMs)
          ? { generationMs }
          : {}),
        ...(typeof measuredOutputTokens === "number" && Number.isFinite(measuredOutputTokens)
          ? { measuredOutputTokens }
          : {}),
        ...(typeof ttftMs === "number" && Number.isFinite(ttftMs) && ttftMs >= 0
          && typeof timedRequests === "number" && Number.isFinite(timedRequests) && timedRequests > 0
          ? { ttftMs: ttftMs / timedRequests }
          : {}),
      });
    }
  }
  return recent.reverse();
}

export function latestActiveTurnId(messages: UIMessage[], runStartedAt: number | null): string | null {
  for (let index = messages.length - 1;index >= 0;index -= 1) {
    const message = messages[index];
    if (message.isStreaming && message.turnId) return message.turnId;
  }
  if (runStartedAt === null) return null;
  for (let index = messages.length - 1;index >= 0;index -= 1) {
    const message = messages[index];
    if (
      message.role !== "user"
      && message.turnId
      && message.createdAt >= runStartedAt * 1000
    ) return message.turnId;
  }
  return null;
}

export function hasInlineDeliveryError(
  messages: UIMessage[],
  error: StreamError | null,
): boolean {
  if (!error?.turnId) return false;
  return messages.some((message) => (
    message.role === "user"
    && message.turnId === error.turnId
    && message.deliveryStatus === "failed"
    && message.deliveryErrorKind === error.kind
  ));
}
