import type { SessionMention } from "@/lib/contracts/messages";
import { isLocalAttachment } from "../../../../packages/client-events/attachments";
import { QUEUED_PROMPTS_STORAGE_PREFIX, type QueuedPrompt, type QueuedPromptImage,
  canAutoSendQueuedPrompt, mergeQueuedPrompt, pauseQueuedPrompt } from "../contracts";
export function queuedPromptsStorageKey(key?: string | null): string | null {
  const clean = key?.trim();
  return clean ? `${QUEUED_PROMPTS_STORAGE_PREFIX}${clean}` : null;
}

export function normalizeQueuedSessionMentions(
  value: unknown,
): SessionMention[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const candidate = item as Partial<SessionMention>;
    const name = candidate.name?.trim().slice(0, 80);
    const sessionKey = candidate.session_key?.trim().slice(0, 512);
    if (
      !name ||
      !sessionKey?.startsWith("websocket:") ||
      !/^[\p{L}\p{N}_-]+$/u.test(name)
    )
      return [];
    return [
      {
        ...(typeof candidate.id === "string" &&
        /^handle_[a-f0-9]{32}$/i.test(candidate.id)
          ? { id: candidate.id }
          : {}),
        name,
        session_key: sessionKey,
        title: candidate.title?.trim().slice(0, 160) ?? "",
      },
    ];
  });
}

export function normalizeQueuedPrompt(
  item: unknown,
  index: number,
): QueuedPrompt | null {
  if (!item || typeof item !== "object") return null;
  const record = item as Partial<QueuedPrompt>;
  if (typeof record.text !== "string") return null;
  const text = record.text.trim();
  const images = Array.isArray(record.images)
    ? record.images.flatMap((image): QueuedPromptImage[] => {
        if (!image || typeof image !== "object") return [];
        const candidate = image as Partial<QueuedPromptImage>;
        if (isLocalAttachment(candidate.local)) {
          return [
            {
              local: candidate.local,
              kind: candidate.local.kind,
              name: candidate.local.name,
            },
          ];
        }
        if (
          typeof candidate.dataUrl !== "string" ||
          !candidate.dataUrl.startsWith("data:")
        ) {
          return [];
        }
        const kind =
          candidate.kind === "file" ||
          candidate.kind === "image" ||
          candidate.kind === "video"
            ? candidate.kind
            : candidate.dataUrl.startsWith("data:image/")
              ? "image"
              : "file";
        return [
          {
            dataUrl: candidate.dataUrl,
            kind,
            ...(typeof candidate.name === "string" && candidate.name.trim()
              ? { name: candidate.name.trim() }
              : {}),
          },
        ];
      })
    : [];
  const quotedContext =
    typeof record.quotedContext === "string" ? record.quotedContext.trim() : "";
  const sessionMentions = normalizeQueuedSessionMentions(
    record.sessionMentions,
  );
  if (!text && images.length === 0) return null;
  const id =
    typeof record.id === "string" && record.id.trim()
      ? record.id
      : `queued-prompt-restored-${index}`;
  const prompt: QueuedPrompt = {
    id,
    text,
    ...(images.length > 0 ? { images } : {}),
    ...(quotedContext ? { quotedContext } : {}),
    ...(sessionMentions.length > 0 ? { sessionMentions } : {}),
    ...(typeof record.autoAfterTurnId === "string" &&
    record.autoAfterTurnId.trim()
      ? { autoAfterTurnId: record.autoAfterTurnId.trim() }
      : {}),
    ...(record.autoPaused === true ? { autoPaused: true } : {}),
    ...(typeof record.autoSendPageId === "string"
      ? { autoSendPageId: record.autoSendPageId }
      : {}),
  };
  return canAutoSendQueuedPrompt(prompt) ? prompt : pauseQueuedPrompt(prompt);
}

export function readQueuedPrompt(storageKey: string): QueuedPrompt | null {
  const raw = window.localStorage.getItem(storageKey);
  const parsed: unknown = raw ? JSON.parse(raw) : [];
  if (!Array.isArray(parsed)) throw new Error("Waiting-message storage must contain an array");
  return parsed
    .map((item, index) => normalizeQueuedPrompt(item, index))
    .filter((item): item is QueuedPrompt => item !== null)
    .reduce<QueuedPrompt | null>((pending, prompt) => pending ? mergeQueuedPrompt(pending, prompt) : prompt, null);
}

export function storeQueuedPrompt(storageKey: string, prompt: QueuedPrompt | null): void {
  if (prompt) window.localStorage.setItem(storageKey, JSON.stringify([prompt]));
  else window.localStorage.removeItem(storageKey);
}
