/** Input receipts and cross-conversation provenance in the projected transcript. */
import type { InboundEvent } from "@/lib/contracts/events";
import type { UIMessage, MessageDeliveryStatus } from "@/lib/contracts/messages";
import { turnFieldsFromEvent } from "./turns";

export function transitionTurnDelivery(
  messages: UIMessage[],
  turnId: string,
  status: MessageDeliveryStatus,
): UIMessage[] {
  let changed = false;
  const next = messages.map((message) => {
    if (
      message.role !== "user"
      || message.turnId !== turnId
      || message.deliveryStatus === status
      || (status === "accepted" && message.deliveryStatus !== "sending")
    ) {
      return message;
    }
    changed = true;
    return { ...message, deliveryStatus: status };
  });
  return changed ? next : messages;
}

export function appendProjectedSessionInput(
  messages: UIMessage[],
  event: Extract<InboundEvent, { event: "user_message" }>,
): UIMessage[] {
  const sessionMessage = event.provenance?.session_message;
  const messageId = sessionMessage?.message_id?.trim();
  if (!sessionMessage || !messageId) return messages;
  if (messages.some((message) => message.sessionMessage?.message_id === messageId)) return messages;

  const row: UIMessage = {
    id: `session-message:${messageId}`,
    role: "user",
    content: event.text,
    createdAt: typeof event.created_at_ms === "number"
      && Number.isFinite(event.created_at_ms)
      ? event.created_at_ms
      : Date.now(),
    sessionMessage,
    ...turnFieldsFromEvent(event, "user"),
  };
  return [...messages, row];
}
