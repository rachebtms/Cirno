import { useDraftPersistence } from "./useDraftPersistence";
import { EMPTY_COMPLETED_TURN_IDS, ThreadComposerProps } from "./contracts";
import { ComposerView } from "./view/ComposerView";
import { useComposerActions } from "./useComposerActions";
import { useComposerAttachments } from "./useComposerAttachments";
import { useComposerCommands } from "./useComposerCommands";
import { useComposerDelivery } from "./useComposerDelivery";
import { useComposerKeyboard } from "./useComposerKeyboard";
import { useComposerMentions } from "./useComposerMentions";
import { useComposerQueues } from "./useComposerQueues";
import { useComposerSelection } from "./useComposerSelection";
import { useComposerState } from "./useComposerState";
export function ThreadComposer({
  active = true,
  onSend,
  disabled,
  placeholder,
  inputAriaLabel,
  compactWhenIdle = false,
  isStreaming = false,
  activeTurnId = null,
  completedTurnIds = EMPTY_COMPLETED_TURN_IDS,
  modelLabel = null,
  modelDetail = null,
  modelPreset = null,
  modelPresets = [],
  onModelPresetChange,
  modelProvider = null,
  modelProviderLabel = null,
  modelNeedsSetup = false,
  onModelBadgeClick,
  onManageModels,
  showContextUsage = false,
  contextUsage = null,
  contextUsageError,
  recentRoundUsage = [],
  variant = "thread",
  slashCommands = [],
  onMentionSearch,
  cliApps = [],
  mcpPresets = [],
  sessions = [],
  skills = [],
  onStop,
  onContinue,
  surfaceRef,
  onInspectAttachment,
  goalState,
  workspaceScope = null,
  workspaceControlsHidden = false,
  workspacePickerLayoutAnchor,
  workspaceDefaultScope = null,
  workspaceControls = null,
  workspaceScopeDisabled = false,
  workspaceProjectLocked = false,
  workspaceError = null,
  onLoadWorkspaceProjects,
  onResolveWorkspaceProject,
  onFavoriteWorkspaceProject,
  onBrowseWorkspaceDirectories,
  onWorkspaceScopeChange,
  pendingQueueKey = null,
  draftKey,
  draftStore,
  persistDraft = false,
  ingressLimits = null,
  quotedContext = null,
  focusRequest = 0,
  onQuotedContextChange,
}: ThreadComposerProps) {
  const inputs = {
    active,
    onSend,
    disabled,
    placeholder,
    inputAriaLabel,
    compactWhenIdle,
    isStreaming,
    activeTurnId,
    completedTurnIds,
    modelLabel,
    modelDetail,
    modelPreset,
    modelPresets,
    onModelPresetChange,
    modelProvider,
    modelProviderLabel,
    modelNeedsSetup,
    onModelBadgeClick,
    onManageModels,
    showContextUsage,
    contextUsage,
    contextUsageError,
    recentRoundUsage,
    variant,
    slashCommands,
    onMentionSearch,
    cliApps,
    mcpPresets,
    sessions,
    skills,
    onStop,
    onContinue,
    surfaceRef,
    onInspectAttachment,
    goalState,
    workspaceScope,
    workspaceControlsHidden,
    workspacePickerLayoutAnchor,
    workspaceDefaultScope,
    workspaceControls,
    workspaceScopeDisabled,
    workspaceProjectLocked,
    workspaceError,
    onLoadWorkspaceProjects,
    onResolveWorkspaceProject,
    onFavoriteWorkspaceProject,
    onBrowseWorkspaceDirectories,
    onWorkspaceScopeChange,
    pendingQueueKey,
    draftKey,
    draftStore,
    persistDraft,
    ingressLimits,
    quotedContext,
    focusRequest,
    onQuotedContextChange,
  };
  const composerState = useComposerState({ inputs });
  const composerSelection = useComposerSelection({ inputs, composerState });
  const composerAttachments = useComposerAttachments({
    composerState,
    composerSelection,
    inputs,
  });
  const draftPersistence = useDraftPersistence(inputs, composerState, composerAttachments);
  const composerQueues = useComposerQueues({
    composerAttachments,
    inputs,
    composerSelection,
    composerState,
  });
  const composerCommands = useComposerCommands({
    composerQueues,
    composerState,
    composerSelection,
    composerAttachments,
    inputs,
  });
  const composerMentions = useComposerMentions({
    composerState,
    composerCommands,
    inputs,
    composerSelection,
    composerAttachments,
  });
  const composerDelivery = useComposerDelivery({
    composerMentions,
    inputs,
    composerState,
    composerSelection,
    composerQueues,
    composerAttachments,
    composerCommands,
  });
  const composerKeyboard = useComposerKeyboard({
    composerAttachments,
    composerQueues,
    composerState,
    composerCommands,
    composerSelection,
    composerMentions,
    composerDelivery,
    inputs,
  });
  const composerActions = useComposerActions({
    inputs,
    composerState,
    composerQueues,
  });
  return (
    <ComposerView
      draftPersistence={draftPersistence}
      composerState={composerState}
      composerActions={composerActions}
      inputs={inputs}
      composerDelivery={composerDelivery}
      composerCommands={composerCommands}
      composerSelection={composerSelection}
      composerQueues={composerQueues}
      composerKeyboard={composerKeyboard}
      composerMentions={composerMentions}
      composerAttachments={composerAttachments}
    />
  );
}
