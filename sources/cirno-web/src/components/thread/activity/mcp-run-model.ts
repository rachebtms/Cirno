import {
  toolActivityDetails
} from "@/components/thread/activity/activity-text";
import type { ToolProgressEvent } from "@/lib/contracts/activity";
import type { UIMessage } from "@/lib/contracts/messages";
import { canonicalToolTrace, formatToolCallTrace } from "@/lib/tool-traces";
import { traceLines } from "./activity-entries";
import { parseToolEventArguments, titleFromPresetName, TOOL_RUN_STATUS_RANK, toolEventName, toolProgressError, ToolRunStatus, toolRunStatusFromPhase } from "./tool-run-events";

export interface McpRunSummary {
  key: string;
  presetName: string;
  displayName: string;
  toolName: string;
  args: unknown;
  status: ToolRunStatus;
  error?: string;
  detailsText?: string;
}

export const MCP_TOOL_NAME_RE = /^mcp_([a-z0-9_-]+?)_(.+)$/i;

export function isMcpRunTraceLine(line: string): boolean {
  return MCP_TOOL_NAME_RE.test(line.trim().split("(", 1)[0] ?? "");
}

export function mcpRunFromToolName(
  toolName: string,
  argsObject: unknown,
  options: { key: string; status: ToolRunStatus; error?: string },
): McpRunSummary | null {
  const match = MCP_TOOL_NAME_RE.exec(toolName);
  if (!match) return null;
  const presetName = match[1].toLowerCase();
  return {
    key: options.key,
    presetName,
    displayName: titleFromPresetName(presetName),
    toolName: match[2],
    args: argsObject,
    status: options.status,
    error: options.error,
  };
}

export function parseMcpRunTrace(line: string, status: ToolRunStatus = "running"): McpRunSummary | null {
  const match = /^([a-z0-9_-]+)\((.*)\)$/i.exec(line.trim());
  if (!match || !MCP_TOOL_NAME_RE.test(match[1])) return null;
  const argsText = match[2].trim();
  let argsObject: unknown = {};
  if (argsText) {
    try {
      argsObject = JSON.parse(argsText);
    } catch {
      argsObject = argsText;
    }
  }
  return mcpRunFromToolName(match[1], argsObject, { key: line, status });
}

export function mcpRunFromEvent(event: ToolProgressEvent): McpRunSummary | null {
  const name = toolEventName(event);
  if (!MCP_TOOL_NAME_RE.test(name)) return null;
  const argsObject = parseToolEventArguments(event);
  const key = event.call_id ? `call:${event.call_id}` : `${name}:${JSON.stringify(argsObject)}`;
  const run = mcpRunFromToolName(name, argsObject, {
    key,
    status: toolRunStatusFromPhase(event.phase),
    error: toolProgressError(event.error),
  });
  return run && { ...run, detailsText: toolActivityDetails(formatToolCallTrace(event) ?? name, event.result, toolProgressError(event.error)) };
}

export function mcpRunMapByTraceLine(message: UIMessage): Map<string, McpRunSummary> {
  const runsByLine = new Map<string, McpRunSummary>();
  for (const event of message.toolEvents ?? []) {
    const run = mcpRunFromEvent(event);
    if (!run) continue;
    const line = formatToolCallTrace(event);
    if (!line) continue;
    const key = canonicalToolTrace(line);
    runsByLine.set(key, mergeMcpRun(runsByLine.get(key), run));
  }
  return runsByLine;
}

export function mergeMcpRun(existing: McpRunSummary | undefined, incoming: McpRunSummary): McpRunSummary {
  if (!existing) return incoming;
  return TOOL_RUN_STATUS_RANK[incoming.status] >= TOOL_RUN_STATUS_RANK[existing.status]
    ? { ...existing, ...incoming }
    : existing;
}

export function collectMcpRuns(messages: UIMessage[]): McpRunSummary[] {
  const runsByKey = new Map<string, McpRunSummary>();
  for (const message of messages) {
    if (message.kind !== "trace") continue;
    let hasStructuredMcpRun = false;
    for (const event of message.toolEvents ?? []) {
      const run = mcpRunFromEvent(event);
      if (!run) continue;
      hasStructuredMcpRun = true;
      runsByKey.set(run.key, mergeMcpRun(runsByKey.get(run.key), run));
    }
    if (hasStructuredMcpRun) continue;
    for (const line of traceLines(message)) {
      const run = parseMcpRunTrace(line);
      if (!run || runsByKey.has(run.key)) continue;
      runsByKey.set(run.key, run);
    }
  }
  return [...runsByKey.values()];
}
