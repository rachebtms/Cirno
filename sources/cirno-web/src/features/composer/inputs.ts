import {
  type ComposerContextUsage,
  type ComposerRoundUsage,
} from "@/components/thread/ComposerUsagePopover";
import { type ModelPresetOption } from "@/features/model-selection/contracts";
import type { SendAttachment, SendOptions } from "@/hooks/useCirnoStream";
import type { ComposerDraftStore } from "@/lib/composer-draft";
import type { GoalStateWsPayload } from "@/lib/contracts/activity";
import type { CliAppInfo } from "@/lib/contracts/apps";
import type { WebUIIngressLimits } from "@/lib/contracts/bootstrap";
import type { SlashCommand } from "@/lib/contracts/commands";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { McpPresetInfo } from "@/lib/contracts/mcp";
import type { SkillSummary } from "@/lib/contracts/skills";
import type { ProjectDirectory, WorkspaceDirectoriesPayload, WorkspaceScopePayload, WorkspacesPayload } from "@/lib/contracts/workspaces";
import { type Ref } from "react";
import { type LocalAttachment } from "../../../packages/client-events/attachments";
export interface ComponentInputs {
  active: boolean;
  onSend: (
    content: string,
    images?: SendAttachment[],
    options?: SendOptions,
  ) => boolean | void | Promise<boolean | void>;
  disabled: boolean | undefined;
  placeholder: string | undefined;
  inputAriaLabel: string | undefined;
  compactWhenIdle: boolean;
  isStreaming: boolean;
  activeTurnId: string | null;
  completedTurnIds: readonly string[];
  modelLabel: string | null;
  modelDetail: string | null;
  modelPreset: string | null;
  modelPresets: ModelPresetOption[];
  onModelPresetChange: ((name: string) => void) | undefined;
  modelProvider: string | null;
  modelProviderLabel: string | null;
  modelNeedsSetup: boolean;
  onModelBadgeClick: (() => void) | undefined;
  onManageModels: (() => void) | undefined;
  showContextUsage: boolean;
  contextUsage: ComposerContextUsage | null;
  contextUsageError: string | undefined;
  recentRoundUsage: readonly ComposerRoundUsage[];
  variant: "thread" | "hero";
  slashCommands: SlashCommand[];
  onMentionSearch: (() => void) | undefined;
  cliApps: CliAppInfo[];
  mcpPresets: McpPresetInfo[];
  sessions: ChatSummary[];
  skills: SkillSummary[];
  onStop: (() => void) | undefined;
  onContinue: (() => Promise<void>) | undefined;
  surfaceRef: Ref<HTMLDivElement> | undefined;
  onInspectAttachment: ((path: string) => Promise<LocalAttachment>) | undefined;
  goalState: GoalStateWsPayload | undefined;
  workspaceScope: WorkspaceScopePayload | null;
  workspaceControlsHidden: boolean;
  workspacePickerLayoutAnchor: HTMLElement | null | undefined;
  workspaceDefaultScope: WorkspaceScopePayload | null;
  workspaceControls: {
    can_change_project: boolean;
    can_browse_directories?: boolean;
    can_resolve_project?: boolean;
    can_manage_favorites?: boolean;
  } | null;
  workspaceScopeDisabled: boolean;
  workspaceProjectLocked: boolean;
  workspaceError: string | null;
  onLoadWorkspaceProjects: (() => Promise<WorkspacesPayload>) | undefined;
  onResolveWorkspaceProject:
  | ((path: string) => Promise<ProjectDirectory>)
  | undefined;
  onFavoriteWorkspaceProject:
  | ((path: string, pinned: boolean) => Promise<ProjectDirectory[]>)
  | undefined;
  onBrowseWorkspaceDirectories:
  | ((
    path: string,
    query: string,
    showHidden: boolean,
  ) => Promise<WorkspaceDirectoriesPayload>)
  | undefined;
  onWorkspaceScopeChange: ((scope: WorkspaceScopePayload) => void) | undefined;
  pendingQueueKey: string | null;
  draftKey: string | undefined;
  draftStore: ComposerDraftStore | undefined;
  persistDraft: boolean;
  ingressLimits: WebUIIngressLimits | null;
  quotedContext: string | null;
  focusRequest: number;
  onQuotedContextChange: ((text: string | null) => void) | undefined;
}
