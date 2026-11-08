import { useTranslation } from "react-i18next";
import { parseQuotedUserMessage } from "@/lib/user-message-quote";
import type { MessageBubbleProps } from "../contracts";
import { UserText } from "./UserText";
import { MessageQuote } from "./MessageQuote";
import { MessageMedia } from "./MessageMedia";
import { DeliveryStatus } from "./DeliveryStatus";

export function UserMessage(props: MessageBubbleProps) {
  const { message, editor, temporary } = props,
    { t } = useTranslation();
  const { content, quotedContext } = parseQuotedUserMessage(message.content);
  return (
    <div
      className={`message-user ml-auto flex ${editor ? "message-user-editing" : ""}`}
    >
      <MessageMedia
        images={message.images}
        media={message.media}
        align="right"
        pending={message.deliveryStatus === "sending"}
      />
      {quotedContext && !editor && (
        <MessageQuote
          text={quotedContext}
          label={t("thread.composer.quotedContext")}
        />
      )}
      {editor ??
        (content.trim() && (
          <div
            data-user-text-bubble
            className="relative ml-auto w-fit max-w-full min-w-0"
          >
            <p
              data-theme-surface
              data-temporary-message={temporary || undefined}
              className={`message-user-text ml-auto w-fit rounded-floating ${temporary ? "border-dashed border-muted-foreground/40 bg-transparent" : "bg-secondary/70"}`}
            >
              <UserText {...props} text={content} />
            </p>
          </div>
        ))}
      <DeliveryStatus
        status={message.deliveryStatus}
        errorKind={message.deliveryErrorKind}
      />
    </div>
  );
}
