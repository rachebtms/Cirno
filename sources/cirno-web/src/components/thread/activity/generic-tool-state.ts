import {
  type GenericToolStatus
} from "@/components/thread/activity/generic-tool-model";
import type { UIMessage } from "@/lib/contracts/messages";
import { canonicalToolTrace, formatToolCallTrace } from "@/lib/tool-traces";
import { TOOL_RUN_STATUS_RANK, toolProgressError } from "./tool-run-events";

export interface GenericToolState {
  status: GenericToolStatus;
  error?: string;
  result?: unknown;
}

export function genericToolStateByTraceLine(message: UIMessage): Map<string, GenericToolState> {
  const map = new Map<string, GenericToolState>();
  for (const event of message.toolEvents ?? []) {
    const line = formatToolCallTrace(event);
    if (!line) continue;
    const key = canonicalToolTrace(line);
    const status: GenericToolStatus = event.phase === "error"
      ? "error"
      : event.phase === "end"
        ? "done"
        : "running";
    const next = {
      status,
      error: status === "error" ? toolProgressError(event.error) : undefined,
      result: event.result,
    };
    const previous = map.get(key);
    if (!previous || TOOL_RUN_STATUS_RANK[next.status] >= TOOL_RUN_STATUS_RANK[previous.status]) {
      map.set(key, next);
    }
  }
  return map;
}
