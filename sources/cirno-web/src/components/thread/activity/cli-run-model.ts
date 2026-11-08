import {
  toolActivityDetails
} from "@/components/thread/activity/activity-text";
import type { ToolProgressEvent } from "@/lib/contracts/activity";
import type { UIMessage } from "@/lib/contracts/messages";
import { implementationToolName } from "@/lib/tool-names";
import { canonicalToolTrace, formatToolCallTrace } from "@/lib/tool-traces";
import { traceLines } from "./activity-entries";
import { parseToolEventArguments, TOOL_RUN_STATUS_RANK, toolEventName, toolProgressError, ToolRunStatus, toolRunStatusFromPhase } from "./tool-run-events";

export interface CliRunSummary {
  key: string;
  name: string;
  args: string[];
  json: boolean;
  workingDir?: string;
  status: ToolRunStatus;
  error?: string;
  detailsText?: string;
}

export const CLI_RUN_TOOL_NAMES = new Set(["run_cli_app", "cli_anything_run"]);

export function isCliRunTraceLine(line: string): boolean {
  return CLI_RUN_TOOL_NAMES.has(implementationToolName(line.trim().split("(", 1)[0]));
}

export function parseCliRunTrace(line: string, status: ToolRunStatus = "running"): CliRunSummary | null {
  const match = /^([a-zA-Z0-9_.-]+)\((.*)\)$/.exec(line.trim());
  if (!match || !isCliRunTraceLine(line)) return null;
  const argsText = match[2].trim();
  let argsObject: unknown = {};
  if (argsText) {
    try {
      argsObject = JSON.parse(argsText);
    } catch {
      return {
        key: line,
        name: "cli",
        args: [argsText],
        json: false,
        status,
      };
    }
  }
  return cliRunFromArguments(argsObject, { key: line, status });
}

export function cliRunFromArguments(
  argsObject: unknown,
  options: { key: string; status: ToolRunStatus; error?: string },
): CliRunSummary {
  if (!argsObject || typeof argsObject !== "object" || Array.isArray(argsObject)) {
    return {
      key: options.key,
      name: "cli",
      args: [],
      json: false,
      status: options.status,
      error: options.error,
    };
  }
  const record = argsObject as Record<string, unknown>;
  const appName = typeof record.name === "string" && record.name.trim()
    ? record.name.trim()
    : "cli";
  const rawArgs = Array.isArray(record.args) ? record.args : [];
  const cliArgs = rawArgs.filter((item): item is string => typeof item === "string");
  return {
    key: options.key,
    name: appName,
    args: cliArgs,
    json: record.json === true || record.json === "true",
    workingDir: typeof record.working_dir === "string" ? record.working_dir : undefined,
    status: options.status,
    error: options.error,
  };
}

export function cliRunFromEvent(event: ToolProgressEvent): CliRunSummary | null {
  const name = implementationToolName(toolEventName(event));
  if (!CLI_RUN_TOOL_NAMES.has(name)) return null;
  const argsObject = parseToolEventArguments(event);
  const key = event.call_id ? `call:${event.call_id}` : `${name}:${JSON.stringify(argsObject)}`;
  return {
    ...cliRunFromArguments(argsObject, {
      key,
      status: toolRunStatusFromPhase(event.phase),
      error: toolProgressError(event.error),
    }), detailsText: toolActivityDetails(formatToolCallTrace(event) ?? name, event.result, toolProgressError(event.error))
  };
}

export function cliRunMapByTraceLine(message: UIMessage): Map<string, CliRunSummary> {
  const runsByLine = new Map<string, CliRunSummary>();
  for (const event of message.toolEvents ?? []) {
    const run = cliRunFromEvent(event);
    if (!run) continue;
    const line = formatToolCallTrace(event);
    if (!line) continue;
    const key = canonicalToolTrace(line);
    runsByLine.set(key, mergeCliRun(runsByLine.get(key), run));
  }
  return runsByLine;
}

export function mergeCliRun(existing: CliRunSummary | undefined, incoming: CliRunSummary): CliRunSummary {
  if (!existing) return incoming;
  return TOOL_RUN_STATUS_RANK[incoming.status] >= TOOL_RUN_STATUS_RANK[existing.status]
    ? { ...existing, ...incoming }
    : existing;
}

export function collectCliRuns(messages: UIMessage[]): CliRunSummary[] {
  const runsByKey = new Map<string, CliRunSummary>();
  for (const message of messages) {
    if (message.kind !== "trace") continue;
    let hasStructuredCliRun = false;
    for (const event of message.toolEvents ?? []) {
      const run = cliRunFromEvent(event);
      if (!run) continue;
      hasStructuredCliRun = true;
      runsByKey.set(run.key, mergeCliRun(runsByKey.get(run.key), run));
    }
    if (hasStructuredCliRun) continue;
    for (const line of traceLines(message)) {
      const run = parseCliRunTrace(line);
      if (!run || runsByKey.has(run.key)) continue;
      runsByKey.set(run.key, run);
    }
  }
  return [...runsByKey.values()];
}

export function displayCliArg(arg: string): string {
  return /\s/.test(arg) ? JSON.stringify(arg) : arg;
}

export function formatCliArgs(run: CliRunSummary): string {
  const args = [...(run.json ? ["--json"] : []), ...run.args].map(displayCliArg);
  return args.join(" ");
}
