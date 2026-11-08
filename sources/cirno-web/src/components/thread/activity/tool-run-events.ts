import type { ToolProgressEvent } from "@/lib/contracts/activity";

export function parseToolEventArguments(event: ToolProgressEvent): unknown {
  const fnArgs = (event as { function?: { arguments?: unknown } }).function?.arguments;
  const raw = fnArgs ?? event.arguments;
  if (typeof raw !== "string") return raw ?? {};
  if (!raw.trim()) return {};
  try {
    return JSON.parse(raw);
  } catch {
    return { args: [raw] };
  }
}

export function toolRunStatusFromPhase(phase: unknown): ToolRunStatus {
  if (phase === "error") return "error";
  if (phase === "end") return "done";
  return "running";
}

export function toolProgressError(error: unknown): string | undefined {
  if (typeof error === "string") return error;
  if (error && typeof error === "object") {
    try {
      return JSON.stringify(error);
    } catch {
      return "Tool call failed";
    }
  }
  return undefined;
}

export function toolEventName(event: ToolProgressEvent): string {
  return typeof (event as { function?: { name?: unknown } }).function?.name === "string"
    ? String((event as { function?: { name?: unknown } }).function?.name)
    : typeof event.name === "string"
      ? event.name
      : "";
}

export function titleFromPresetName(name: string): string {
  const productName = PRODUCT_NAME_OVERRIDES[name.toLowerCase()];
  if (productName) return productName;
  return name
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ") || name;
}

export const PRODUCT_NAME_OVERRIDES: Record<string, string> = {
  github: "GitHub",
  gitlab: "GitLab",
  openai: "OpenAI",
};

export type ToolRunStatus = "running" | "done" | "error";
export const TOOL_RUN_STATUS_RANK: Record<ToolRunStatus, number> = { running: 1, done: 2, error: 3 };
