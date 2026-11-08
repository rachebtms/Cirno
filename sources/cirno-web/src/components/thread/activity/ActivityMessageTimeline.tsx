import { MarkdownText } from "@/components/MarkdownText";
import { FileEditGroup, type FileEditSummary } from "@/components/thread/activity/FileEditRow";
import { ReasoningRow } from "@/components/thread/activity/ReasoningRow";
import type { FileEditDisplayMode } from "@/features/preferences/store";
import {
  isReasoningOnlyAssistant
} from "@/lib/activity-timeline";
import type { CliAppInfo } from "@/lib/contracts/apps";
import type { McpPresetInfo } from "@/lib/contracts/mcp";
import type { UIMessage } from "@/lib/contracts/messages";
import {
  Fragment,
  memo,
  type ReactNode
} from "react";
import { ActivityTraceTimeline } from "./ActivityTraceTimeline";

export const ActivityMessageTimeline = memo(function ActivityMessageTimeline({
  messages,
  active,
  cliAppsByName,
  mcpPresetsByName,
  fileEditsByMessage,
  fileEditDisplayMode,
  onOpenFilePreview,
}: {
  messages: UIMessage[];
  active: boolean;
  cliAppsByName: Map<string, CliAppInfo>;
  mcpPresetsByName: Map<string, McpPresetInfo>;
  fileEditsByMessage: Map<string, FileEditSummary[]>;
  fileEditDisplayMode: FileEditDisplayMode;
  onOpenFilePreview?: (path: string) => void;
}) {
  const items: ReactNode[] = [];

  messages.forEach((message, index) => {
    if (message.activityKind === "model") {
      items.push(
        <ActivityModelMessage
          key={message.id}
          message={message}
          active={active}
          onOpenFilePreview={onOpenFilePreview}
        />,
      );
      return;
    }
    if (isReasoningOnlyAssistant(message)) {
      items.push(
        <ReasoningRow
          key={message.id}
          text={message.reasoning ?? ""}
          streaming={active && !!message.reasoningStreaming}
        />,
      );
      return;
    }
    if (message.kind === "trace") {
      const fileEdits = fileEditsByMessage.get(message.id) ?? [];
      items.push(
        <Fragment key={message.id}>
          <ActivityTraceTimeline
            message={message}
            active={active && index === messages.length - 1}
            cliAppsByName={cliAppsByName}
            mcpPresetsByName={mcpPresetsByName}
          />
          <FileEditGroup
            edits={fileEdits}
            displayMode={fileEditDisplayMode}
            onOpenFilePreview={onOpenFilePreview}
          />
        </Fragment>,
      );
    }
  });
  return <>{items}</>;
});

/**
 * Keep an intermediate assistant segment as normal Markdown. The activity
 * surface owns ordering and lifecycle, not a reduced rendering mode: users
 * should see the same prose, links, and code treatment before and after the
 * surrounding turn is folded.
 */
export function ActivityModelMessage({
  message,
  active,
  onOpenFilePreview,
}: {
  message: UIMessage;
  active: boolean;
  onOpenFilePreview?: (path: string) => void;
}) {
  if (!message.content.trim()) return null;
  return (
    <div
      data-testid="activity-model-message"
      data-assistant-selectable={active && message.isStreaming ? undefined : "true"}
      className="w-full min-w-0 py-1 text-reading"
    >
      <MarkdownText
        streaming={active && !!message.isStreaming}
        preserveStreamingLayout
        onOpenFilePreview={onOpenFilePreview}
      >
        {message.content}
      </MarkdownText>
    </div>
  );
}
