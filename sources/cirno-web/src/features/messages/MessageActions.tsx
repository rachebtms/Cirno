import { Check, Copy, GitFork, SquarePen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatMessageEndTime } from "@/lib/format-time";
import type { MessageActionsProps } from "./contracts";
import { messageCopyContent } from "./model/copyContent";
import { useMessageCopy } from "./model/useMessageCopy";
import { MessageActionButton } from "./ui/MessageActionButton";
import { FallbackResponseSources } from "./ui/ResponseSources";
import "./messages.css";

/** Actions stay next to the timestamp on pointer and touch devices. */
export function MessageActions({
  message,
  isTurnStreaming = false,
  onForkFromHere,
  onEdit,
}: MessageActionsProps) {
  const { t } = useTranslation(),
    content = messageCopyContent(message, t),
    copy = useMessageCopy(content);
  const hasText = Boolean(content.trim()),
    user = message.role === "user";
  const human = user && !message.inputOrigin && !message.sessionMessage;
  const editable = human && !isTurnStreaming && onEdit;
  const forkable =
    !user &&
    !message.isStreaming &&
    !isTurnStreaming &&
    hasText &&
    onForkFromHere;
  const timestamp =
    !user &&
    typeof message.completedAt === "number" &&
    Number.isFinite(message.completedAt)
      ? message.completedAt
      : message.createdAt;
  const timestampLabel = Number.isFinite(timestamp)
    ? formatMessageEndTime(timestamp)
    : "";
  const time = timestampLabel && (
    <time
      data-message-timestamp
      data-message-created-at={user || undefined}
      data-assistant-completed-at={
        (!user && timestamp === message.completedAt) || undefined
      }
      dateTime={new Date(timestamp).toISOString()}
    >
      {timestampLabel}
    </time>
  );
  const automation =
    !user &&
    ["cron", "local_trigger", "trigger"].includes(message.source?.kind ?? "")
      ? message.source?.label?.trim() || t("message.automationSourceFallback")
      : null;
  return (
    <div
      data-message-actions
      className={`message-actions ${human ? "message-actions-end" : ""}`}
    >
      <div
        role="group"
        aria-label={t("message.actions")}
        data-message-block-toolbar
        className="message-toolbar"
      >
        {human && time}
        {hasText && (
          <MessageActionButton
            label={copy.label}
            isDisabled={copy.busy}
            onPress={() => {
              void copy.copy();
            }}
            data-message-block-copy-action
            data-assistant-copy-action={!user || undefined}
          >
            {copy.copied ? (
              <Check size={16} aria-hidden />
            ) : (
              <Copy size={16} aria-hidden />
            )}
          </MessageActionButton>
        )}
        {editable && (
          <MessageActionButton
            label={t("message.edit")}
            onPress={onEdit}
            data-message-edit-action
          >
            <SquarePen size={16} aria-hidden />
          </MessageActionButton>
        )}
        {forkable && (
          <MessageActionButton
            label={t("message.forkFromHere")}
            onPress={onForkFromHere}
            data-message-block-fork-action
            data-assistant-fork-action
          >
            <GitFork size={16} aria-hidden />
          </MessageActionButton>
        )}
        {!human && time}
      </div>
      {copy.error && (
        <span role="alert" className="message-action-error">
          {copy.error}
        </span>
      )}
      <FallbackResponseSources
        sources={!user ? message.responseSources : undefined}
      />
      {automation && (
        <span data-automation-trigger className="message-source-caption">
          {t("message.automationTriggered")} {automation}
        </span>
      )}
    </div>
  );
}
