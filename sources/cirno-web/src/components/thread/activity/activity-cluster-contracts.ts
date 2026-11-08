import type { CliAppInfo } from "@/lib/contracts/apps";
import type { McpPresetInfo } from "@/lib/contracts/mcp";
import type { RetryStatus, UIMessage } from "@/lib/contracts/messages";

export interface AgentActivityClusterProps {
  messages: UIMessage[];
  /** True while the session turn is still running (drives “Working…” copy + header sheen). */
  isTurnStreaming: boolean;
  hasBodyBelow: boolean;
  /** Persisted end-to-end turn latency from the assistant answer, used for history replay. */
  turnLatencyMs?: number;
  /** User turn start timestamp for live activity before the first trace/reasoning row. */
  startedAtMs?: number;
  retryStatus?: RetryStatus | null;
  cliApps?: CliAppInfo[];
  mcpPresets?: McpPresetInfo[];
  traceDetailScope?: string | null;
  onLoadTraceDetails?: (refs: string[]) => void | Promise<void>;
  onOpenFilePreview?: (path: string) => void;
  /** Optional controlled expansion state for a completed inline activity block. */
  defaultCollapsed?: boolean;
  expanded?: boolean;
  onExpandedChange?: (expanded: boolean) => void;
  /** Hide individual segment headers when a shared disclosure owns this cluster. */
  hideHeader?: boolean;
  /** Stable id used by an external disclosure control. */
  detailsId?: string;
}

export interface ActivityCounts {
  reasoningSteps: number;
  toolCalls: number;
  modelSegments: number;
  cliCount: number;
  mcpCount: number;
  fileCount: number;
}
