import type { UIMessage } from "@/lib/contracts/messages";

export type MessageVariant =
  | "compaction"
  | "tool"
  | "incoming"
  | "system"
  | "user"
  | "assistant"
  | "hidden";

export function messageVariant(message: UIMessage): MessageVariant {
  if (message.kind === "compaction" && message.compaction) return "compaction";
  if (message.kind === "trace") return "tool";
  if (message.role === "user") {
    if (
      message.sessionMessage &&
      (!message.inputOrigin || message.inputOrigin.kind === "supervision")
    )
      return "incoming";
    return message.inputOrigin ? "system" : "user";
  }
  return message.userQuestion ? "hidden" : "assistant";
}
