import { FileEditGroup } from "@/components/thread/activity/FileEditRow";
import { ThinkingReasoningShell } from "@/components/thread/activity/ThinkingReasoningShell";
import { coalesceActivityMessages } from "@/components/thread/activity/activity-message-model";
import { useFileEditDisplayMode } from "@/hooks/useFileEditDisplayMode";
import type { UIMessage } from "@/lib/contracts/messages";
import { cn } from "@/lib/utils";
import {
  useMemo,
  type ReactNode
} from "react";
import { useTranslation } from "react-i18next";
import { FoldedAgentActivity } from "./activity/ActivityDisclosure";
import { AgentActivityClusterProps } from "./activity/activity-cluster-contracts";
import { isFileEditTraceLine, traceLines } from "./activity/activity-entries";
import { completedActivityDurationMs, formatActivityDuration } from "./activity/activity-summary";
import { summarizeFileEditsByMessage } from "./activity/file-edit-summary";

export function AgentActivityCluster(props: AgentActivityClusterProps) {
  const { t } = useTranslation();
  const displayMode = useFileEditDisplayMode();
  const messages = useMemo(() => coalesceActivityMessages(props.messages), [props.messages]);
  const editsByMessage = useMemo(
    () => summarizeFileEditsByMessage(messages, props.isTurnStreaming),
    [messages, props.isTurnStreaming],
  );
  if (props.defaultCollapsed || displayMode === "summary" || !editsByMessage.size) {
    return <FoldedAgentActivity {...props} />;
  }

  // Diff rows break the fold so they stay visible in their original timeline position.
  const items: ReactNode[] = [];
  let foldedCount = 0;
  let pending: UIMessage[] = [];
  const flush = (last: boolean) => {
    // A live turn still needs its status header when the last row is a diff.
    if (!pending.length && !(last && props.isTurnStreaming)) return;
    foldedCount += 1;
    items.push(
      <FoldedAgentActivity
        {...props}
        detailsId={undefined}
        hideHeader={props.expanded !== undefined}
        key={pending[0]?.id ?? "tail-status"}
        messages={pending}
        isTurnStreaming={last && props.isTurnStreaming}
        retryStatus={last ? props.retryStatus : null}
        hasBodyBelow={false}
      />,
    );
    pending = [];
  };
  for (const message of messages) {
    const edits = editsByMessage.get(message.id);
    if (message.fileEdits?.length) {
      const traces = traceLines(message).filter((line) => !isFileEditTraceLine(line));
      if (traces.some((line) => line.trim())) {
        pending.push({ ...message, traces, content: traces.at(-1) ?? "", fileEdits: undefined });
      }
    } else {
      pending.push(message);
    }
    if (edits?.length) {
      flush(false);
      items.push(
        <FileEditGroup
          key={`${message.id}:edits`}
          edits={edits}
          displayMode={displayMode}
          onOpenFilePreview={props.onOpenFilePreview}
        />,
      );
    }
  }
  flush(true);
  const duration = completedActivityDurationMs(messages, props.turnLatencyMs);
  const label = duration > 0 ? t("message.activityWorkedFor", { duration: formatActivityDuration(duration) }) : t("message.activityWorked");
  return (
    <div className={cn("flex w-full flex-col gap-0.5", props.hasBodyBelow && "mb-2")}>
      {props.expanded !== undefined && foldedCount > 0 ? <ThinkingReasoningShell
        active={false} expanded={props.expanded} contextual renderDetails={false}
        contentId={props.detailsId} label={label} collapseLabel={t("message.collapseActivity")}
        onToggle={() => props.onExpandedChange?.(!props.expanded)}>{null}</ThinkingReasoningShell> : null}
      <div id={props.detailsId} className="flex min-w-0 flex-col gap-0.5">{items}</div>
    </div>
  );
}
