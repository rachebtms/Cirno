import { type FileEditSummary } from "@/components/thread/activity/FileEditRow";
import {
  isReasoningOnlyAssistant
} from "@/lib/activity-timeline";
import type { UIMessage } from "@/lib/contracts/messages";
import { ActivityCounts } from "./activity-cluster-contracts";
import { traceLines } from "./activity-entries";
import { CliRunSummary, isCliRunTraceLine } from "./cli-run-model";
import { McpRunSummary, isMcpRunTraceLine } from "./mcp-run-model";

export function countActivity(
  messages: UIMessage[],
  fileEdits: FileEditSummary[],
  cliRuns: CliRunSummary[],
  mcpRuns: McpRunSummary[],
): ActivityCounts {
  let reasoningSteps = 0;
  let toolCalls = 0;
  let modelSegments = 0;
  const cliCount = cliRuns.length;
  const mcpCount = mcpRuns.length;
  for (const m of messages) {
    if (m.activityKind === "model") {
      modelSegments += 1;
      continue;
    }
    if (isReasoningOnlyAssistant(m)) {
      reasoningSteps += 1;
      continue;
    }
    if (m.kind === "trace") {
      if (m.traceDetail) {
        toolCalls += m.traceDetail.traceCount;
        continue;
      }
      const lines = traceLines(m);
      for (const line of lines) {
        if (!isCliRunTraceLine(line) && !isMcpRunTraceLine(line)) {
          toolCalls += 1;
        }
      }
    }
  }
  return {
    reasoningSteps,
    toolCalls,
    modelSegments,
    cliCount,
    mcpCount,
    fileCount: fileEdits.length,
  };
}

export function activityDurationMs(
  messages: UIMessage[],
  active: boolean,
  now: number,
  completedLatencyMs?: number,
  activeStartedAtMs?: number,
): number {
  if (!active && Number.isFinite(completedLatencyMs) && completedLatencyMs! >= 0) {
    return Math.round(completedLatencyMs!);
  }
  const timestamps = messages
    .map((message) => message.createdAt)
    .filter((value) => Number.isFinite(value));
  if (!timestamps.length) {
    return active
      && typeof activeStartedAtMs === "number"
      && Number.isFinite(activeStartedAtMs)
      ? Math.max(0, now - activeStartedAtMs)
      : 0;
  }
  const first = active && Number.isFinite(activeStartedAtMs)
    ? activeStartedAtMs!
    : Math.min(...timestamps);
  const last = active && first > 1_000_000_000_000
    ? now
    : Math.max(...timestamps);
  return Math.max(0, last - first);
}

export function completedActivityDurationMs(
  messages: UIMessage[],
  completedLatencyMs?: number,
): number {
  return activityDurationMs(messages, false, 0, completedLatencyMs);
}

export function formatActivityDuration(ms: number): string {
  const seconds = ms > 0 && ms < 1000 ? 1 : Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
}
