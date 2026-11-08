import { Disclosure } from "@heroui/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { MarkdownText } from "@/components/MarkdownText";
import type { MessageBubbleProps } from "../contracts";
import { MessageMedia } from "./MessageMedia";

export function SystemMessage({
  message,
  onOpenFilePreview,
}: MessageBubbleProps) {
  const { t } = useTranslation(),
    [expanded, setExpanded] = useState(false),
    origin = message.inputOrigin!;
  const label = t(`thread.inputSources.${origin.kind}`);
  return (
    <Disclosure
      data-system-input
      isExpanded={expanded}
      onExpandedChange={setExpanded}
      className="message-system"
    >
      <Disclosure.Heading>
        <Disclosure.Trigger>
          {label}
          {origin.kind !== "heartbeat" && origin.label && ` · ${origin.label}`}
          <Disclosure.Indicator />
        </Disclosure.Trigger>
      </Disclosure.Heading>
      <Disclosure.Content>
        <Disclosure.Body>
          {expanded && (
            <>
              <MarkdownText onOpenFilePreview={onOpenFilePreview}>
                {message.content}
              </MarkdownText>
              <MessageMedia
                images={message.images}
                media={message.media}
                align="left"
              />
            </>
          )}
        </Disclosure.Body>
      </Disclosure.Content>
    </Disclosure>
  );
}
