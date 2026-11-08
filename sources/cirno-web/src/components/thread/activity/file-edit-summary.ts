import { type FileEditSummary } from "@/components/thread/activity/FileEditRow";
import type { UIFileEdit } from "@/lib/contracts/activity";
import type { UIMessage } from "@/lib/contracts/messages";

export function fileEditCallKey(edit: UIFileEdit): string {
  if (edit.call_id && edit.path) return `${edit.call_id}|${edit.tool}|${edit.path}`;
  if (edit.call_id) return `${edit.call_id}|${edit.tool}`;
  return `${edit.tool}|${edit.path}`;
}

export function latestFileEditEvents(edits: UIFileEdit[]): UIFileEdit[] {
  const order: string[] = [];
  const byKey = new Map<string, UIFileEdit>();
  for (const edit of edits) {
    const key = fileEditCallKey(edit);
    if (!byKey.has(key)) order.push(key);
    byKey.set(key, edit);
  }
  return order.map((key) => byKey.get(key)).filter(Boolean) as UIFileEdit[];
}

/** Keep each edit at the point where its call first appeared. Later lifecycle
 * events update that row in place instead of moving completed edits to the end. */
export function summarizeFileEditsByMessage(
  messages: UIMessage[],
  active: boolean,
): Map<string, FileEditSummary[]> {
  const messageByEdit = new Map<string, string>();
  const edits: UIFileEdit[] = [];
  for (const message of messages) {
    for (const edit of message.fileEdits ?? []) {
      const key = fileEditCallKey(edit);
      if (!messageByEdit.has(key)) messageByEdit.set(key, message.id);
      edits.push(edit);
    }
  }

  const grouped = new Map<string, FileEditSummary[]>();
  for (const edit of summarizeFileEdits(edits, active)) {
    const messageId = messageByEdit.get(edit.key);
    if (!messageId) continue;
    const group = grouped.get(messageId) ?? [];
    group.push(edit);
    grouped.set(messageId, group);
  }
  return grouped;
}

export function summarizeFileEdits(edits: UIFileEdit[], active: boolean): FileEditSummary[] {
  return latestFileEditEvents(edits).flatMap((edit) => {
    const editing = active && edit.status === "editing";
    const failed = edit.status === "error";
    if (!edit.path && edit.pending && !editing) return [];
    if (!edit.path && !editing && !failed) return [];

    const status: UIFileEdit["status"] = editing
      ? "editing"
      : failed
        ? "error"
        : "done";
    const binary = !!edit.binary;
    return [{
      key: fileEditCallKey(edit),
      path: edit.path || "",
      absolute_path: edit.absolute_path,
      added: binary ? 0 : edit.added,
      deleted: binary ? 0 : edit.deleted,
      approximate: active && !!edit.approximate,
      binary,
      status,
      operation: edit.operation,
      pending: !!edit.pending && !edit.path,
      error: edit.error,
      diff: edit.diff,
    }];
  });
}
