import { Button, Disclosure } from "@heroui/react";
import { Wrench } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { MessageBubbleProps } from "../contracts";

const PAGE_SIZE = 200;

/** Closed history mounts no trace rows; opening a large group reveals it in pages. */
export function ToolMessages({ message }: MessageBubbleProps) {
  const { t } = useTranslation(),
    [expanded, setExpanded] = useState(false),
    [limit, setLimit] = useState(PAGE_SIZE);
  const lines = message.traces ?? [message.content];
  return (
    <Disclosure
      isExpanded={expanded}
      onExpandedChange={(open) => {
        setExpanded(open);
        if (!open) setLimit(PAGE_SIZE);
      }}
      className="message-tools"
    >
      <Disclosure.Heading>
        <Disclosure.Trigger>
          <Wrench size={14} aria-hidden />
          <span>
            {t(lines.length === 1 ? "message.toolSingle" : "message.toolMany", {
              count: lines.length,
            })}
          </span>
          <Disclosure.Indicator />
        </Disclosure.Trigger>
      </Disclosure.Heading>
      <Disclosure.Content>
        <Disclosure.Body>
          {expanded && (
            <>
              <ul>
                {lines.slice(0, limit).map((line, index) => (
                  <li key={index}>{line}</li>
                ))}
              </ul>
              {limit < lines.length && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onPress={() => setLimit((count) => count + PAGE_SIZE)}
                >
                  {t("message.loadMoreTools", {
                    count: Math.min(PAGE_SIZE, lines.length - limit),
                  })}
                </Button>
              )}
            </>
          )}
        </Disclosure.Body>
      </Disclosure.Content>
    </Disclosure>
  );
}
