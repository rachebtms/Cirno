import type { SessionMention } from "@/lib/contracts/messages";
import type { LocalAttachment } from "../../../packages/client-events/attachments";

/** Ordered attachments retain browser Files in memory and persist local references. */
export interface ComposerDraft {
  text: string;
  attachments: Array<File | LocalAttachment>;
  sessionMentions: SessionMention[];
  quotedContext: string | null;
}

export interface DraftStorageIssue { action: "read" | "save" | "remove"; detail: string }
