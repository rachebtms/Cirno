export type TraceEvent = {
  id: number; kind: string; created_ms: number; summary: string; status: string;
  session_key: string; turn_id: string | null; bytes?: number; origin?: string | null;
};
export type RecordingInfo = { id: string; epoch: string; running: boolean; reason: string | null; count: number; created_ms: number };
export type TracePage = RecordingInfo & { events: TraceEvent[]; before: number | null; sources: string[] };
export type TraceDetail = {
  event?: unknown; messages?: { role?: string; content?: unknown }[];
  offset?: number; total?: number; tools?: unknown; response?: unknown; status?: string;
};
export const eventGroup = (kind: string) => {
  if (kind === "system_input") return "system";
  if (kind === "request") return "request";
  if (kind === "input") return "input";
  if (kind.startsWith("reasoning")) return "reasoning";
  if (kind.startsWith("answer")) return "answer";
  if (kind === "tool_activity") return "tool";
  if (kind === "compaction") return "compaction";
  if (kind === "file_activity") return "file";
  return "lifecycle";
};
export const EVENT_GROUPS = ["input", "answer", "reasoning", "tool", "compaction", "request", "file", "lifecycle", "system"] as const;
