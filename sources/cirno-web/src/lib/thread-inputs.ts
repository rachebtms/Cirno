import type { UIMessage } from "@/lib/contracts/messages";

/** Match the server's model-input count when branching or paging history. */
export function isModelInput(message: UIMessage): boolean {
  return message.role === "user" && message.deliveryStatus !== "failed"
    && !["supervision", "subagent", "continuation"].includes(message.inputOrigin?.kind ?? "");
}

/** Tool traces can be text-only or deferred; both can represent real side effects. */
export function hasToolHistory(message: UIMessage): boolean {
  return message.role === "tool" || message.kind === "trace"
    || Boolean(message.toolEvents?.length || message.fileEdits?.length || message.traceDetail?.traceCount);
}
