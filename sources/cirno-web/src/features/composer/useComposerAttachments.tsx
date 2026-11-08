import { splitCapabilityMentionSegments } from "@/components/CliAppMentionText";
import { useComposerMentionInput } from "@/hooks/useComposerMentionInput";
import type { ComposerDraft } from "@/lib/composer-draft";
import { sameComposerDraft } from "@/lib/composer-draft";
import {
  composerMentionText,
  isCapabilityMentionStart,
  type CapabilityMentionSegment,
} from "@/lib/composer-mention-text";
import { useCallback, useEffect, useLayoutEffect, useMemo } from "react";
import {
  pastedFilePath,
  PastedPathRange,
} from "../../../packages/client-events/attachments";
import { sessionMentionOptions } from "./capability-mentions";
import {
  CliAppMentionQuery,
  mentionInsertion,
  SESSION_MENTIONS_LIMIT,
} from "./contracts";
import type { ComponentInputs } from "./inputs";
import type { useComposerSelection } from "./useComposerSelection";
import type { useComposerState } from "./useComposerState";

export function useComposerAttachments({
  composerState,
  composerSelection,
  inputs,
}: {
  composerState: ReturnType<typeof useComposerState>;
  composerSelection: ReturnType<typeof useComposerSelection>;
  inputs: ComponentInputs;
}) {
  const {
    interactionDisabled,
    cliAppMenuDismissed,
    cursorPosition,
    value,
    boundSessionMentions,
    setValue,
    setSlashMenuDismissed,
    setCliAppMenuDismissed,
    setCursorPosition,
    textareaRef,
    onAttachmentPaste,
    pathCheckGeneration,
    setPathInspection,
    scopeIdentity,
    pathCheckScope,
    setInlineError,
    t,
    pathInspection,
    addLocal,
    formatRejection,
    sessionDragPreview,
    setBoundSessionMentions,
    draftAttachmentsReady,
    images,
  } = composerState;
  const { isUserShell } = composerSelection;
  const {
    onMentionSearch,
    sessions,
    cliApps,
    mcpPresets,
    pendingQueueKey,
    onInspectAttachment,
    draftKey,
    draftStore,
    quotedContext,
    persistDraft,
  } = inputs;
  const cliAppMention = useMemo<CliAppMentionQuery | null>(() => {
    if (interactionDisabled || isUserShell || cliAppMenuDismissed) return null;
    const caret = Math.min(Math.max(cursorPosition, 0), value.length);
    const beforeCaret = value.slice(0, caret);
    const match = /@([\p{L}\p{N}_-]*)$/iu.exec(beforeCaret);
    if (!match || !isCapabilityMentionStart(value, match.index)) return null;
    const query = match[1].toLowerCase();
    return {
      query,
      start: match.index,
      end: caret,
    };
  }, [
    cliAppMenuDismissed,
    cursorPosition,
    interactionDisabled,
    isUserShell,
    value,
  ]);
  const mentionSearchActive = cliAppMention !== null;
  useEffect(() => {
    if (mentionSearchActive) onMentionSearch?.();
  }, [mentionSearchActive, onMentionSearch]);
  const availableSessionMentions = useMemo(
    () => sessionMentionOptions(sessions),
    [sessions],
  );
  const sessionMentionCatalog = useMemo(
    () => [...availableSessionMentions, ...boundSessionMentions],
    [availableSessionMentions, boundSessionMentions],
  );
  const mentionSegments = useMemo<CapabilityMentionSegment[]>(
    () =>
      isUserShell
        ? [{ kind: "text", text: value }]
        : splitCapabilityMentionSegments(
            value,
            cliApps,
            mcpPresets,
            sessionMentionCatalog,
          ),
    [cliApps, isUserShell, mcpPresets, sessionMentionCatalog, value],
  );
  const editMentionInput = useCallback((next: string, cursor: number) => {
    setValue(next);
    setSlashMenuDismissed(false);
    setCliAppMenuDismissed(false);
    setCursorPosition(cursor);
  }, []);
  const mentionInput = useComposerMentionInput({
    segments: mentionSegments,
    inputRef: textareaRef,
    onEdit: editMentionInput,
    resetKey: pendingQueueKey,
  });
  const { rawSelection, replace: replaceMentionInput } = mentionInput;
  const onPaste = useCallback(
    (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
      onAttachmentPaste(event);
      if (
        event.defaultPrevented ||
        interactionDisabled ||
        isUserShell ||
        !onInspectAttachment
      )
        return;
      const raw = event.clipboardData.getData("text/plain");
      const path = pastedFilePath(raw);
      if (!path) return;
      event.preventDefault();
      const { start, end } = rawSelection();
      const pasted = value.slice(0, start) + raw + value.slice(end);
      const generation = ++pathCheckGeneration.current;
      replaceMentionInput(pasted, start + raw.length);
      setPathInspection({
        generation,
        scope: scopeIdentity,
        range: new PastedPathRange(pasted, start, start + raw.length),
      });
      void onInspectAttachment(path)
        .then((attachment) => {
          if (generation !== pathCheckGeneration.current) return;
          setPathInspection((current) =>
            current?.generation === generation
              ? { ...current, attachment }
              : current,
          );
        })
        .catch((error: unknown) => {
          if (
            generation !== pathCheckGeneration.current ||
            pathCheckScope.current !== scopeIdentity
          )
            return;
          setPathInspection(null);
          if (
            error instanceof Error &&
            "status" in error &&
            error.status === 404
          )
            return;
          setInlineError(
            error instanceof Error
              ? error.message
              : t("message.attachmentUnavailable"),
          );
        });
    },
    [
      interactionDisabled,
      isUserShell,
      onAttachmentPaste,
      onInspectAttachment,
      rawSelection,
      replaceMentionInput,
      scopeIdentity,
      t,
      value,
    ],
  );
  useLayoutEffect(() => {
    if (!pathInspection) return;
    if (
      isUserShell ||
      pathInspection.scope !== scopeIdentity ||
      !pathInspection.range.update(value)
    ) {
      pathCheckGeneration.current += 1;
      setPathInspection(null);
      return;
    }
    // Let the native IME commit before removing the confirmed path from its text.
    if (!pathInspection.attachment || mentionInput.isComposing) return;
    const edited = pathInspection.range.replace("", rawSelection().start);
    if (edited) {
      const rejection = addLocal(pathInspection.attachment);
      if (rejection) setInlineError(formatRejection(rejection));
      else {
        replaceMentionInput(edited.value, edited.cursor, {
          preserveFocus: true,
        });
        setInlineError(null);
      }
    }
    setPathInspection(null);
  }, [
    addLocal,
    formatRejection,
    isUserShell,
    mentionInput.isComposing,
    pathInspection,
    rawSelection,
    replaceMentionInput,
    scopeIdentity,
    value,
  ]);
  const draftText = composerMentionText(mentionInput.segments).raw;
  const sessionDragInsertion = sessionDragPreview
    ? mentionInsertion(
        value,
        sessionDragPreview.mention.name,
        sessionDragPreview.start,
        sessionDragPreview.end,
      )
    : null;
  const displayMentionSegments =
    sessionDragInsertion && sessionDragPreview
      ? splitCapabilityMentionSegments(
          sessionDragInsertion.value,
          cliApps,
          mcpPresets,
          sessionMentionCatalog,
        )
      : mentionInput.segments;
  const activeSessionMentions = useMemo(() => {
    const seen = new Set<string>();
    return mentionSegments.flatMap((segment) => {
      if (segment.kind !== "session" || seen.has(segment.mention.session_key))
        return [];
      seen.add(segment.mention.session_key);
      return [segment.mention];
    });
  }, [mentionSegments]);
  useLayoutEffect(() => {
    // Pin resolved identities so a catalog refresh cannot retarget an existing reference.
    if (
      activeSessionMentions.length !== boundSessionMentions.length ||
      activeSessionMentions.some(
        (mention, index) => mention !== boundSessionMentions[index],
      )
    ) {
      setBoundSessionMentions(activeSessionMentions);
    }
  }, [activeSessionMentions, boundSessionMentions]);
  useLayoutEffect(() => {
    if (!draftKey || !draftStore || !draftAttachmentsReady) return;
    if (!draftText && images.length === 0 && !quotedContext) {
      if (draftStore.getStorageIssue(draftKey)?.action === "read") return;
      draftStore.delete(draftKey, persistDraft);
      return;
    }
    const nextDraft: ComposerDraft = {
      text: draftText,
      attachments: images.flatMap((image): ComposerDraft["attachments"] =>
        image.local
          ? [image.local]
          : image.file instanceof File
            ? [image.file]
            : [],
      ),
      sessionMentions: activeSessionMentions,
      quotedContext,
    };
    const previous = draftStore.get(draftKey);
    draftStore.set(
      draftKey,
      previous && sameComposerDraft(previous, nextDraft) ? previous : nextDraft,
      persistDraft,
    );
  }, [
    activeSessionMentions,
    draftAttachmentsReady,
    draftKey,
    draftStore,
    images,
    persistDraft,
    quotedContext,
    draftText,
  ]);
  const insertableSessionMentions = useMemo(
    () =>
      availableSessionMentions.filter((mention) => {
        const bound = activeSessionMentions.find(
          (active) => active.name.toLowerCase() === mention.name.toLowerCase(),
        );
        return (
          (!bound || bound.session_key === mention.session_key) &&
          (activeSessionMentions.length < SESSION_MENTIONS_LIMIT ||
            activeSessionMentions.some(
              (active) => active.session_key === mention.session_key,
            ))
        );
      }),
    [activeSessionMentions, availableSessionMentions],
  );
  return {
    cliAppMention,
    insertableSessionMentions,
    sessionMentionCatalog,
    displayMentionSegments,
    sessionDragInsertion,
    draftText,
    mentionSegments,
    mentionInput,
    replaceMentionInput,
    rawSelection,
    activeSessionMentions,
    onPaste,
  };
}
