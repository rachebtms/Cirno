import { coalesceActivityMessages } from "@/components/thread/activity/activity-message-model";
import { FileEditGroup } from "@/components/thread/activity/FileEditRow";
import { ThinkingReasoningShell } from "@/components/thread/activity/ThinkingReasoningShell";
import { usePageVisibility } from "@/hooks/usePageVisibility";
import { usePreferences } from "@/hooks/usePreferences";
import { useThreadVisibility } from "@/hooks/useThreadVisibility";
import type { CliAppInfo } from "@/lib/contracts/apps";
import type { McpPresetInfo } from "@/lib/contracts/mcp";
import { cn } from "@/lib/utils";
import {
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";
import { useTranslation } from "react-i18next";
import { AgentActivityClusterProps } from "./activity-cluster-contracts";
import { messageHasOnlyFileActivity } from "./activity-entries";
import { activityDurationMs, countActivity, formatActivityDuration } from "./activity-summary";
import { ActivityMessageTimeline } from "./ActivityMessageTimeline";
import { collectCliRuns } from "./cli-run-model";
import { summarizeFileEditsByMessage } from "./file-edit-summary";
import { collectMcpRuns } from "./mcp-run-model";
import { useDeferredActivityDetails } from "./useDeferredActivityDetails";

export function FoldedAgentActivity({
  messages,
  isTurnStreaming,
  hasBodyBelow,
  turnLatencyMs,
  startedAtMs,
  elapsedBeforeActiveMs = 0,
  retryStatus = null,
  cliApps = EMPTY_CLI_APPS,
  mcpPresets = EMPTY_MCP_PRESETS,
  traceDetailScope = null,
  onLoadTraceDetails,
  onOpenFilePreview,
  afterInputMessage,
  defaultCollapsed = false,
  expanded,
  onExpandedChange,
  hideHeader = false,
  detailsId,
}: AgentActivityClusterProps) {
  const { t } = useTranslation();
  const { activityMode, fileEditDisplayMode } = usePreferences();
  const pageVisible = usePageVisibility();
  const threadVisible = useThreadVisibility();
  const activityMessages = useMemo(() => coalesceActivityMessages(messages), [messages]);
  const fileEditsByMessage = useMemo(
    () => summarizeFileEditsByMessage(activityMessages, isTurnStreaming),
    [activityMessages, isTurnStreaming],
  );
  const fileEdits = useMemo(
    () => [...fileEditsByMessage.values()].flat(),
    [fileEditsByMessage],
  );
  const cliRuns = useMemo(() => collectCliRuns(activityMessages), [activityMessages]);
  const mcpRuns = useMemo(() => collectMcpRuns(activityMessages), [activityMessages]);
  const cliAppsByName = useMemo(
    () => new Map(cliApps.map((app) => [app.name.toLowerCase(), app])),
    [cliApps],
  );
  const mcpPresetsByName = useMemo(
    () => new Map(mcpPresets.map((preset) => [preset.name.toLowerCase(), preset])),
    [mcpPresets],
  );
  const {
    reasoningSteps,
    toolCalls,
    modelSegments,
    cliCount,
    mcpCount,
    fileCount,
  } = countActivity(activityMessages, fileEdits, cliRuns, mcpRuns);

  const [userToggledOuter, setUserToggledOuter] = useState(false);
  const [outerOpenLocal, setOuterOpenLocal] = useState(false);
  const [completionHoldOpen, setCompletionHoldOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const wasTurnStreamingRef = useRef(isTurnStreaming);
  const wasTurnStreaming = wasTurnStreamingRef.current;
  /** Auto follows execution; expanded keeps details open unless manually collapsed. */
  const outerExpanded = expanded ?? (
    userToggledOuter
      ? outerOpenLocal
      : !defaultCollapsed && (activityMode === "expanded" || isTurnStreaming || completionHoldOpen || (wasTurnStreaming && !isTurnStreaming))
  );
  useEffect(() => {
    setUserToggledOuter(false);
  }, [activityMode]);
  const { failed: traceDetailLoadFailed, retry: requestTraceDetails } = useDeferredActivityDetails({
    messages, scope: traceDetailScope, expanded: outerExpanded, load: onLoadTraceDetails,
  });

  const hasVisibleActivity = reasoningSteps > 0 || toolCalls > 0 || modelSegments > 0 || cliCount > 0 || mcpCount > 0 || fileCount > 0
    || activityMessages.some(message => !!message.inputOrigin);
  const hasOnlyFileActivity = fileCount > 0 && activityMessages.every(messageHasOnlyFileActivity);
  const durationMs = (isTurnStreaming ? elapsedBeforeActiveMs : 0) + activityDurationMs(
    activityMessages,
    isTurnStreaming,
    now,
    turnLatencyMs,
    startedAtMs,
  );
  const activityDuration = formatActivityDuration(durationMs);
  const isCompletedDisclosure = !isTurnStreaming && expanded !== undefined;
  const retryError = retryStatus?.error_kind === "connection"
    ? t("message.retryConnection", { defaultValue: "Connection failed" })
    : retryStatus?.error_kind === "timeout"
      ? t("message.retryTimeout", { defaultValue: "Model timed out" })
      : retryStatus?.error_kind === "rate_limit"
        ? t("message.retryRateLimit", { defaultValue: "Rate limited" })
        : retryStatus?.error_kind === "server"
          ? t("message.retryServer", { defaultValue: "Model unavailable" })
          : t("message.retryUnknown", { defaultValue: "Model request failed" });
  const retrySeconds = retryStatus?.next_retry_at === undefined
    ? 0
    : Math.max(0, Math.ceil(retryStatus.next_retry_at - now / 1000));
  const activityLabel = retryStatus?.state === "exhausted"
    ? t("message.retryExhausted", {
      error: retryError,
      defaultValue: "{{error}} Ending turn",
    })
    : retryStatus?.state === "waiting"
      ? retrySeconds > 0
        ? t("message.retryWaiting", {
          error: retryError,
          seconds: retrySeconds,
          defaultValue: "{{error}} Retrying in {{seconds}}s",
        })
        : t("message.retrying", {
          error: retryError,
          defaultValue: "{{error}} Retrying",
        })
      : isTurnStreaming
        ? t("message.activityWorkingFor", {
          duration: activityDuration,
          defaultValue: "Working for {{duration}}",
        })
        : durationMs <= 0
          ? t("message.activityWorked", { defaultValue: "Worked" })
          : t("message.activityWorkedFor", {
            duration: activityDuration,
            defaultValue: "Worked for {{duration}}",
          });

  const toggleOuter = () => {
    if (expanded !== undefined) {
      onExpandedChange?.(!expanded);
      return;
    }
    const nextOpen = userToggledOuter ? !outerOpenLocal : !outerExpanded;
    setUserToggledOuter(true);
    setOuterOpenLocal(nextOpen);
  };

  useEffect(() => {
    if (!isTurnStreaming || !pageVisible || !threadVisible) return undefined;
    setNow(Date.now());
    const interval = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(interval);
  }, [isTurnStreaming, pageVisible, threadVisible]);

  useEffect(() => {
    const wasStreaming = wasTurnStreamingRef.current;
    wasTurnStreamingRef.current = isTurnStreaming;
    if (isTurnStreaming) {
      setCompletionHoldOpen(false);
      return undefined;
    }
    if (!wasStreaming || userToggledOuter) return undefined;
    setCompletionHoldOpen(true);
    const timeout = window.setTimeout(() => setCompletionHoldOpen(false), 300);
    return () => window.clearTimeout(timeout);
  }, [isTurnStreaming, userToggledOuter]);

  if (!hasVisibleActivity && !isTurnStreaming) return null;

  if (hasOnlyFileActivity && expanded === undefined) {
    return (
      <div className={cn("w-full", hasBodyBelow && "mb-2")}>
        <FileEditGroup
          edits={fileEdits}
          displayMode={fileEditDisplayMode}
          onOpenFilePreview={onOpenFilePreview}
        />
      </div>
    );
  }

  return (
    <div className={cn("w-full", hasBodyBelow && expanded !== false && "mb-2")}>
      <ThinkingReasoningShell
        active={isTurnStreaming}
        expanded={outerExpanded}
        contextual={isCompletedDisclosure}
        showHeader={!hideHeader}
        collapseLabel={t("message.collapseActivity")}
        contentId={detailsId}
        label={activityLabel}
        hasDetails={hasVisibleActivity}
        onToggle={toggleOuter}
      >
        {traceDetailLoadFailed ? (
          <div role="alert" className="flex items-center gap-2 py-1 text-[12px] text-destructive">
            <span>{t("message.traceDetailsLoadFailed", { defaultValue: "Full activity details could not be loaded." })}</span>
            <button
              type="button"
              className="shrink-0 rounded-sm font-medium underline underline-offset-2 hover:no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => void requestTraceDetails()}
            >
              {t("message.retryTraceDetails", { defaultValue: "Retry" })}
            </button>
          </div>
        ) : null}
        <ActivityMessageTimeline
          messages={activityMessages}
          afterInputMessage={afterInputMessage}
          active={isTurnStreaming}
          cliAppsByName={cliAppsByName}
          mcpPresetsByName={mcpPresetsByName}
          fileEditsByMessage={fileEditsByMessage}
          fileEditDisplayMode={fileEditDisplayMode}
          onOpenFilePreview={onOpenFilePreview}
        />
      </ThinkingReasoningShell>
    </div>
  );
}

export const EMPTY_CLI_APPS: CliAppInfo[] = [];

export const EMPTY_MCP_PRESETS: McpPresetInfo[] = [];
