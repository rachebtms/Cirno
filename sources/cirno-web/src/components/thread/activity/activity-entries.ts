import type { UIMessage } from "@/lib/contracts/messages";
import { implementationToolName } from "@/lib/tool-names";

export function traceLines(message: UIMessage): string[] {
  if (message.traces?.length) return message.traces;
  return message.content.trim() ? [message.content] : [];
}

export function messageHasOnlyFileActivity(message: UIMessage): boolean {
  if (message.kind !== "trace" || !message.fileEdits?.length) return false;
  return traceLines(message).every((line) => !line.trim() || isFileEditTraceLine(line));
}

export function isFileEditTraceLine(line: string): boolean {
  return ["write_file", "edit_file", "apply_patch"].includes(implementationToolName(line.trim().split("(", 1)[0]));
}
