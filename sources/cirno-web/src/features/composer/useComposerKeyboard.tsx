import { type ComposerActionState } from "@/components/thread/ComposerActionIcon";
import {
  WorkspaceAccessMenu,
  WorkspaceProjectPicker,
} from "@/components/thread/WorkspaceControls";
import {
  useCallback,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";

import type { ComponentInputs } from "./inputs";
import type { useComposerAttachments } from "./useComposerAttachments";
import type { useComposerCommands } from "./useComposerCommands";
import type { useComposerDelivery } from "./useComposerDelivery";
import type { useComposerMentions } from "./useComposerMentions";
import type { useComposerQueues } from "./useComposerQueues";
import type { useComposerSelection } from "./useComposerSelection";
import type { useComposerState } from "./useComposerState";

export function useComposerKeyboard({
  composerAttachments,
  composerQueues,
  composerState,
  composerCommands,
  composerSelection,
  composerMentions,
  composerDelivery,
  inputs,
}: {
  composerAttachments: ReturnType<typeof useComposerAttachments>;
  composerQueues: ReturnType<typeof useComposerQueues>;
  composerState: ReturnType<typeof useComposerState>;
  composerCommands: ReturnType<typeof useComposerCommands>;
  composerSelection: ReturnType<typeof useComposerSelection>;
  composerMentions: ReturnType<typeof useComposerMentions>;
  composerDelivery: ReturnType<typeof useComposerDelivery>;
  inputs: ComponentInputs;
}) {
  const { mentionInput } = composerAttachments;
  const { showCliAppMenu, filteredMentionCandidates } = composerQueues;
  const {
    setSelectedCliAppIndex,
    selectedCliAppIndex,
    setCliAppMenuDismissed,
    setSelectedCommandIndex,
    selectedCommandIndex,
    setSlashMenuDismissed,
    hasCoarsePointer,
    queuedPrompt,
    value,
    images,
    addFiles,
    remove,
    setInlineError,
    chipRefs,
    textareaRef,
    interactionDisabled,
    full,
    sendPending,
    showProjectPicker,
    formRef,
  } = composerState;
  const { chooseMentionCandidate, chooseSlashCommand } = composerCommands;
  const {
    showSlashMenu,
    filteredSlashCommands,
    canQueueGuidance,
    canSend,
    requiresModelSetup,
  } = composerSelection;
  const { queueGuidancePrompt, sendQueuedPrompt, showContinueButton } =
    composerMentions;
  const { submit } = composerDelivery;
  const {
    isStreaming,
    onStop,
    workspaceScope,
    workspaceControlsHidden,
    workspaceScopeDisabled,
    onWorkspaceScopeChange,
    workspacePickerLayoutAnchor,
    workspaceProjectLocked,
    workspaceDefaultScope,
    workspaceControls,
    workspaceError,
    onFavoriteWorkspaceProject,
    onResolveWorkspaceProject,
    onLoadWorkspaceProjects,
    onBrowseWorkspaceDirectories,
  } = inputs;
  const onKeyDown = (e: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    mentionInput.onKeyDown(e);
    if (
      e.defaultPrevented ||
      e.nativeEvent.isComposing ||
      mentionInput.isComposing
    )
      return;
    if (showCliAppMenu) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedCliAppIndex(
          (idx) => (idx + 1) % filteredMentionCandidates.length,
        );
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedCliAppIndex(
          (idx) =>
            (idx - 1 + filteredMentionCandidates.length) %
            filteredMentionCandidates.length,
        );
        return;
      }
      if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
        e.preventDefault();
        chooseMentionCandidate(filteredMentionCandidates[selectedCliAppIndex]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setCliAppMenuDismissed(true);
        return;
      }
    }
    if (showSlashMenu) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedCommandIndex(
          (idx) => (idx + 1) % filteredSlashCommands.length,
        );
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedCommandIndex(
          (idx) =>
            (idx - 1 + filteredSlashCommands.length) %
            filteredSlashCommands.length,
        );
        return;
      }
      if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
        e.preventDefault();
        chooseSlashCommand(filteredSlashCommands[selectedCommandIndex]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setSlashMenuDismissed(true);
        return;
      }
    }
    // Touch keyboards: a plain Enter inserts a newline; sending stays on the
    // send button. The select-on-Enter menu branches above take precedence.
    if (
      e.key === "Enter" &&
      !e.shiftKey &&
      !e.altKey &&
      !e.ctrlKey &&
      !e.metaKey &&
      !e.nativeEvent.isComposing &&
      hasCoarsePointer
    ) {
      return;
    }
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (canQueueGuidance) {
        if (!e.repeat) queueGuidancePrompt();
        return;
      }
      // Empty Enter explicitly sends the visible pending message, including restored drafts.
      if (
        queuedPrompt &&
        value.length === 0 &&
        images.length === 0 &&
        !e.altKey &&
        !e.ctrlKey &&
        !e.metaKey
      ) {
        if (!e.repeat) {
          sendQueuedPrompt(queuedPrompt);
        }
        return;
      }
      submit();
    }
  };
  const onFilePick: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    addFiles(files);
  };
  const removeChip = useCallback(
    (id: string) => {
      const { nextFocusId } = remove(id);
      setInlineError(null);
      requestAnimationFrame(() => {
        const el = nextFocusId ? chipRefs.current.get(nextFocusId) : null;
        if (el) {
          el.focus();
        } else {
          textareaRef.current?.focus();
        }
      });
    },
    [remove],
  );
  const onChipKey = useCallback(
    (id: string) => (e: ReactKeyboardEvent<HTMLButtonElement>) => {
      if (
        e.key === "Delete" ||
        e.key === "Backspace" ||
        e.key === "Enter" ||
        e.key === " "
      ) {
        e.preventDefault();
        removeChip(id);
      }
    },
    [removeChip],
  );
  const attachButtonDisabled = interactionDisabled || full;
  const showStopButton = isStreaming && !!onStop && !canSend;
  const actionState: ComposerActionState = showContinueButton
    ? sendPending
      ? "busy"
      : "continue"
    : showStopButton
      ? "stop"
      : requiresModelSetup
        ? "setup"
        : canSend || !isStreaming
          ? "send"
          : "busy";
  const accessControl =
    workspaceScope && !workspaceControlsHidden ? (
      <WorkspaceAccessMenu
        scope={workspaceScope}
        disabled={interactionDisabled || workspaceScopeDisabled}
        onChange={onWorkspaceScopeChange}
        hintBoundaryRef={formRef}
      />
    ) : null;
  const workspaceControl = showProjectPicker ? (
    <WorkspaceProjectPicker
      layoutAnchor={workspacePickerLayoutAnchor}
      disabled={
        interactionDisabled || workspaceScopeDisabled || workspaceProjectLocked
      }
      scope={workspaceScope}
      defaultScope={workspaceDefaultScope}
      controls={workspaceControls}
      error={workspaceError}
      onFavoriteProject={onFavoriteWorkspaceProject}
      onResolveProject={onResolveWorkspaceProject}
      onLoadProjects={onLoadWorkspaceProjects}
      onBrowseDirectories={onBrowseWorkspaceDirectories}
      onChange={onWorkspaceScopeChange}
    />
  ) : null;
  return {
    removeChip,
    onChipKey,
    onKeyDown,
    onFilePick,
    attachButtonDisabled,
    accessControl,
    showStopButton,
    actionState,
    workspaceControl,
  };
}
