import { useTabCompact } from "@/ui/layout/TabSurface";
import type { ComposerDraft } from "@/lib/composer-draft";
import {
  acceptedAttachmentKind,
  MAX_ATTACHMENT_BYTES,
  MAX_ATTACHMENTS_PER_MESSAGE,
  MAX_VIDEO_BYTES,
  useAttachedImages,
  type AttachmentError,
} from "@/hooks/useAttachedImages";
import { useClipboardAndDrop } from "@/hooks/useClipboardAndDrop";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { usePreferences } from "@/hooks/usePreferences";
import { useThreadVisibility } from "@/hooks/useThreadVisibility";
import type { SessionMention } from "@/lib/contracts/messages";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { useTranslation } from "react-i18next";
import {
  PastedPathRange,
  type LocalAttachment,
} from "../../../packages/client-events/attachments";
import {
  readSlashRecents,
} from "./commands";
import { formatBytes } from "./contracts";
import { autosizeTextarea } from "@/ui/fields/textarea";
import type { ComponentInputs } from "./inputs";
import { queuedPromptsStorageKey } from "./queue/storage";
import { queuedPromptStoreFor } from "./queue/store";

export function useComposerState({ inputs }: { inputs: ComponentInputs }) {
  const {
    active,
    draftKey,
    draftStore,
    persistDraft,
    workspaceScope,
    pendingQueueKey,
    disabled,
    isStreaming,
    variant,
    workspaceDefaultScope,
    onWorkspaceScopeChange,
    onLoadWorkspaceProjects,
    onBrowseWorkspaceDirectories,
    onResolveWorkspaceProject,
    onFavoriteWorkspaceProject,
    workspaceControls,
    workspaceControlsHidden,
    activeTurnId,
    placeholder,
    ingressLimits,
    compactWhenIdle,
    workspaceError,
    focusRequest,
  } = inputs;
  const { t } = useTranslation();
  const canFocus = useThreadVisibility() && active;
  const [initialDraft] = useState(() =>
    draftKey ? draftStore?.get(draftKey, persistDraft) : undefined,
  );
  const [value, setValue] = useState(initialDraft?.text ?? "");
  const [boundSessionMentions, setBoundSessionMentions] = useState<
    SessionMention[]
  >(initialDraft?.sessionMentions ?? []);
  const [sessionDragPreview, setSessionDragPreview] = useState<{
    mention: SessionMention;
    start: number;
    end: number;
  } | null>(null);
  const [inlineError, setInlineError] = useState<string | null>(null);
  const [sendPending, setSendPending] = useState(false);
  const [pathInspection, setPathInspection] = useState<{
    generation: number;
    scope: string;
    range: PastedPathRange;
    attachment?: LocalAttachment;
  } | null>(null);
  const pathCheckGeneration = useRef(0);
  const pathCheckScope = useRef("");
  const scopeIdentity = `${workspaceScope?.project_path ?? ""}:${workspaceScope?.access_mode ?? ""}`;
  pathCheckScope.current = scopeIdentity;
  useEffect(
    () => () => {
      pathCheckGeneration.current += 1;
    },
    [],
  );
  const [modelSetupAttentionRequest, setModelSetupAttentionRequest] =
    useState(0);
  const queuedPromptStorageKey = queuedPromptsStorageKey(pendingQueueKey);
  const queuedPromptStore = useMemo(
    () => queuedPromptStoreFor(queuedPromptStorageKey),
    [queuedPromptStorageKey],
  );
  const queueSnapshot = useSyncExternalStore(
    queuedPromptStore.subscribe,
    queuedPromptStore.getSnapshot,
  );
  const queuedPrompt = queueSnapshot.prompt;
  const setQueuedPrompt = queuedPromptStore.set;
  const interactionDisabled =
    !!disabled || sendPending || queueSnapshot.sending;
  const [slashMenuDismissed, setSlashMenuDismissed] = useState(false);
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0);
  const [cliAppMenuDismissed, setCliAppMenuDismissed] = useState(false);
  const [selectedCliAppIndex, setSelectedCliAppIndex] = useState(0);
  const [cursorPosition, setCursorPosition] = useState(0);
  const [recentSlashCommands, setRecentSlashCommands] = useState<string[]>(() =>
    readSlashRecents(),
  );
  const hasTouchPrimaryPointer = useMediaQuery(
    "(hover: none) and (pointer: coarse)",
  );
  const hasCoarsePointer = useMediaQuery("(pointer: coarse)");
  const mobileWorkspaceControls = useTabCompact(640);
  const { readingTextSize, customReadingTextSize } = usePreferences();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mentionOverlayRef = useRef<HTMLDivElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const [compactControls, setCompactControls] = useState(false);
  useLayoutEffect(() => {
    const form = formRef.current;
    if (!form) return;
    let previousWidth = 0;
    const update = () => {
      const width = form.getBoundingClientRect().width;
      if (width <= 0 || width === previousWidth) return;
      previousWidth = width;
      setCompactControls(width <= 512);
      const input = textareaRef.current;
      if (input) autosizeTextarea(input);
    };
    update();
    const observer =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(form);
    window.addEventListener("resize", update);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", update);
    };
  }, []);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const chipRefs = useRef(new Map<string, HTMLButtonElement>());
  const queuedPromptCounterRef = useRef(0);
  const previousPendingQueueKeyRef = useRef(pendingQueueKey);
  const previousQueueRunRef = useRef({ key: pendingQueueKey, isStreaming });
  const isHero = variant === "hero";
  const projectPickerAvailable =
    !!workspaceDefaultScope &&
    !!onWorkspaceScopeChange &&
    !!onLoadWorkspaceProjects &&
    !!onBrowseWorkspaceDirectories &&
    !!onResolveWorkspaceProject &&
    !!onFavoriteWorkspaceProject &&
    workspaceControls?.can_change_project !== false;
  const showProjectPicker = projectPickerAvailable && !workspaceControlsHidden;
  useEffect(() => {
    if (!isStreaming || !activeTurnId) return;
    setQueuedPrompt((prompt) =>
      !prompt || prompt.autoPaused || prompt.autoAfterTurnId === activeTurnId
        ? prompt
        : { ...prompt, autoAfterTurnId: activeTurnId },
    );
  }, [activeTurnId, isStreaming, pendingQueueKey, setQueuedPrompt]);
  const resolvedPlaceholder =
    placeholder ?? t("thread.composer.placeholderThread");
  const maxAttachments =
    ingressLimits?.attachments.max_count ?? MAX_ATTACHMENTS_PER_MESSAGE;
  const maxFileBytes =
    ingressLimits?.attachments.max_file_bytes ?? MAX_ATTACHMENT_BYTES;
  const maxVideoBytes =
    ingressLimits?.attachments.max_video_bytes ?? MAX_VIDEO_BYTES;
  const maxTextBytes = ingressLimits?.message.max_text_bytes ?? 64 * 1024;
  const {
    images,
    enqueue,
    addLocal,
    remove,
    clear,
    restoreReadyImages,
    encoding: encodingFiles,
    full,
  } = useAttachedImages({ ingressLimits });
  const encoding = encodingFiles || pathInspection !== null;
  const restoredDraftAttachments = useRef(false);
  const [draftAttachmentsReady, setDraftAttachmentsReady] = useState(
    !initialDraft?.attachments.length,
  );
  const restoreDraftAttachments = useCallback((attachments: ComposerDraft["attachments"]) => {
    for (const attachment of attachments) {
      if (attachment instanceof File) enqueue([attachment], { restoringDraft: true });
      else addLocal(attachment, { restoringDraft: true });
    }
  }, [enqueue, addLocal]);
  useLayoutEffect(() => {
    if (restoredDraftAttachments.current) return;
    restoredDraftAttachments.current = true;
    restoreDraftAttachments(initialDraft?.attachments ?? []);
    setDraftAttachmentsReady(true);
  }, [restoreDraftAttachments, initialDraft]);
  const formatRejection = useCallback(
    (reason: Exclude<AttachmentError, "too_large">): string => {
      const key = `thread.composer.imageRejected.${reason}`;
      const fallback =
        reason === "too_many_videos"
          ? "Max 1 video per message"
          : reason === "too_many_attachments"
            ? `Max ${maxAttachments} attachments per message`
            : reason === "empty_file"
              ? "Empty files cannot be attached"
              : reason === "total_too_large"
                ? "Attachments are too large together — remove some or use smaller files"
                : "Unsupported file type";
      return t(key, { max: maxAttachments, defaultValue: fallback });
    },
    [maxAttachments, t],
  );
  const formatUploadTooLarge = useCallback(
    (size: number, maximum: number) =>
      t("thread.composer.imageRejected.too_large", {
        size: formatBytes(size),
        max: formatBytes(maximum),
      }),
    [t],
  );
  const textTooLargeMessage = useCallback(
    () =>
      t("thread.composer.textTooLarge", {
        max: formatBytes(maxTextBytes),
        defaultValue: `Message text is too large (max ${formatBytes(maxTextBytes)})`,
      }),
    [maxTextBytes, t],
  );
  const addFiles = useCallback(
    (files: File[]) => {
      if (interactionDisabled || files.length === 0) return;
      const { rejected } = enqueue(files);
      if (rejected.length > 0) {
        const { reason, file } = rejected[0];
        setInlineError(
          reason === "too_large"
            ? formatUploadTooLarge(
                file.size,
                acceptedAttachmentKind(file) === "video"
                  ? maxVideoBytes
                  : maxFileBytes,
              )
            : formatRejection(reason),
        );
      } else {
        setInlineError(null);
      }
    },
    [
      enqueue,
      formatRejection,
      formatUploadTooLarge,
      interactionDisabled,
      maxFileBytes,
      maxVideoBytes,
    ],
  );
  const {
    isDragging,
    onPaste: onAttachmentPaste,
    onDragEnter,
    onDragOver,
    onDragLeave,
    onDrop,
  } = useClipboardAndDrop(addFiles);
  useEffect(() => {
    if (
      !canFocus ||
      compactWhenIdle ||
      interactionDisabled ||
      hasTouchPrimaryPointer ||
      (workspaceError && showProjectPicker)
    ) {
      return;
    }
    const el = textareaRef.current;
    if (!el) return;
    const id = requestAnimationFrame(() => el.focus());
    return () => cancelAnimationFrame(id);
  }, [
    canFocus,
    compactWhenIdle,
    hasTouchPrimaryPointer,
    interactionDisabled,
    showProjectPicker,
    workspaceError,
  ]);
  useEffect(() => {
    if (!canFocus || !focusRequest || interactionDisabled) return;
    const id = requestAnimationFrame(() => textareaRef.current?.focus());
    return () => cancelAnimationFrame(id);
  }, [canFocus, focusRequest, interactionDisabled]);
  return {
    images,
    value,
    interactionDisabled,
    encoding,
    slashMenuDismissed,
    cursorPosition,
    recentSlashCommands,
    t,
    cliAppMenuDismissed,
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
    pathInspection,
    addLocal,
    formatRejection,
    sessionDragPreview,
    setBoundSessionMentions,
    draftAttachmentsReady,
    setSelectedCommandIndex,
    setSelectedCliAppIndex,
    selectedCommandIndex,
    selectedCliAppIndex,
    formRef,
    mentionOverlayRef,
    compactControls,
    readingTextSize,
    customReadingTextSize,
    previousPendingQueueKeyRef,
    clear,
    setQueuedPrompt,
    setRecentSlashCommands,
    setSessionDragPreview,
    maxTextBytes,
    textTooLargeMessage,
    maxAttachments,
    maxVideoBytes,
    maxFileBytes,
    formatUploadTooLarge,
    queuedPromptCounterRef,
    queuedPrompt,
    restoreReadyImages,
    restoreDraftAttachments,
    queuedPromptStore,
    queueStorageIssue: queueSnapshot.storageIssue,
    queueSendError: queueSnapshot.error
      ? queueSnapshot.error.kind === "rejected" ? t("thread.composer.queued.sendRejected") : queueSnapshot.error.detail
      : null,
    previousQueueRunRef,
    queuedPromptStorageKey,
    setSendPending,
    setModelSetupAttentionRequest,
    hasTouchPrimaryPointer,
    hasCoarsePointer,
    addFiles,
    remove,
    chipRefs,
    full,
    sendPending,
    isHero,
    inlineError,
    isDragging,
    showProjectPicker,
    modelSetupAttentionRequest,
    mobileWorkspaceControls,
    onDragEnter,
    onDragOver,
    onDragLeave,
    onDrop,
    resolvedPlaceholder,
    fileInputRef,
  };
}
