import { useTranslation } from "react-i18next";
import { MarkdownText } from "@/components/MarkdownText";
import { SessionHandleLabel } from "@/components/SessionHandleLabel";
import type { MessageBubbleProps } from "../contracts";
import { MessageMedia } from "./MessageMedia";

export function IncomingMessage({
  message,
  onOpenFilePreview,
}: MessageBubbleProps) {
  const { t } = useTranslation(),
    handle = message.sessionMessage!.session,
    origin = message.inputOrigin;
  const content =
    origin?.kind === "supervision"
      ? [
          t(
            `thread.supervision.actions.${origin.action?.replaceAll(".", "_")}`,
            { defaultValue: t("thread.supervision.changed") },
          ),
          ...Object.entries(origin.values ?? {}).map(
            ([key, value]) =>
              `${t(`thread.supervision.fields.${key}`)}: ${value}`,
          ),
        ].join("\n\n")
      : message.content;
  return (
    <div
      data-session-message
      className="message-incoming mr-auto w-fit max-w-[min(85%,36rem)]"
    >
      <div className="message-incoming-source">
        <SessionHandleLabel id={handle.id}>@{handle.name}</SessionHandleLabel>
      </div>
      <div
        data-theme-surface
        className="relative rounded-floating bg-secondary/70 px-4 py-2"
      >
        <div data-assistant-selectable="true">
          <MarkdownText
            preserveStreamingLayout
            onOpenFilePreview={onOpenFilePreview}
          >
            {content}
          </MarkdownText>
        </div>
        <MessageMedia
          media={message.media}
          images={message.images}
          align="left"
        />
      </div>
    </div>
  );
}
