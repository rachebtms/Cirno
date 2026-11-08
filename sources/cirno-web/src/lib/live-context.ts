import type { UIMessage } from "@/lib/contracts/messages";
import type { ComposerContextUsage } from "@/components/thread/ComposerUsagePopover";

/** A display estimate, never a provider usage or billing measurement. */
function textTokens(value: string): number {
  const wide = value.match(/[\u2e80-\u9fff\uac00-\ud7af\uf900-\ufaff]/gu)?.length ?? 0;
  return Math.ceil(wide + (value.length - wide) / 4);
}

export function visibleContextTokens(messages: UIMessage[]): number {
  let tokens = 0;
  for (const message of messages) {
    if (message.kind === "compaction") continue;
    const events = message.toolEvents ?? [];
    if (message.kind !== "trace" || events.length === 0) tokens += textTokens(message.content || "");
    if (message.reasoning && message.reasoning !== message.content) tokens += textTokens(message.reasoning);
    for (const event of events) {
      // Start/end updates for a call have already been merged by call_id.
      tokens += textTokens(JSON.stringify(event.arguments ?? {}));
      if (event.result != null) tokens += textTokens(typeof event.result === "string" ? event.result : JSON.stringify(event.result));
    }
  }
  return tokens;
}

export function liveContextUsage(base: ComposerContextUsage | null, messages: UIMessage[], running: boolean,
  measuredVisibleTokens?: number): ComposerContextUsage | null {
  if (!base || !running) return base;
  let anchor = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message.kind === "compaction" && message.compaction?.phase === "succeeded"
      || message.role === "assistant" && !message.isStreaming && message.usage?.context_tokens !== undefined) {
      anchor = i; break;
    }
  }
  const previous = anchor >= 0 ? messages[anchor] : null;
  const lastOutput = previous?.roundUsages?.at(-1)?.completion_tokens ?? 0;
  const added = anchor >= 0 ? visibleContextTokens(messages.slice(anchor + 1)) + lastOutput
    : Math.max(0, visibleContextTokens(messages) - (measuredVisibleTokens ?? 0));
  return { ...base, contextTokens: base.contextTokens + added, estimated: true };
}
