import {
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { Check, ChevronRight, CircleAlert, Clock3, Copy, Quote, Wrench, SquarePen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { DisclosureContent } from "@/components/ui/disclosure";

import { AttachmentTile } from "@/components/AttachmentTile";
import { CodeBlock } from "@/components/CodeBlock";
import { SessionHandleLabel } from "@/components/SessionHandleLabel";
import { FallbackResponseSources } from "@/components/ResponseSourceBadge";
import { ImageGallery } from "@/components/ImageGallery";
import { InlineImageProvider, useInlineImages } from "@/components/InlineImageContext";
import { INLINE_REFERENCE_HIGHLIGHT_COLOR, InlineTokenHighlight } from "@/components/InlineTokenHighlight";
import { MarkdownText } from "@/components/MarkdownText";
import { SlashCommandText } from "@/components/SlashCommandText";
import { ReasoningRow } from "@/components/thread/activity/ReasoningRow";
import { StreamingLabelSheen } from "@/components/ui/streaming-label-sheen";
import { ContextCompactionNotice } from "@/components/thread/ContextCompactionNotice";
import { UserMessageText } from "@/components/UserMessageText";
import { HoverHint } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { copyTextToClipboard } from "@/lib/clipboard";
import { formatMessageEndTime } from "@/lib/format-time";
import { toMediaAttachment } from "@/lib/media";
import { matchingSlashCommand } from "@/lib/slash-command";
import { parseQuotedUserMessage } from "@/lib/user-message-quote";
import type {
  CliAppInfo,
  McpPresetInfo,
  SlashCommand,
  UICliAppAttachment,
  UIMcpPresetAttachment,
  UIImage,
  UIMediaAttachment,
  UIMessage,
  MessageDeliveryErrorKind,
  MessageDeliveryStatus,
} from "@/lib/types";

interface MessageBubbleProps {
  message: UIMessage;
  editor?: ReactNode;
  /** Give temporary-chat user turns the dashed private-mode treatment. */
  temporary?: boolean;
  cliApps?: CliAppInfo[];
  mcpPresets?: McpPresetInfo[];
  slashCommands?: SlashCommand[];
  onOpenFilePreview?: (path: string) => void;
}

function ForkArrowIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M16 3h5v5" />
      <path d="M8 3H3v5" />
      <path d="m21 3-7.536 7.536A5 5 0 0 0 12 14.07V21" />
      <path d="m3 3 7.536 7.536A5 5 0 0 1 12 14.07V15" />
    </svg>
  );
}

function useMessageCopy(content: string) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const copyResetRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (copyResetRef.current !== null) {
        window.clearTimeout(copyResetRef.current);
      }
    };
  }, []);

  const onCopy = useCallback(() => {
    void copyTextToClipboard(content).then((ok) => {
      if (!ok) return;
      setCopied(true);
      if (copyResetRef.current !== null) {
        window.clearTimeout(copyResetRef.current);
      }
      copyResetRef.current = window.setTimeout(() => {
        setCopied(false);
        copyResetRef.current = null;
      }, 1_500);
    });
  }, [content]);

  const label = copied ? t("message.copiedReply") : t("message.copyReply");
  return { copied, label, onCopy };
}

function messageCopyContent(message: UIMessage, t: (key: string) => string) {
  if (message.renderAs === "text") return message.content;
  return message.role === "assistant" && message.compactReply === "empty"
    ? t("thread.compaction.empty")
    : message.role === "assistant" && message.compactReply === "failed"
      ? t("thread.compaction.failed")
      : message.content;
}

/** Shared copy behavior for desktop and mobile message footers. */
export function MessageCopyButton({ message, className }: { message: UIMessage; className?: string }) {
  const { t } = useTranslation();
  const content = messageCopyContent(message, t);
  const { copied, label, onCopy } = useMessageCopy(content);
  if (!content.trim()) return null;
  return <HoverHint content={label} side="top" align="center"><button type="button" data-message-block-copy-action
    data-assistant-copy-action={message.role === "assistant" || undefined}
    onClick={onCopy} aria-label={label}
    className={cn(
      "inline-flex h-[var(--message-block-control-size)] w-[var(--message-block-action-width)] items-center justify-center rounded-control",
      "text-muted-foreground transition-[color] hover:text-foreground",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transform-none",
      className,
    )}>
    {copied ? <Check className="h-4 w-4" strokeWidth={1.75} aria-hidden />
      : <Copy className="h-4 w-4" strokeWidth={1.75} aria-hidden />}
  </button></HoverHint>;
}

interface MessageActionsProps {
  message: UIMessage;
  isTurnStreaming?: boolean;
  onForkFromHere?: () => void;
  onEdit?: () => void;
}

/** Persistent controls beside each message's timestamp, on desktop and touch screens. */
export function MessageActions({ message, isTurnStreaming = false, onForkFromHere, onEdit }: MessageActionsProps) {
  const { t } = useTranslation();
  const hasText = messageCopyContent(message, t).trim().length > 0;
  const user = message.role === "user";
  const alignEnd = user && !message.inputOrigin && !message.sessionMessage;
  const showEdit = user && !message.inputOrigin && !message.sessionMessage && !isTurnStreaming && onEdit !== undefined;
  const showFork = !user && !message.isStreaming && !isTurnStreaming && hasText && onForkFromHere !== undefined;
  const timestamp = !user && typeof message.completedAt === "number" && Number.isFinite(message.completedAt)
    ? message.completedAt : message.createdAt;
  const timestampLabel = typeof timestamp === "number" && Number.isFinite(timestamp) ? formatMessageEndTime(timestamp) : "";
  const time = timestampLabel ? <time data-message-timestamp data-message-created-at={user || undefined}
    data-assistant-completed-at={!user && timestamp === message.completedAt || undefined}
    dateTime={new Date(timestamp).toISOString()} className="px-1 text-xs tabular-nums text-muted-foreground/80">{timestampLabel}</time> : null;
  const automationSourceLabel = !user && ["cron", "local_trigger", "trigger"].includes(message.source?.kind ?? "")
    ? message.source?.label?.trim() || t("message.automationSourceFallback") : "";
  const actionClass = "inline-flex h-[var(--message-block-control-size)] w-[var(--message-block-action-width)] items-center justify-center rounded-control text-muted-foreground/80 transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
  return <div data-message-actions className={cn("mt-1 flex min-w-0 flex-col gap-0.5", alignEnd ? "items-end" : "items-start")}>
    <div role="group" aria-label={t("message.actions")} data-message-block-toolbar className="flex min-w-0 flex-wrap items-center gap-0.5">
      {alignEnd ? time : null}
      {hasText ? <MessageCopyButton message={message} /> : null}
      {showEdit ? <HoverHint content={t("message.edit")} side="top"><button type="button" onClick={onEdit}
        aria-label={t("message.edit")} data-message-edit-action className={actionClass}><SquarePen className="h-4 w-4" aria-hidden /></button></HoverHint> : null}
      {showFork ? <HoverHint content={t("message.forkFromHere")} side="top"><button type="button" onClick={onForkFromHere}
        aria-label={t("message.forkFromHere")} data-message-block-fork-action data-assistant-fork-action className={actionClass}><ForkArrowIcon className="h-4 w-4" /></button></HoverHint> : null}
      {!alignEnd ? time : null}
    </div>
    <FallbackResponseSources sources={!user ? message.responseSources : undefined} />
    {automationSourceLabel ? <span data-automation-trigger className="text-xs text-muted-foreground">{t("message.automationTriggered")} {automationSourceLabel}</span> : null}
  </div>;
}

function deliveryErrorCopy(
  kind: MessageDeliveryErrorKind | undefined,
  t: (key: string) => string,
): { title: string; body: string } {
  switch (kind) {
    case "message_too_big":
      return {
        title: t("errors.messageTooBig.title"),
        body: t("errors.messageTooBig.body"),
      };
    case "workspace_scope_rejected":
      return {
        title: t("errors.workspaceScopeRejected.title"),
        body: t("errors.workspaceScopeRejected.body"),
      };
    case "turn_rejected":
    case undefined:
      return {
        title: t("errors.turnRejected.title"),
        body: t("errors.turnRejected.body"),
      };
    default: {
      const _exhaustive: never = kind;
      return { title: String(_exhaustive), body: "" };
    }
  }
}

function UserDeliveryStatus({
  status,
  errorKind,
}: {
  status: MessageDeliveryStatus | undefined;
  errorKind: MessageDeliveryErrorKind | undefined;
}) {
  const { t } = useTranslation();
  if (status !== "sending" && status !== "failed") return null;
  if (status === "sending") {
    return (
      <span
        role="status"
        className="inline-flex items-center gap-1 text-[12px] leading-none text-muted-foreground"
      >
        <Clock3 className="h-3.5 w-3.5" aria-hidden />
        {t("message.delivery.sending")}
      </span>
    );
  }

  const label = t("message.delivery.failed");
  const { title, body } = deliveryErrorCopy(errorKind, t);
  return (
    <>
      <HoverHint
        side="top"
        align="end"
        contentClassName="max-w-72 px-3 py-2.5 text-left"
        content={<>
          <p className="font-medium text-popover-foreground">{title}</p>
          <p className="mt-1 leading-relaxed text-muted-foreground">{body}</p>
        </>}
      >
          <button
            type="button"
            aria-label={`${label}: ${title}`}
            className={cn(
              "inline-flex items-center gap-1 rounded-sm text-[12px] leading-none",
              "text-destructive/80 transition-colors hover:text-destructive",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              "dark:text-red-400/80 dark:hover:text-red-400",
            )}
          >
            <CircleAlert className="h-3.5 w-3.5" aria-hidden />
            {label}
          </button>
      </HoverHint>
      <span role="alert" aria-live="assertive" className="sr-only">
        {title}. {body}
      </span>
    </>
  );
}

function IncomingSessionMessage({
  message,
  onOpenFilePreview,
}: {
  message: UIMessage;
  onOpenFilePreview?: (path: string) => void;
}) {
  const handle = message.sessionMessage!.session;
  const handleName = `@${handle.name}`;

  return (
    <div
      data-session-message
      className="group relative mr-auto w-fit min-w-0 max-w-[min(85%,36rem)] text-reading"
    >
      <div className="mb-1.5 flex items-center px-4 text-[12px] text-muted-foreground">
        <SessionHandleLabel id={handle.id}>{handleName}</SessionHandleLabel>
      </div>
      <div data-theme-surface className="relative min-w-0 rounded-floating bg-secondary/70 px-4 py-2">
        <div data-assistant-selectable="true" className="min-w-0">
          <MarkdownText
            preserveStreamingLayout
            onOpenFilePreview={onOpenFilePreview}
          >
            {message.content}
          </MarkdownText>
        </div>
      </div>
    </div>
  );
}

/** Render user turns as compact bubbles and assistant turns as document-like prose. */
export function MessageBubble({
  message,
  editor,
  temporary = false,
  cliApps = [],
  mcpPresets = [],
  slashCommands = [],
  onOpenFilePreview,
}: MessageBubbleProps) {
  const { t } = useTranslation();
  const mentionCliApps = useMemo(
    () => mergeCliMentionApps(cliApps, message.cliApps),
    [cliApps, message.cliApps],
  );
  const mentionMcpPresets = useMemo(
    () => mergeMcpMentionPresets(mcpPresets, message.mcpPresets),
    [mcpPresets, message.mcpPresets],
  );

  if (message.kind === "compaction" && message.compaction) {
    return <ContextCompactionNotice compaction={message.compaction} />;
  }

  if (message.kind === "trace") {
    return <TraceGroup message={message} />;
  }

  if (message.role === "user" && message.inputOrigin?.kind === "supervision" && message.sessionMessage) {
    const origin = message.inputOrigin;
    const action = t(`thread.supervision.actions.${origin.action?.replaceAll(".", "_")}`, { defaultValue: t("thread.supervision.changed") });
    const fields = Object.entries(origin.values ?? {}).map(([key, value]) =>
      `${t(`thread.supervision.fields.${key}`)}: ${value}`,
    );
    return <IncomingSessionMessage
      message={{ ...message, content: [action, ...fields].join("\n\n") }}
      onOpenFilePreview={onOpenFilePreview}
    />;
  }

  if (message.role === "user" && message.inputOrigin) {
    return (
      <details data-system-input className="mr-auto w-full min-w-0 rounded-xl border border-border/60 bg-secondary/30 px-4 py-3 text-ui">
        <summary className="cursor-pointer select-none text-muted-foreground">
          {t(`thread.inputSources.${message.inputOrigin.kind}`)}
          {message.inputOrigin.kind !== "heartbeat" && message.inputOrigin.label ? ` · ${message.inputOrigin.label}` : ""}
        </summary>
        <div className="mt-3 min-w-0 break-words text-reading"><MarkdownText onOpenFilePreview={onOpenFilePreview}>{message.content}</MarkdownText></div>
      </details>
    );
  }

  if (message.role === "user" && message.sessionMessage) {
    return (
      <IncomingSessionMessage
        message={message}
        onOpenFilePreview={onOpenFilePreview}
      />
    );
  }

  if (message.role === "user") {
    const images = message.images ?? [];
    const media = message.media ?? [];
    const hasImages = images.length > 0;
    const hasMedia = media.length > 0;
    const parsedMessage = parseQuotedUserMessage(message.content);
    const userContent = parsedMessage.content;
    const hasText = userContent.trim().length > 0;
    const showDeliveryStatus =
      message.deliveryStatus === "sending" || message.deliveryStatus === "failed";
    const quotedContext = parsedMessage.quotedContext;
    const slashCommand = matchingSlashCommand(userContent, slashCommands);
    const bangPrefix = /^(\s*)!/.exec(userContent);
    const messageText = bangPrefix ? (
      <>
        {bangPrefix[1]}
        <InlineTokenHighlight testId="message-shell-prefix" className="font-normal" color={INLINE_REFERENCE_HIGHLIGHT_COLOR}>
          <span className="opacity-90">!</span>
        </InlineTokenHighlight>
        {userContent.slice(bangPrefix[0].length)}
      </>
    ) : slashCommand ? (
      <>
        <SlashCommandText command={slashCommand.command} />
        <UserMessageText
          text={userContent.slice(slashCommand.command.length)}
          cliApps={mentionCliApps}
          mcpPresets={mentionMcpPresets}
          sessionMentions={message.sessionMentions}
        />
      </>
    ) : (
      <UserMessageText
        text={userContent}
        cliApps={mentionCliApps}
        mcpPresets={mentionMcpPresets}
        sessionMentions={message.sessionMentions}
      />
    );
    return (
      <div
        className={cn("group relative ml-auto flex min-w-0 flex-col items-end gap-1.5", editor ? "w-full" : "w-fit max-w-[min(85%,36rem)]")}
      >
        {hasImages ? <ImageGallery images={images} align="right" size="compact" /> : null}
        {!hasImages && hasMedia ? (
          <MessageMedia media={media} align="right" pending={message.deliveryStatus === "sending"} />
        ) : null}
        {quotedContext && !editor ? (
          <UserQuotedContext
            text={quotedContext}
            label={t("thread.composer.quotedContext")}
          />
        ) : null}
        {editor ?? (hasText ? (
          <div data-user-text-bubble className="relative ml-auto w-fit max-w-full min-w-0">
            <p
              data-theme-surface
              data-temporary-message={temporary ? "true" : undefined}
              className={cn(
                "ml-auto w-fit max-w-full min-w-0 rounded-floating px-4 py-2",
                "text-left text-reading whitespace-pre-wrap [overflow-wrap:anywhere]",
                temporary
                  ? "border border-dashed border-muted-foreground/40 bg-transparent"
                  : "bg-secondary/70",
              )}
            >
              {messageText}
            </p>
          </div>
        ) : null)}
        {showDeliveryStatus ? (
            <div className="flex min-h-8 items-center justify-end gap-1.5 text-muted-foreground">
              <UserDeliveryStatus
                status={message.deliveryStatus}
                errorKind={message.deliveryErrorKind}
              />
            </div>
        ) : null}
      </div>
    );
  }

  if (message.userQuestion) return null;

  const assistantContent = messageCopyContent(message, t);
  const empty = assistantContent.trim().length === 0;
  const media = message.media ?? [];
  const reasoning = message.role === "assistant" ? message.reasoning ?? "" : "";
  const reasoningStreaming = !!(message.role === "assistant" && message.reasoningStreaming);
  const hasReasoning = reasoning.length > 0 || reasoningStreaming;
  return (
    <div
      data-assistant-message
      className="group/assistant relative w-full text-reading"
    >
      {hasReasoning ? (
        <ReasoningBubble
          text={reasoning}
          streaming={reasoningStreaming}
          hasBodyBelow={!empty}
        />
      ) : null}
      {empty && message.isStreaming && !hasReasoning ? (
        <ThinkingState />
      ) : empty && message.isStreaming ? null : (
        <InlineImageProvider>
          <div data-assistant-selectable={message.isStreaming ? undefined : "true"}>
            {message.renderAs === "text" ? (
              <CodeBlock language="text" code={assistantContent} highlight={false} ansi={false} />
            ) : (
              /* A mode switch rebuilds Streamdown's subtree and moves the scroll anchor. */
              <MarkdownText
                streaming={!!message.isStreaming}
                preserveStreamingLayout
                onOpenFilePreview={onOpenFilePreview}
              >
                {assistantContent}
              </MarkdownText>
            )}
          </div>
          {media.length > 0 ? <MessageMedia media={media} align="left" /> : null}
        </InlineImageProvider>
      )}
    </div>
  );
}

function UserQuotedContext({ text, label }: { text: string; label: string }) {
  return (
    <blockquote
      data-theme-surface
      data-theme-ink
      className={cn(
        "ml-auto flex w-fit max-w-full min-w-0 items-start gap-2 rounded-control",
        "border border-border/60 bg-muted/35 px-3 py-2 text-left text-muted-foreground",
      )}
      aria-label={label}
    >
      <Quote className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <p className="min-w-0 line-clamp-3 whitespace-pre-wrap text-reading-small [overflow-wrap:anywhere]">
        {text}
      </p>
    </blockquote>
  );
}

function mergeMcpMentionPresets(
  presets: McpPresetInfo[],
  attachments: UIMcpPresetAttachment[] | undefined,
): McpPresetInfo[] {
  if (!attachments?.length) return presets;
  const byName = new Map(presets.map((preset) => [preset.name.toLowerCase(), preset]));
  for (const attachment of attachments) {
    const name = attachment.name?.trim();
    if (!name) continue;
    const existing = byName.get(name.toLowerCase());
    byName.set(name.toLowerCase(), {
      name,
      display_name: attachment.display_name || existing?.display_name || name,
      category: attachment.category || existing?.category || "mcp",
      description: existing?.description || "",
      docs_url: existing?.docs_url || "",
      transport: attachment.transport || existing?.transport || "mcp",
      requires: existing?.requires || "",
      note: existing?.note || "",
      install_supported: existing?.install_supported ?? true,
      installed: true,
      configured: attachment.configured ?? existing?.configured ?? true,
      available: existing?.available ?? true,
      status: attachment.status || existing?.status || "configured",
      logo_url: attachment.logo_url ?? existing?.logo_url ?? null,
      brand_color: attachment.brand_color ?? existing?.brand_color ?? null,
      required_fields: existing?.required_fields || [],
      connection_summary: existing?.connection_summary || "",
    });
  }
  return Array.from(byName.values());
}

function mergeCliMentionApps(
  cliApps: CliAppInfo[],
  attachments: UICliAppAttachment[] | undefined,
): CliAppInfo[] {
  if (!attachments?.length) return cliApps;
  const byName = new Map(cliApps.map((app) => [app.name.toLowerCase(), app]));
  for (const attachment of attachments) {
    const name = attachment.name?.trim();
    if (!name) continue;
    const existing = byName.get(name.toLowerCase());
    byName.set(name.toLowerCase(), {
      name,
      display_name: attachment.display_name || existing?.display_name || name,
      category: attachment.category || existing?.category || "cli",
      description: existing?.description || "",
      requires: existing?.requires || "",
      source: existing?.source || "attached",
      entry_point: attachment.entry_point || existing?.entry_point || "",
      install_supported: existing?.install_supported ?? true,
      installed: true,
      available: existing?.available ?? true,
      status: existing?.status || "installed",
      logo_url: attachment.logo_url ?? existing?.logo_url ?? null,
      brand_color: attachment.brand_color ?? existing?.brand_color ?? null,
      skill_installed: existing?.skill_installed ?? true,
    });
  }
  return Array.from(byName.values());
}

function MessageMedia({
  media,
  align,
  pending = false,
}: {
  media: UIMediaAttachment[];
  align: "left" | "right";
  pending?: boolean;
}) {
  const inlineImages = useInlineImages();
  if (media.length === 0) return null;
  const images: UIImage[] = [];
  const seen = new Set<string>();
  const videos: UIMediaAttachment[] = [];
  const files: UIMediaAttachment[] = [];
  for (const item of media) {
    const normalized = toMediaAttachment(item);
    if (normalized.kind === "image") {
      if (normalized.url && (inlineImages.has(normalized.url) || seen.has(normalized.url))) continue;
      if (normalized.url) seen.add(normalized.url);
      images.push({ url: normalized.url, name: normalized.name });
    } else if (normalized.kind === "video") {
      videos.push(normalized);
    } else {
      files.push(normalized);
    }
  }
  if (images.length === 0 && videos.length === 0 && files.length === 0) return null;

  return (
    <div
      className={cn(
        "mt-2 flex min-w-0 max-w-full flex-col gap-2",
        align === "right" ? "items-end" : "items-start",
      )}
    >
      {images.length > 0 ? (
        <ImageGallery images={images} align={align} size={align === "left" ? "large" : "compact"} />
      ) : null}
      {videos.map((item, i) => (
        <AttachmentTile key={`video-${i}`} attachment={item} pending={pending} className="my-0" />
      ))}
      {files.length > 0 ? (
        <div className={cn("flex w-full min-w-0 flex-wrap items-start gap-2", align === "right" && "justify-end")}>
          {files.map((item, i) => (
            <AttachmentTile key={`file-${i}`} attachment={item} pending={pending} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** Quiet pre-token state that occupies a stable line in the answer column. */
function ThinkingState() {
  const { t } = useTranslation();
  return (
    <span
      aria-label={t("message.assistantTyping")}
      className="inline-flex min-h-7 items-center py-1 text-[13px]"
    >
      <StreamingLabelSheen active>
        {t("message.reasoningStreaming", { defaultValue: "Thinking…" })}
      </StreamingLabelSheen>
    </span>
  );
}

interface ReasoningBubbleProps {
  text: string;
  streaming: boolean;
  hasBodyBelow: boolean;
}

function ReasoningBubble({
  text,
  streaming,
  hasBodyBelow,
}: ReasoningBubbleProps) {
  return (
    <ReasoningRow
      text={text}
      streaming={streaming}
      className={cn(
        "animate-in fade-in-0 slide-in-from-top-1 duration-200",
        hasBodyBelow && "mb-2",
      )}
    />
  );
}

interface TraceGroupProps {
  message: UIMessage;
}

/**
 * Collapsible group of tool-call / progress breadcrumbs. Defaults to
 * collapsed because tool traces are supporting evidence, not the answer.
 * A single click expands the exact calls when the user wants details.
 */
function TraceGroup({ message }: TraceGroupProps) {
  const { t } = useTranslation();
  const lines = message.traces ?? [message.content];
  const count = lines.length;
  const [open, setOpen] = useState(false);
  const [hasOpened, setHasOpened] = useState(false);
  const releaseContent = useCallback(() => setHasOpened(false), []);
  const contentId = useId();
  return (
    <div className="w-full">
      <button
        type="button"
        onClick={() => {
          if (!open) setHasOpened(true);
          setOpen((value) => !value);
        }}
        className={cn(
          "group flex w-full items-center gap-2 rounded-md px-2 py-1.5",
          "text-xs text-muted-foreground transition-colors hover:bg-muted/45",
        )}
        aria-expanded={open}
        aria-controls={contentId}
      >
        <Wrench className="h-3.5 w-3.5" aria-hidden />
        <span className="font-medium">
          {count === 1
            ? t("message.toolSingle")
            : t("message.toolMany", { count })}
        </span>
        <ChevronRight
          aria-hidden
          className={cn(
            "ml-auto h-3.5 w-3.5 transition-transform duration-200 motion-reduce:transition-none",
            open && "rotate-90",
          )}
        />
      </button>
      <DisclosureContent id={contentId} open={open} onExitComplete={releaseContent}>
        {hasOpened && <ul
          className="mt-1 space-y-0.5 border-l border-muted-foreground/20 pl-3"
        >
          {lines.map((line, i) => (
            <li
              key={i}
              className="whitespace-pre-wrap break-words font-mono text-[11.5px] leading-relaxed text-muted-foreground/90"
            >
              {line}
            </li>
          ))}
        </ul>}
      </DisclosureContent>
    </div>
  );
}
