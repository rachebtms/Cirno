import type { SessionMention } from "@/lib/contracts/messages";
import { isRecord } from "../record";
import { isLocalAttachment } from "../../../packages/client-events/attachments";
import type { ComposerDraft } from "./contracts";
export const STORAGE_PREFIX = "cirno.composer-draft.v1.";
export function readDraft(raw: string): ComposerDraft | undefined {
  const value: unknown = JSON.parse(raw);
  if (
    !isRecord(value) ||
    typeof value.text !== "string" ||
    (value.quotedContext !== null && typeof value.quotedContext !== "string") ||
    !Array.isArray(value.sessionMentions)
  )
    throw new Error("Saved draft has an invalid format");
  const sessionMentions = value.sessionMentions.flatMap(
    (item: unknown): SessionMention[] => {
      if (
        !isRecord(item) ||
        typeof item.name !== "string" ||
        !/^[\p{L}\p{N}_-]{1,80}$/u.test(item.name) ||
        typeof item.session_key !== "string" ||
        !item.session_key.startsWith("websocket:") ||
        item.session_key.length > 512 ||
        typeof item.title !== "string"
      )
        return [];
      return [
        {
          name: item.name,
          session_key: item.session_key,
          title: item.title.slice(0, 160),
          ...(typeof item.id === "string" &&
          /^handle_[a-f0-9]{32}$/i.test(item.id)
            ? { id: item.id }
            : {}),
        },
      ];
    },
  );
  const rawAttachments = Array.isArray(value.attachments)
    ? value.attachments
    : value.localAttachments;
  const attachments = Array.isArray(rawAttachments)
    ? rawAttachments.filter(isLocalAttachment)
    : [];
  return {
    text: value.text,
    quotedContext: value.quotedContext,
    sessionMentions,
    attachments,
  };
}


export function saveDraft(key: string, draft: ComposerDraft): void {
  if (!draft.text && !draft.quotedContext && !draft.attachments.some(isLocalAttachment)) {
    localStorage.removeItem(STORAGE_PREFIX + key);
    return;
  }
  localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify({ ...draft,
    attachments: draft.attachments.filter(isLocalAttachment) }));
}
export function clearStoredComposerDrafts(): void {
  const keys: string[] = [];
  for (let index = 0; index < localStorage.length; index++) {
    const key = localStorage.key(index);
    if (key?.startsWith(STORAGE_PREFIX)) keys.push(key);
  }
  const errors: unknown[] = [];
  for (const key of keys) {
    try { localStorage.removeItem(key); } catch (error) { errors.push(error); }
  }
  if (errors.length) throw new AggregateError(errors, errors.map(error => error instanceof Error ? error.message : String(error)).join("; "));
}
