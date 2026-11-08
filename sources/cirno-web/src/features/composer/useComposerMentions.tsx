import {
  MAX_TOTAL_ATTACHMENT_BYTES,
  MAX_VIDEOS_PER_MESSAGE,
  type RestoredReadyImage,
} from "@/hooks/useAttachedImages";
import type { SendOptions } from "@/hooks/useCirnoStream";
import { onComposerDraftAccepted } from "@/lib/composer-draft";
import { clearDraggedSession } from "@/lib/session-drag";
import { formatQuotedUserMessage } from "@/lib/user-message-quote";
import { useCallback, useEffect } from "react";
import {
  canAutoSendQueuedPrompt,
  getQueuedPromptPageId,
  mergeQueuedPrompt,
  pauseQueuedPrompt,
  QueuedPrompt,
  queuedUploadBytes,
  SESSION_MENTIONS_LIMIT,
  utf8Bytes,
} from "./contracts";
import type { ComponentInputs } from "./inputs";
import {
  queuedImagesToSendImages,
  readyImagesToQueuedImages,
} from "./queue/payload";
import type { useComposerAttachments } from "./useComposerAttachments";
import type { useComposerCommands } from "./useComposerCommands";
import type { useComposerSelection } from "./useComposerSelection";
import type { useComposerState } from "./useComposerState";

export function useComposerMentions({
  composerState,
  composerCommands,
  inputs,
  composerSelection,
  composerAttachments,
}: {
  composerState: ReturnType<typeof useComposerState>;
  composerCommands: ReturnType<typeof useComposerCommands>;
  inputs: ComponentInputs;
  composerSelection: ReturnType<typeof useComposerSelection>;
  composerAttachments: ReturnType<typeof useComposerAttachments>;
}) {
  const {
    sessionDragPreview,
    setSessionDragPreview,
    setValue,
    setInlineError,
    setSlashMenuDismissed,
    setCliAppMenuDismissed,
    setCursorPosition,
    clear,
    maxTextBytes,
    textTooLargeMessage,
    formatRejection,
    maxAttachments,
    maxVideoBytes,
    maxFileBytes,
    formatUploadTooLarge,
    t,
    queuedPromptCounterRef,
    value,
    queuedPrompt,
    setQueuedPrompt,
    textareaRef,
    setBoundSessionMentions,
    restoreReadyImages,
    interactionDisabled,
    queuedPromptStore,
    previousQueueRunRef,
    queuedPromptStorageKey,
    images,
  } = composerState;
  const { focusTextarea } = composerCommands;
  const {
    draftStore,
    draftKey,
    onQuotedContextChange,
    ingressLimits,
    activeTurnId,
    isStreaming,
    onSend,
    pendingQueueKey,
    completedTurnIds,
    onContinue,
  } = inputs;
  const {
    readyImages,
    normalizedQuotedContext,
    canQueueGuidance,
    hasComposerContent,
    requiresModelSetup,
  } = composerSelection;
  const { activeSessionMentions, replaceMentionInput } = composerAttachments;
  useEffect(() => {
    if (!sessionDragPreview) return;
    const clearPreview = () => {
      clearDraggedSession();
      setSessionDragPreview(null);
    };
    document.addEventListener("dragend", clearPreview);
    return () => document.removeEventListener("dragend", clearPreview);
  }, [sessionDragPreview]);
  const clearComposerText = useCallback(
    (restoreFocus = true) => {
      setValue("");
      setInlineError(null);
      setSlashMenuDismissed(false);
      setCliAppMenuDismissed(false);
      setCursorPosition(0);
      if (restoreFocus) focusTextarea();
    },
    [focusTextarea],
  );
  useEffect(() => {
    if (!draftStore || !draftKey) return;
    return onComposerDraftAccepted(draftStore, (key) => {
      if (key !== draftKey) return;
      clear();
      clearComposerText(false);
      onQuotedContextChange?.(null);
    });
  }, [clear, clearComposerText, draftKey, draftStore, onQuotedContextChange]);
  const queuedPromptError = useCallback(
    (prompt: QueuedPrompt): string | null => {
      if (
        utf8Bytes(formatQuotedUserMessage(prompt.text, prompt.quotedContext)) >
        maxTextBytes
      ) {
        return textTooLargeMessage();
      }
      const attachments = prompt.images ?? [];
      const videos = attachments.filter((item) => item.kind === "video").length;
      if (videos > MAX_VIDEOS_PER_MESSAGE)
        return formatRejection("too_many_videos");
      if (attachments.length - videos > maxAttachments)
        return formatRejection("too_many_attachments");
      const oversized = attachments.find(
        (item) =>
          queuedUploadBytes(item) >
          (item.kind === "video" ? maxVideoBytes : maxFileBytes),
      );
      if (oversized) {
        return formatUploadTooLarge(
          queuedUploadBytes(oversized),
          oversized.kind === "video" ? maxVideoBytes : maxFileBytes,
        );
      }
      const total = attachments.reduce(
        (sum, item) =>
          sum + (item.kind === "video" ? 0 : queuedUploadBytes(item)),
        0,
      );
      if (
        total >
        (ingressLimits?.attachments.max_total_bytes ??
          MAX_TOTAL_ATTACHMENT_BYTES)
      ) {
        return formatRejection("total_too_large");
      }
      if ((prompt.sessionMentions?.length ?? 0) > SESSION_MENTIONS_LIMIT) {
        return t("thread.composer.queued.tooManyMentions", {
          max: SESSION_MENTIONS_LIMIT,
        });
      }
      return null;
    },
    [
      formatRejection,
      formatUploadTooLarge,
      ingressLimits,
      maxAttachments,
      maxFileBytes,
      maxVideoBytes,
      maxTextBytes,
      t,
      textTooLargeMessage,
    ],
  );
  const collectGuidancePrompt = useCallback((): QueuedPrompt => {
    queuedPromptCounterRef.current += 1;
    const prompt: QueuedPrompt = {
      id: `queued-prompt-${Date.now()}-${queuedPromptCounterRef.current}`,
      text: value.trim(),
      autoSendPageId: getQueuedPromptPageId(),
      images: readyImagesToQueuedImages(readyImages),
      ...(activeTurnId ? { autoAfterTurnId: activeTurnId } : {}),
      ...(normalizedQuotedContext
        ? { quotedContext: normalizedQuotedContext }
        : {}),
      sessionMentions: activeSessionMentions,
    };
    return queuedPrompt ? mergeQueuedPrompt(queuedPrompt, prompt) : prompt;
  }, [
    activeSessionMentions,
    activeTurnId,
    normalizedQuotedContext,
    queuedPrompt,
    readyImages,
    value,
  ]);
  const queueGuidancePrompt = useCallback(() => {
    if (!canQueueGuidance) return;
    const prompt = collectGuidancePrompt();
    const error = queuedPromptError(prompt);
    if (error) {
      setInlineError(error);
      return;
    }
    setQueuedPrompt(prompt);
    clear();
    clearComposerText();
    onQuotedContextChange?.(null);
  }, [
    canQueueGuidance,
    clear,
    clearComposerText,
    collectGuidancePrompt,
    onQuotedContextChange,
    queuedPromptError,
    setQueuedPrompt,
  ]);
  const removeQueuedPrompt = useCallback(() => {
    setQueuedPrompt(null);
    requestAnimationFrame(() => textareaRef.current?.focus());
  }, [setQueuedPrompt]);
  const editQueuedPrompt = useCallback(
    (pending: QueuedPrompt) => {
      const prompt =
        hasComposerContent || normalizedQuotedContext
          ? collectGuidancePrompt()
          : pending;
      setQueuedPrompt(null);
      replaceMentionInput(prompt.text, prompt.text.length);
      setBoundSessionMentions(prompt.sessionMentions ?? []);
      setInlineError(null);
      setSlashMenuDismissed(false);
      setCliAppMenuDismissed(false);
      onQuotedContextChange?.(prompt.quotedContext ?? null);
      if (prompt.images?.length) {
        restoreReadyImages(prompt.images as RestoredReadyImage[]);
      } else {
        clear();
      }
      focusTextarea();
    },
    [
      clear,
      collectGuidancePrompt,
      hasComposerContent,
      normalizedQuotedContext,
      onQuotedContextChange,
      replaceMentionInput,
      focusTextarea,
      restoreReadyImages,
      setQueuedPrompt,
    ],
  );
  const sendQueuedPrompt = useCallback(
    (prompt: QueuedPrompt, extraOptions?: SendOptions) => {
      if (interactionDisabled) return;
      const error = queuedPromptError(prompt);
      if (error) {
        setQueuedPrompt(pauseQueuedPrompt(prompt));
        queuedPromptStore.reportError(error);
        return;
      }
      const text = prompt.text.trim();
      const queuedImages = queuedImagesToSendImages(prompt.images);
      const options: SendOptions | undefined =
        extraOptions ||
        prompt.quotedContext ||
        prompt.sessionMentions?.length ||
        isStreaming
          ? {
              ...extraOptions,
              ...(prompt.quotedContext
                ? { quotedContext: prompt.quotedContext }
                : {}),
              ...(prompt.sessionMentions?.length
                ? { sessionMentions: prompt.sessionMentions }
                : {}),
              ...(isStreaming ? { continueActiveTurn: true } : {}),
            }
          : undefined;
      setInlineError(null);
      queuedPromptStore.send(prompt, () =>
        options
          ? onSend(text, queuedImages, options)
          : queuedImages?.length
            ? onSend(text, queuedImages)
            : onSend(text),
      );
      requestAnimationFrame(() => textareaRef.current?.focus());
    },
    [
      interactionDisabled,
      isStreaming,
      onSend,
      queuedPromptStore,
      queuedPromptError,
      setQueuedPrompt,
    ],
  );
  useEffect(() => {
    const previous = previousQueueRunRef.current;
    previousQueueRunRef.current = { key: pendingQueueKey, isStreaming };
    // Switching to an idle session is not completion of the previous session's run.
    if (previous.key !== pendingQueueKey) return;
    if (
      isStreaming ||
      interactionDisabled ||
      !queuedPrompt ||
      !canAutoSendQueuedPrompt(queuedPrompt)
    )
      return;
    const waitingTurnCompleted =
      queuedPromptStorageKey !== null &&
      queuedPrompt.autoAfterTurnId !== undefined
        ? completedTurnIds.includes(queuedPrompt.autoAfterTurnId)
        : previous.isStreaming;
    if (!waitingTurnCompleted) return;
    sendQueuedPrompt(queuedPrompt);
  }, [
    completedTurnIds,
    interactionDisabled,
    sendQueuedPrompt,
    isStreaming,
    pendingQueueKey,
    queuedPrompt,
    queuedPromptStorageKey,
  ]);
  const showContinueButton =
    !!onContinue &&
    !isStreaming &&
    !hasComposerContent &&
    images.length === 0 &&
    !normalizedQuotedContext &&
    !requiresModelSetup;
  return {
    showContinueButton,
    clearComposerText,
    collectGuidancePrompt,
    queuedPromptError,
    sendQueuedPrompt,
    queueGuidancePrompt,
    removeQueuedPrompt,
    editQueuedPrompt,
  };
}
