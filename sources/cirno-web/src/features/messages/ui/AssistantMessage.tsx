import { useTranslation } from "react-i18next";
import { CodeBlock } from "@/components/CodeBlock";
import { MarkdownText } from "@/components/MarkdownText";
import { InlineImageProvider } from "@/components/InlineImageContext";
import { ReasoningRow } from "@/components/thread/activity/ReasoningRow";
import { StreamingLabelSheen } from "@/components/ui/streaming-label-sheen";
import type { MessageBubbleProps } from "../contracts";
import { messageCopyContent } from "../model/copyContent";
import { MessageMedia } from "./MessageMedia";

export function AssistantMessage({
  message,
  assistantBubble,
  onOpenFilePreview,
}: MessageBubbleProps) {
  const { t } = useTranslation(),
    content = messageCopyContent(message, t),
    empty = !content.trim();
  const reasoning =
    message.role === "assistant" ? (message.reasoning ?? "") : "";
  const thinking = Boolean(
    message.role === "assistant" && message.reasoningStreaming,
  );
  const hasReasoning = Boolean(reasoning || thinking);
  return (
    <div
      data-assistant-message
      data-assistant-bubble={assistantBubble || undefined}
      className={`message-assistant ${assistantBubble ? "message-assistant-bubble" : ""}`}
    >
      {hasReasoning && (
        <ReasoningRow
          text={reasoning}
          streaming={thinking}
          className={!empty ? "mb-2" : undefined}
        />
      )}
      {empty && message.isStreaming ? (
        !hasReasoning && (
          <span
            aria-label={t("message.assistantTyping")}
            className="message-thinking"
          >
            <StreamingLabelSheen active>
              {t("message.reasoningStreaming")}
            </StreamingLabelSheen>
          </span>
        )
      ) : (
        <InlineImageProvider>
          <div
            data-assistant-selectable={message.isStreaming ? undefined : "true"}
          >
            {message.renderAs === "text" ? (
              <CodeBlock
                language="text"
                code={content}
                chrome="none"
                highlight={false}
                ansi={false}
              />
            ) : (
              <MarkdownText
                streaming={Boolean(message.isStreaming)}
                preserveStreamingLayout
                onOpenFilePreview={onOpenFilePreview}
              >
                {content}
              </MarkdownText>
            )}
          </div>
          <MessageMedia
            images={message.images}
            media={message.media}
            align="left"
          />
        </InlineImageProvider>
      )}
    </div>
  );
}
