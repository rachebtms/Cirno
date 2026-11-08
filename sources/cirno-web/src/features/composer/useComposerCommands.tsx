import {
  clearDraggedSession,
  hasDraggedSession,
  readDraggedSession,
} from "@/lib/session-drag";
import { useCallback, useEffect, useLayoutEffect } from "react";
import {
  SlashPaletteCommand,
  storeSlashRecents,
} from "./commands";
import {
  MentionCandidate,
  SLASH_PALETTE_GAP_PX,
  SLASH_PALETTE_MAX_HEIGHT_PX,
  SLASH_PALETTE_MIN_HEIGHT_PX,
  SLASH_RECENTS_LIMIT,
  SlashPalettePlacement,
  mentionInsertion,
  pauseQueuedPrompt,
} from "./contracts";
import { autosizeTextarea } from "@/ui/fields/textarea";
import type { ComponentInputs } from "./inputs";
import { getVisibleBounds } from "./layout/visible-bounds";
import type { useComposerAttachments } from "./useComposerAttachments";
import type { useComposerQueues } from "./useComposerQueues";
import type { useComposerSelection } from "./useComposerSelection";
import type { useComposerState } from "./useComposerState";

export function useComposerCommands({
  composerQueues,
  composerState,
  composerSelection,
  composerAttachments,
  inputs,
}: {
  composerQueues: ReturnType<typeof useComposerQueues>;
  composerState: ReturnType<typeof useComposerState>;
  composerSelection: ReturnType<typeof useComposerSelection>;
  composerAttachments: ReturnType<typeof useComposerAttachments>;
  inputs: ComponentInputs;
}) {
  const { showAnyPalette, setSlashPaletteLayout, filteredMentionCandidates } =
    composerQueues;
  const {
    formRef,
    textareaRef,
    mentionOverlayRef,
    compactControls,
    readingTextSize,
    customReadingTextSize,
    previousPendingQueueKeyRef,
    setValue,
    setInlineError,
    setSlashMenuDismissed,
    setCliAppMenuDismissed,
    setCursorPosition,
    clear,
    setQueuedPrompt,
    recentSlashCommands,
    setRecentSlashCommands,
    value,
    sessionDragPreview,
    setSessionDragPreview,
    interactionDisabled,
  } = composerState;
  const { filteredSlashCommands, skillQuery } = composerSelection;
  const {
    mentionInput,
    replaceMentionInput,
    cliAppMention,
    insertableSessionMentions,
    rawSelection,
  } = composerAttachments;
  const { pendingQueueKey, onStop, isStreaming } = inputs;
  useLayoutEffect(() => {
    if (!showAnyPalette) return;

    const updateLayout = () => {
      const form = formRef.current;
      if (!form) return;
      const rect = form.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) return;

      const bounds = getVisibleBounds(form);
      const spaceAbove = Math.max(
        0,
        rect.top - bounds.top - SLASH_PALETTE_GAP_PX,
      );
      const spaceBelow = Math.max(
        0,
        bounds.bottom - rect.bottom - SLASH_PALETTE_GAP_PX,
      );
      // A landscape keyboard can leave less height than one input and option.
      // Use the available width instead of clipping an absolute menu in the
      // short viewport's scrollable composer footer.
      const beside =
        rect.width >= 640 && !!form.closest("#root.short-visual-viewport");
      const placement: SlashPalettePlacement = beside
        ? "beside"
        : spaceAbove >= SLASH_PALETTE_MIN_HEIGHT_PX || spaceAbove >= spaceBelow
          ? "above"
          : "below";
      const available = beside
        ? Math.max(0, bounds.bottom - bounds.top)
        : placement === "above"
          ? spaceAbove
          : spaceBelow;
      const maxHeight = Math.min(SLASH_PALETTE_MAX_HEIGHT_PX, available);

      setSlashPaletteLayout((current) =>
        current.placement === placement && current.maxHeight === maxHeight
          ? current
          : { placement, maxHeight },
      );
    };

    updateLayout();
    const viewport = window.visualViewport;
    viewport?.addEventListener("resize", updateLayout);
    viewport?.addEventListener("scroll", updateLayout);
    window.addEventListener("resize", updateLayout);
    document.addEventListener("scroll", updateLayout, true);
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(updateLayout);
    if (formRef.current) observer?.observe(formRef.current);
    return () => {
      observer?.disconnect();
      viewport?.removeEventListener("resize", updateLayout);
      viewport?.removeEventListener("scroll", updateLayout);
      window.removeEventListener("resize", updateLayout);
      document.removeEventListener("scroll", updateLayout, true);
    };
  }, [
    filteredMentionCandidates.length,
    filteredSlashCommands.length,
    showAnyPalette,
  ]);
  const focusTextarea = useCallback(() => {
    requestAnimationFrame(() => textareaRef.current?.focus());
  }, []);
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el || mentionInput.isComposing) return;
    autosizeTextarea(el);
    if (mentionOverlayRef.current)
      mentionOverlayRef.current.scrollTop = el.scrollTop;
  }, [compactControls, mentionInput.isComposing, mentionInput.value]);
  useEffect(() => {
    // The parent projects typography tokens in its layout effect; measure after it.
    const input = textareaRef.current;
    if (input) autosizeTextarea(input);
  }, [readingTextSize, customReadingTextSize]);
  useLayoutEffect(() => {
    if (previousPendingQueueKeyRef.current === pendingQueueKey) return;
    previousPendingQueueKeyRef.current = pendingQueueKey;
    setValue("");
    setInlineError(null);
    setSlashMenuDismissed(false);
    setCliAppMenuDismissed(false);
    setCursorPosition(0);
    clear();
  }, [clear, pendingQueueKey]);
  const handleStop = useCallback(() => {
    setQueuedPrompt((prompt) => (prompt ? pauseQueuedPrompt(prompt) : null));
    onStop?.();
  }, [onStop, setQueuedPrompt]);
  const chooseSlashCommand = useCallback(
    (command: SlashPaletteCommand) => {
      if (command.command === "/stop" && isStreaming && onStop) {
        handleStop();
        setValue("");
        setSlashMenuDismissed(true);
        setCliAppMenuDismissed(false);
        setInlineError(null);
        focusTextarea();
        return;
      }

      const nextRecents = [
        command.command,
        ...recentSlashCommands.filter((item) => item !== command.command),
      ].slice(0, SLASH_RECENTS_LIMIT);
      setRecentSlashCommands(nextRecents);
      storeSlashRecents(nextRecents);

      if (skillQuery !== null) {
        const suffix = value.slice(skillQuery.end);
        const inserted = `${command.command}${suffix.startsWith(" ") ? "" : " "}`;
        const next = `${value.slice(0, skillQuery.start)}${inserted}${suffix}`;
        const nextCursor = skillQuery.start + inserted.length;
        replaceMentionInput(next, nextCursor);
      } else {
        setValue(command.argHint ? `${command.command} ` : command.command);
      }
      setSlashMenuDismissed(true);
      setCliAppMenuDismissed(false);
      setInlineError(null);
      focusTextarea();
    },
    [
      handleStop,
      isStreaming,
      onStop,
      recentSlashCommands,
      replaceMentionInput,
      focusTextarea,
      skillQuery,
      value,
    ],
  );
  const insertMention = useCallback(
    (name: string, start: number, end: number) => {
      const insertion = mentionInsertion(value, name, start, end);
      replaceMentionInput(insertion.value, insertion.cursor);
      setCliAppMenuDismissed(true);
      setSlashMenuDismissed(false);
      setInlineError(null);
      focusTextarea();
    },
    [replaceMentionInput, focusTextarea, value],
  );
  const chooseMentionCandidate = useCallback(
    (candidate: MentionCandidate) => {
      if (!cliAppMention) return;
      insertMention(candidate.name, cliAppMention.start, cliAppMention.end);
    },
    [cliAppMention, insertMention],
  );
  const handleSessionDrop = useCallback(
    (event: React.DragEvent) => {
      if (!hasDraggedSession(event.dataTransfer)) return false;
      event.preventDefault();
      clearDraggedSession();
      const preview = sessionDragPreview;
      setSessionDragPreview(null);
      if (interactionDisabled) return true;
      const sessionKey = readDraggedSession(event.dataTransfer);
      const mention = insertableSessionMentions.find(
        (candidate) =>
          candidate.session_key ===
          (sessionKey ?? preview?.mention.session_key),
      );
      if (!mention) return true;
      const caret = preview?.start ?? rawSelection().start;
      insertMention(mention.name, caret, preview?.end ?? rawSelection().end);
      return true;
    },
    [
      insertableSessionMentions,
      insertMention,
      interactionDisabled,
      rawSelection,
      sessionDragPreview,
    ],
  );
  const previewSessionDrop = useCallback(
    (event: React.DragEvent) => {
      if (!hasDraggedSession(event.dataTransfer)) return false;
      if (interactionDisabled) {
        event.dataTransfer.dropEffect = "none";
        setSessionDragPreview(null);
        return true;
      }
      const sessionKey = readDraggedSession(event.dataTransfer);
      const mention = insertableSessionMentions.find(
        (candidate) => candidate.session_key === sessionKey,
      );
      if (!mention) {
        event.dataTransfer.dropEffect = "none";
        setSessionDragPreview(null);
        return true;
      }
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
      const { start, end } = rawSelection();
      setSessionDragPreview((current) =>
        current?.mention.session_key === mention.session_key &&
        current.start === start &&
        current.end === end
          ? current
          : { mention, start, end },
      );
      return true;
    },
    [insertableSessionMentions, interactionDisabled, rawSelection],
  );
  return {
    focusTextarea,
    handleStop,
    chooseMentionCandidate,
    chooseSlashCommand,
    previewSessionDrop,
    handleSessionDrop,
  };
}
