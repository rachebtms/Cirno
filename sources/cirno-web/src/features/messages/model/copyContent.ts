import type { UIMessage } from "@/lib/contracts/messages";

export function messageCopyContent(
  message: UIMessage,
  t: (key: string) => string,
) {
  if (message.renderAs === "text") return message.content;
  if (message.role === "assistant" && message.compactReply)
    return t(`thread.compaction.${message.compactReply}`);
  return message.content;
}
