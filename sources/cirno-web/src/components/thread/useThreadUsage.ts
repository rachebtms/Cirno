import { liveContextUsage, visibleContextTokens } from "@/lib/live-context";
import { useEffect, useEffectEvent, useMemo, useState } from "react";
import { composerRoundUsage as convertRoundUsage, latestComposerContextUsage, recentComposerRoundUsage } from "./composer-usage";

import type {
  ComposerContextUsage, ComposerRoundUsage,
} from "@/components/thread/ComposerUsagePopover";
import type { RoundUsage, UIMessage } from "@/lib/contracts/messages";
import { useClient } from "@/providers/ClientProvider";

export function useThreadUsage(displayMessages: UIMessage[], previewSessionKey: string | null, isStreaming: boolean) {
  const { client } = useClient();
  const recordedContextUsage = useMemo(
    () => latestComposerContextUsage(displayMessages),
    [displayMessages],
  );
  const lastCompactionId = [...displayMessages].reverse().find(message => message.kind === "compaction"
    && message.compaction?.phase === "succeeded")?.compaction?.id;
  const recordedRounds = useMemo(() => recentComposerRoundUsage(displayMessages), [displayMessages]);
  const [measuredContext, setMeasuredContext] = useState<{
    key: string; compactionId: string | undefined; usage?: ComposerContextUsage; error?: string; visibleTokens?: number;
    rounds?: ComposerRoundUsage[];
  } | null>(null);
  const needsContextMeasurement = recordedContextUsage === null;
  const hasMessages = displayMessages.length > 0;
  const needsRequestSnapshot = isStreaming || recordedRounds.length === 0;
  const measureVisibleTokens = useEffectEvent(() => visibleContextTokens(displayMessages));
  useEffect(() => {
    if (!previewSessionKey || (!needsContextMeasurement && !needsRequestSnapshot) || !hasMessages) return;
    let cancelled = false;
    const visibleTokens = measureVisibleTokens();
    void client.requestMutation<{
      context_tokens: number; context_window_tokens: number; estimated: boolean;
      recent_requests?: { id: string; timestamp: number; usage: RoundUsage }[];
    }>(
      "session.context_usage", { session_key: previewSessionKey },
    ).then(value => {
      if (!cancelled) setMeasuredContext({
        key: previewSessionKey, compactionId: lastCompactionId,
        rounds: (value.recent_requests ?? []).flatMap(request => {
          const round = convertRoundUsage(request.usage, request.id, request.timestamp);
          return round ? [round] : [];
        }),
        visibleTokens, usage: { contextTokens: value.context_tokens, contextWindowTokens: value.context_window_tokens, estimated: value.estimated }
      });
    }).catch((error: Error) => {
      if (!cancelled) setMeasuredContext({ key: previewSessionKey, compactionId: lastCompactionId, error: error.message });
    });
    return () => { cancelled = true; };
    // Capture visible text at measurement time; streaming deltas must not repeatedly
    // rebuild/tokenize the entire server-side prompt while this request is in flight.
  }, [client, previewSessionKey, lastCompactionId, needsContextMeasurement, needsRequestSnapshot, isStreaming, hasMessages]);
  const currentMeasurement = measuredContext?.key === previewSessionKey && measuredContext?.compactionId === lastCompactionId ? measuredContext : null;
  const composerContextUsage = liveContextUsage(recordedContextUsage ?? currentMeasurement?.usage ?? null, displayMessages, isStreaming, currentMeasurement?.visibleTokens);
  const composerContextError = needsContextMeasurement ? currentMeasurement?.error : undefined;
  const measuredRounds = currentMeasurement?.rounds ?? [];
  const composerRoundUsage = (measuredRounds.at(-1)?.timestamp ?? -1) > (recordedRounds.at(-1)?.timestamp ?? -1)
    ? measuredRounds : recordedRounds;

  return { composerContextUsage, composerContextError, composerRoundUsage };
}
