import { liveContextUsage, visibleContextTokens } from "@/lib/live-context";
import { useEffect, useMemo, useState } from "react";
import { latestComposerContextUsage, recentComposerRoundUsage } from "./composer-usage";

import type {
  ComposerContextUsage
} from "@/components/thread/ComposerUsagePopover";
import type { UIMessage } from "@/lib/contracts/messages";
import { useClient } from "@/providers/ClientProvider";

export function useThreadUsage(displayMessages: UIMessage[], previewSessionKey: string | null, isStreaming: boolean) {
  const { client } = useClient();
  const recordedContextUsage = useMemo(
    () => latestComposerContextUsage(displayMessages),
    [displayMessages],
  );
  const lastCompactionId = [...displayMessages].reverse().find(message => message.kind === "compaction"
    && message.compaction?.phase === "succeeded")?.compaction?.id;
  const [measuredContext, setMeasuredContext] = useState<{
    key: string; compactionId: string | undefined; usage?: ComposerContextUsage; error?: string; visibleTokens?: number;
  } | null>(null);
  const needsContextMeasurement = recordedContextUsage === null;
  useEffect(() => {
    if (!previewSessionKey || !needsContextMeasurement || displayMessages.length === 0) return;
    let cancelled = false;
    const visibleTokens = visibleContextTokens(displayMessages);
    void client.requestMutation<{ context_tokens: number; context_window_tokens: number; estimated: boolean }>(
      "session.context_usage", { session_key: previewSessionKey },
    ).then(value => {
      if (!cancelled) setMeasuredContext({
        key: previewSessionKey, compactionId: lastCompactionId,
        visibleTokens, usage: { contextTokens: value.context_tokens, contextWindowTokens: value.context_window_tokens, estimated: value.estimated }
      });
    }).catch((error: Error) => {
      if (!cancelled) setMeasuredContext({ key: previewSessionKey, compactionId: lastCompactionId, error: error.message });
    });
    return () => { cancelled = true; };
  }, [client, previewSessionKey, lastCompactionId, needsContextMeasurement, isStreaming, displayMessages.length]);
  const currentMeasurement = measuredContext?.key === previewSessionKey && measuredContext?.compactionId === lastCompactionId ? measuredContext : null;
  const composerContextUsage = liveContextUsage(recordedContextUsage ?? currentMeasurement?.usage ?? null, displayMessages, isStreaming, currentMeasurement?.visibleTokens);
  const composerContextError = needsContextMeasurement ? currentMeasurement?.error : undefined;
  const composerRoundUsage = useMemo(
    () => recentComposerRoundUsage(displayMessages),
    [displayMessages],
  );

  return { composerContextUsage, composerContextError, composerRoundUsage };
}
