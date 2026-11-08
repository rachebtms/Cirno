import type { ComponentType } from "react";
import { ContextCompactionNotice } from "@/components/thread/ContextCompactionNotice";
import type { MessageBubbleProps } from "./contracts";
import { messageVariant, type MessageVariant } from "./model/messageVariant";
import { UserMessage } from "./ui/UserMessage";
import { AssistantMessage } from "./ui/AssistantMessage";
import { IncomingMessage } from "./ui/IncomingMessage";
import { SystemMessage } from "./ui/SystemMessage";
import { ToolMessages } from "./ui/ToolMessages";
import "./messages.css";

const views: Record<MessageVariant, ComponentType<MessageBubbleProps>> = {
  user: UserMessage,
  assistant: AssistantMessage,
  incoming: IncomingMessage,
  system: SystemMessage,
  tool: ToolMessages,
  compaction: ({ message }) => (
    <ContextCompactionNotice compaction={message.compaction!} />
  ),
  hidden: () => null,
};

export function MessageBubble(props: MessageBubbleProps) {
  const variant = messageVariant(props.message),
    View = views[variant];
  return <View key={variant} {...props} />;
}
