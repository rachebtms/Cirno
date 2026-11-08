import { cliAppMentionPayload, mcpPresetMentionPayload } from "./capability-mentions";
import type { SendOptions } from "@/hooks/useCirnoStream";
import { acceptComposerDraft } from "@/lib/composer-draft";
import {
  isSideChannelLifecycle,
  slashCommandLifecycle,
} from "@/lib/slash-command";
import { formatQuotedUserMessage } from "@/lib/user-message-quote";
import { useCallback } from "react";
import { utf8Bytes } from "./contracts";
import type { ComponentInputs } from "./inputs";
import {
  queuedImagesToSendImages,
  readyImagesToQueuedImages,
} from "./queue/payload";
import type { useComposerAttachments } from "./useComposerAttachments";
import type { useComposerCommands } from "./useComposerCommands";
import type { useComposerMentions } from "./useComposerMentions";
import type { useComposerQueues } from "./useComposerQueues";
import type { useComposerSelection } from "./useComposerSelection";
import type { useComposerState } from "./useComposerState";

export function useComposerDelivery({
  composerMentions,
  inputs,
  composerState,
  composerSelection,
  composerQueues,
  composerAttachments,
  composerCommands,
}: {
  composerMentions: ReturnType<typeof useComposerMentions>;
  inputs: ComponentInputs;
  composerState: ReturnType<typeof useComposerState>;
  composerSelection: ReturnType<typeof useComposerSelection>;
  composerQueues: ReturnType<typeof useComposerQueues>;
  composerAttachments: ReturnType<typeof useComposerAttachments>;
  composerCommands: ReturnType<typeof useComposerCommands>;
}) {
  const {
    showContinueButton,
    clearComposerText,
    collectGuidancePrompt,
    queuedPromptError,
    sendQueuedPrompt,
  } = composerMentions;
  const {
    onContinue,
    slashCommands,
    isStreaming,
    onStop,
    onQuotedContextChange,
    draftKey,
    draftStore,
    onSend,
  } = inputs;
  const {
    interactionDisabled,
    setSendPending,
    setInlineError,
    t,
    setModelSetupAttentionRequest,
    images,
    value,
    maxTextBytes,
    textTooLargeMessage,
    clear,
    queuedPrompt,
    hasTouchPrimaryPointer,
    textareaRef,
    setQueuedPrompt,
  } = composerState;
  const {
    requiresModelSetup,
    hasComposerContent,
    canSend,
    isUserShell,
    normalizedQuotedContext,
    readyImages,
  } = composerSelection;
  const { activeCliMentionApps, activeMcpPresetMentions } = composerQueues;
  const { activeSessionMentions } = composerAttachments;
  const { handleStop } = composerCommands;
  const submit = useCallback(() => {
    if (showContinueButton && onContinue && !interactionDisabled) {
      setSendPending(true);
      setInlineError(null);
      void onContinue()
        .catch((error: unknown) => {
          setInlineError(
            error instanceof Error ? error.message : t("recovery.actionFailed"),
          );
        })
        .finally(() => setSendPending(false));
      return;
    }
    if (requiresModelSetup) {
      if (hasComposerContent) {
        setModelSetupAttentionRequest((request) => request + 1);
      }
      return;
    }
    if (!canSend) return;
    if (isUserShell && (images.length > 0 || normalizedQuotedContext)) {
      setInlineError(t("thread.composer.shell.removeContext"));
      return;
    }
    const trimmed = value.trim();
    const content = trimmed;
    if (
      utf8Bytes(formatQuotedUserMessage(content, normalizedQuotedContext)) >
      maxTextBytes
    ) {
      setInlineError(textTooLargeMessage());
      return;
    }
    // Keep self-contained local previews across drafts and optimistic bubbles.
    // The client decodes these to HTTP binary; WS messages contain only refs.
    const payload = queuedImagesToSendImages(
      readyImagesToQueuedImages(readyImages),
    );
    const attachedCliApps = activeCliMentionApps.map(cliAppMentionPayload);
    const attachedMcpPresets = activeMcpPresetMentions.map(mcpPresetMentionPayload);
    const options: SendOptions | undefined =
      !isUserShell &&
      (attachedCliApps.length > 0 ||
        attachedMcpPresets.length > 0 ||
        activeSessionMentions.length > 0 ||
        normalizedQuotedContext)
        ? {
            ...(attachedCliApps.length > 0 ? { cliApps: attachedCliApps } : {}),
            ...(attachedMcpPresets.length > 0
              ? { mcpPresets: attachedMcpPresets }
              : {}),
            ...(activeSessionMentions.length > 0
              ? { sessionMentions: activeSessionMentions }
              : {}),
            ...(normalizedQuotedContext
              ? { quotedContext: normalizedQuotedContext }
              : {}),
          }
        : undefined;
    const hasPlainTextCommandPayload =
      payload === undefined &&
      attachedCliApps.length === 0 &&
      attachedMcpPresets.length === 0 &&
      activeSessionMentions.length === 0;
    const slashLifecycle = hasPlainTextCommandPayload
      ? slashCommandLifecycle(content, slashCommands)
      : null;
    if (slashLifecycle === "stop_active_turn" && isStreaming && onStop) {
      handleStop();
      clear();
      clearComposerText();
      onQuotedContextChange?.(null);
      return;
    }
    const isSideChannel = isUserShell || isSideChannelLifecycle(slashLifecycle);
    const finalizeActiveTurn = slashLifecycle === "finalize_active_turn";
    if (!isUserShell && !slashLifecycle) {
      const prompt = collectGuidancePrompt();
      const error = queuedPromptError(prompt);
      if (error) {
        setInlineError(error);
        return;
      }
      if (queuedPrompt) {
        sendQueuedPrompt(prompt, options);
        if (draftKey) draftStore?.delete(draftKey);
        clear();
        clearComposerText(!hasTouchPrimaryPointer);
        onQuotedContextChange?.(null);
        return;
      }
    }
    const submittedDraft = draftKey ? draftStore?.get(draftKey) : undefined;
    const finishSend = () => {
      // A pending send can finish after this composer unmounts and a newer draft is started.
      if (
        draftKey &&
        draftStore &&
        !acceptComposerDraft(draftStore, draftKey, submittedDraft)
      )
        return;
      if (hasTouchPrimaryPointer) textareaRef.current?.blur();
      if ((!isStreaming && !isUserShell) || finalizeActiveTurn)
        setQueuedPrompt(null);
      // Bubble owns the data URL copy; safe to revoke every staged blob
      // preview here without affecting the rendered message.
      clear();
      clearComposerText(!hasTouchPrimaryPointer);
      onQuotedContextChange?.(null);
    };
    const result = onSend(
      content,
      payload,
      isSideChannel
        ? {
            ...options,
            sideChannel: true,
            ...(isUserShell ? { userShell: true } : {}),
            ...(finalizeActiveTurn ? { finalizeActiveTurn } : {}),
          }
        : isStreaming
          ? { ...options, continueActiveTurn: true }
          : options,
    );
    if (result instanceof Promise) {
      setSendPending(true);
      void result
        .then((accepted) => {
          if (accepted !== false) finishSend();
        })
        .catch((error: unknown) => {
          setInlineError(
            error instanceof Error ? error.message : "Failed to send message",
          );
        })
        .finally(() => setSendPending(false));
      return;
    }
    if (result !== false) finishSend();
  }, [
    activeCliMentionApps,
    activeMcpPresetMentions,
    activeSessionMentions,
    canSend,
    draftKey,
    draftStore,
    clear,
    clearComposerText,
    collectGuidancePrompt,
    queuedPrompt,
    queuedPromptError,
    sendQueuedPrompt,
    setQueuedPrompt,
    hasTouchPrimaryPointer,
    hasComposerContent,
    handleStop,
    images.length,
    isStreaming,
    isUserShell,
    maxTextBytes,
    requiresModelSetup,
    onSend,
    onStop,
    onContinue,
    showContinueButton,
    interactionDisabled,
    onQuotedContextChange,
    normalizedQuotedContext,
    readyImages,
    slashCommands,
    t,
    textTooLargeMessage,
    value,
  ]);
  return { submit };
}
