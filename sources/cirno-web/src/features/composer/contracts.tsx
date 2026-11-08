import {
  ActivityIcon,
  ArchiveIcon,
  CompactIcon,
  DreamIcon,
  DreamLogIcon,
  EditIcon,
  GoalIcon,
  HelpIcon,
  HistoryIcon,
  MemoryIcon,
  ModelsIcon,
  NewChatIcon,
  PromptTemplateIcon,
  RestartIcon,
  RestoreMemoryIcon,
  RestrictedAccessIcon,
  ResumeIcon,
  SkillsIcon,
  StatusIcon,
  StopIcon,
  ToolRunIcon,
  TriggerIcon,
} from "@/components/icons/product-icons";
import {
  type ComposerContextUsage,
  type ComposerRoundUsage,
} from "@/components/thread/ComposerUsagePopover";
import { type ModelPresetOption } from "@/features/model-selection/contracts";
import { type RestoredReadyImage } from "@/hooks/useAttachedImages";
import type { SendAttachment, SendOptions } from "@/hooks/useCirnoStream";
import type { ComposerDraftStore } from "@/lib/composer-draft";
import { isCapabilityMentionStart } from "@/lib/composer-mention-text";
import type { GoalStateWsPayload } from "@/lib/contracts/activity";
import type { CliAppInfo } from "@/lib/contracts/apps";
import type { WebUIIngressLimits } from "@/lib/contracts/bootstrap";
import type { SlashCommand } from "@/lib/contracts/commands";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { McpPresetInfo } from "@/lib/contracts/mcp";
import type { SessionMention } from "@/lib/contracts/messages";
import type { SkillSummary } from "@/lib/contracts/skills";
import type { ProjectDirectory, WorkspaceDirectoriesPayload, WorkspaceScopePayload, WorkspacesPayload } from "@/lib/contracts/workspaces";
import { Code2, Eraser, Ghost, type LucideIcon } from "lucide-react";
import { type Ref } from "react";
import { type LocalAttachment } from "../../../packages/client-events/attachments";

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MiB`;
}

export function utf8Bytes(value: string): number {
  return new TextEncoder().encode(value).byteLength;
}

export interface ThreadComposerProps {
  active?: boolean;
  onSend: (
    content: string,
    images?: SendAttachment[],
    options?: SendOptions,
  ) => boolean | void | Promise<boolean | void>;
  disabled?: boolean;
  placeholder?: string;
  inputAriaLabel?: string;
  compactWhenIdle?: boolean;
  isStreaming?: boolean;
  activeTurnId?: string | null;
  completedTurnIds?: readonly string[];
  modelLabel?: string | null;
  modelDetail?: string | null;
  modelPreset?: string | null;
  modelPresets?: ModelPresetOption[];
  onModelPresetChange?: (name: string) => void;
  modelProvider?: string | null;
  modelProviderLabel?: string | null;
  modelNeedsSetup?: boolean;
  onModelBadgeClick?: () => void;
  onManageModels?: () => void;
  showContextUsage?: boolean;
  contextUsage?: ComposerContextUsage | null;
  contextUsageError?: string;
  recentRoundUsage?: readonly ComposerRoundUsage[];
  variant?: "thread" | "hero";
  slashCommands?: SlashCommand[];
  onMentionSearch?: () => void;
  cliApps?: CliAppInfo[];
  mcpPresets?: McpPresetInfo[];
  sessions?: ChatSummary[];
  skills?: SkillSummary[];
  onStop?: () => void;
  onContinue?: () => Promise<void>;
  surfaceRef?: Ref<HTMLDivElement>;
  onInspectAttachment?: (path: string) => Promise<LocalAttachment>;
  /** Sustained objective for this chat (WebSocket ``goal_state``). */
  goalState?: GoalStateWsPayload;
  workspaceScope?: WorkspaceScopePayload | null;
  workspaceControlsHidden?: boolean;
  workspacePickerLayoutAnchor?: HTMLElement | null;
  workspaceDefaultScope?: WorkspaceScopePayload | null;
  workspaceControls?: WorkspacesPayload["controls"] | null;
  workspaceScopeDisabled?: boolean;
  workspaceProjectLocked?: boolean;
  workspaceError?: string | null;
  onFavoriteWorkspaceProject?: (
    path: string,
    pinned: boolean,
  ) => Promise<ProjectDirectory[]>;
  onResolveWorkspaceProject?: (path: string) => Promise<ProjectDirectory>;
  onLoadWorkspaceProjects?: () => Promise<WorkspacesPayload>;
  onBrowseWorkspaceDirectories?: (
    path: string,
    query: string,
    showHidden: boolean,
  ) => Promise<WorkspaceDirectoriesPayload>;
  onWorkspaceScopeChange?: (scope: WorkspaceScopePayload) => void;
  pendingQueueKey?: string | null;
  draftKey?: string;
  draftStore?: ComposerDraftStore;
  persistDraft?: boolean;
  ingressLimits?: WebUIIngressLimits | null;
  quotedContext?: string | null;
  focusRequest?: number;
  onQuotedContextChange?: (text: string | null) => void;
}

export const COMMAND_ICONS: Record<string, LucideIcon> = {
  activity: ActivityIcon,
  code: Code2,
  play: ResumeIcon,
  eraser: Eraser,
  archive: ArchiveIcon,
  "book-open": SkillsIcon,
  brain: MemoryIcon,
  "circle-help": HelpIcon,
  history: HistoryIcon,
  "rotate-cw": RestartIcon,
  shield: RestrictedAccessIcon,
  sparkles: DreamIcon,
  square: StopIcon,
  "square-pen": EditIcon,
  "undo-2": RestoreMemoryIcon,
  zap: TriggerIcon,
  "file-text": PromptTemplateIcon,
  wrench: ToolRunIcon,
};

export const BUILTIN_COMMAND_ICONS: Record<string, LucideIcon> = {
  "/temporary": Ghost,
  "/ptc": Code2,
  "/access": RestrictedAccessIcon,
  "/resume": ResumeIcon,
  "/clear": Eraser,
  "/new": NewChatIcon,
  "/compact": CompactIcon,
  "/stop": StopIcon,
  "/restart": RestartIcon,
  "/status": StatusIcon,
  "/model": ModelsIcon,
  "/history": HistoryIcon,
  "/goal": GoalIcon,
  "/trigger": TriggerIcon,
  "/dream": DreamIcon,
  "/dream-log": DreamLogIcon,
  "/dream-restore": RestoreMemoryIcon,
  "/dream-prompt": PromptTemplateIcon,
  "/evaluator-prompt": PromptTemplateIcon,
  "/skill": SkillsIcon,
  "/help": HelpIcon,
};

export const SLASH_PALETTE_GAP_PX = 8;

export const SLASH_PALETTE_MAX_HEIGHT_PX = 288;

export const SLASH_PALETTE_MIN_HEIGHT_PX = 144;

export const SLASH_PALETTE_CHROME_PX = 12;

export const SLASH_RECENTS_STORAGE_KEY = "cirno.webui.slashCommandRecents";

export const SLASH_RECENTS_LIMIT = 5;

export const QUEUED_PROMPTS_STORAGE_PREFIX =
  "cirno.webui.composerQueuedGuidance.v1:";

export const EMPTY_COMPLETED_TURN_IDS: readonly string[] = [];

export const SESSION_MENTIONS_LIMIT = 8;

export type SlashPalettePlacement = "above" | "below" | "beside";

export interface SlashPaletteLayout {
  placement: SlashPalettePlacement;
  maxHeight: number;
}

export interface QueuedPrompt {
  id: string;
  text: string;
  images?: QueuedPromptImage[];
  quotedContext?: string;
  sessionMentions?: SessionMention[];
  autoAfterTurnId?: string;
  autoPaused?: boolean;
  autoSendPageId?: string;
}

export const queuedPromptAuthorization: { pageId: string | undefined } = {
  pageId: undefined,
};

export function getQueuedPromptPageId(): string {
  return (queuedPromptAuthorization.pageId ??= crypto.randomUUID());
}

export function canAutoSendQueuedPrompt(prompt: QueuedPrompt): boolean {
  return (
    !prompt.autoPaused && prompt.autoSendPageId === getQueuedPromptPageId()
  );
}

export function pauseQueuedPrompt(prompt: QueuedPrompt): QueuedPrompt {
  return {
    ...prompt,
    autoAfterTurnId: undefined,
    autoSendPageId: undefined,
    autoPaused: true,
  };
}

export function mergeQueuedPrompt(
  first: QueuedPrompt,
  next: QueuedPrompt,
): QueuedPrompt {
  const prompts = [first, next];
  const mentions = new Map<string, SessionMention>();
  for (const prompt of prompts) {
    for (const mention of prompt.sessionMentions ?? []) {
      if (!mentions.has(mention.session_key))
        mentions.set(mention.session_key, mention);
    }
  }
  return {
    id: first.id,
    text: prompts
      .map((prompt) => prompt.text)
      .filter(Boolean)
      .join("\n"),
    images: prompts.flatMap((prompt) => prompt.images ?? []),
    quotedContext: [
      ...new Set(prompts.map((prompt) => prompt.quotedContext).filter(Boolean)),
    ].join("\n\n"),
    sessionMentions: [...mentions.values()],
    autoAfterTurnId: first.autoAfterTurnId,
    autoPaused: prompts.some((prompt) => prompt.autoPaused),
    autoSendPageId: first.autoSendPageId,
  };
}

export function queuedUploadBytes(image: QueuedPromptImage): number {
  if (image.local) return 0;
  const dataUrl = image.dataUrl ?? "";
  const base64 = dataUrl.slice(dataUrl.indexOf(",") + 1);
  const padding = base64.endsWith("==") ? 2 : base64.endsWith("=") ? 1 : 0;
  return Math.floor((base64.length * 3) / 4) - padding;
}

export type QueuedPromptImage = RestoredReadyImage;

export interface CliAppMentionQuery {
  query: string;
  start: number;
  end: number;
}

export type MentionCandidate = {
  name: string;
  displayName: string;
} & (
    | { kind: "session"; mention: SessionMention }
    | {
      kind: "cli" | "mcp";
      brandColor: string | null;
      logoUrl: string | null;
      initials: string;
    }
  );

export interface MentionInsertion {
  value: string;
  cursor: number;
  tokenStart: number;
  tokenEnd: number;
}

export function mentionInsertion(
  value: string,
  name: string,
  start: number,
  end: number,
): MentionInsertion {
  const from = Math.min(Math.max(start, 0), value.length);
  const to = Math.min(Math.max(end, from), value.length);
  const prefix = value.slice(0, from);
  const suffix = value.slice(to);
  const leadingSpace =
    prefix && !isCapabilityMentionStart(value, from) ? " " : "";
  const trailingSpace = /^\s/.test(suffix) ? "" : " ";
  const tokenStart = prefix.length + leadingSpace.length;
  const tokenEnd = tokenStart + name.length + 1;
  return {
    value: `${prefix}${leadingSpace}@${name}${trailingSpace}${suffix}`,
    cursor: tokenEnd + trailingSpace.length,
    tokenStart,
    tokenEnd,
  };
}
