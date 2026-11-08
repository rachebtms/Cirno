import { useWorkspaceOpen } from "@/features/workbench/context";
import type { PointerEvent as ReactPointerEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useFilePreviewState, type FilePreviewState, type FilePreviewStore } from "@/hooks/useFilePreviewState";
import {
  ApiError,
  fetchFilePreview,
  fetchFilePreviewAvailability,
  fetchFileReferenceMetadata
} from "@/lib/api";
import type { FilePreviewPayload, FileReferenceMetadata } from "@/lib/contracts/files";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import { createFilePreviewResource } from "@/lib/file-preview-resource";
import { useClient } from "@/providers/ClientProvider";

const FILE_PREVIEW_DEFAULT_WIDTH = 544;
const FILE_PREVIEW_MIN_WIDTH = 280;
const FILE_PREVIEW_MAX_WIDTH = 860;
const FILE_PREVIEW_MIN_MAIN_WIDTH = 360;
const FILE_PREVIEW_CLOSE_ANIMATION_MS = 320;

type FilePreviewAvailabilityCacheEntry = {
  available?: boolean;
  promise: Promise<boolean>;
  revision: number;
};

function clampFilePreviewWidth(width: number, maxWidth: number): number {
  return Math.min(Math.max(width, FILE_PREVIEW_MIN_WIDTH), maxWidth);
}

function maxFilePreviewWidth(containerWidth: number): number {
  // Keep at least half a narrow pane, or 360px in a wider pane, for the conversation.
  const reserved = Math.min(FILE_PREVIEW_MIN_MAIN_WIDTH, containerWidth / 2);
  return Math.max(0, Math.min(FILE_PREVIEW_MAX_WIDTH, containerWidth - reserved));
}

interface ThreadPreviewOptions {
  chatId: string | null;
  previewSessionKey: string | null;
  workspaceScope: WorkspaceScopePayload | null;
  temporary: boolean;
  headerActive: boolean;
  filePreviewStore?: FilePreviewStore;
  messageCount: number;
}

export function useThreadPreview({
  chatId, previewSessionKey, workspaceScope, temporary, headerActive, filePreviewStore, messageCount,
}: ThreadPreviewOptions) {
  const { client, getToken, token } = useClient();
  const workspaceOpen = useWorkspaceOpen();
  const [browserDirty, setBrowserDirty] = useState(false);
  const [pendingPreviewAction, setPendingPreviewAction] = useState<(() => void) | null>(null);
  const guardPreview = (action: () => void) => { if (browserDirty) setPendingPreviewAction(() => action); else action(); };
  const previewStoreKey = previewSessionKey ?? "new:files";
  const { state: previewState, openFile, openBrowser, resolveFile, selectTab, closeTab, close: closePreview, setWidth: setFilePreviewWidth } =
    useFilePreviewState(previewStoreKey, filePreviewStore);
  const [closingPreview, setClosingPreview] = useState<{ key: string; state: FilePreviewState } | null>(null);
  const filePreviewClosing = closingPreview?.key === previewStoreKey;
  const visiblePreview = filePreviewClosing ? closingPreview.state : previewState;
  const activePreview = visiblePreview.tabs.find((tab) => tab.id === visiblePreview.activeId);
  const previewOpen = Boolean(activePreview);
  const [filePreviewMaxWidth, setFilePreviewMaxWidth] = useState(FILE_PREVIEW_MAX_WIDTH);
  const filePreviewWidth = clampFilePreviewWidth(previewState.width, filePreviewMaxWidth);
  const shellRef = useRef<HTMLElement | null>(null);
  const filePreviewWidthRef = useRef(FILE_PREVIEW_DEFAULT_WIDTH);
  const filePreviewCloseTimerRef = useRef<number | null>(null);
  const filePreviewResizeCleanupRef = useRef<(() => void) | null>(null);
  useEffect(() => {
    filePreviewWidthRef.current = filePreviewWidth;
  }, [filePreviewWidth]);

  useEffect(() => {
    filePreviewResizeCleanupRef.current?.();
    if (filePreviewCloseTimerRef.current !== null) {
      window.clearTimeout(filePreviewCloseTimerRef.current);
      filePreviewCloseTimerRef.current = null;
    }
    setClosingPreview(null);
  }, [previewSessionKey]);

  useEffect(() => {
    return () => {
      filePreviewResizeCleanupRef.current?.();
      if (filePreviewCloseTimerRef.current !== null) {
        window.clearTimeout(filePreviewCloseTimerRef.current);
      }
    };
  }, []);

  const filePreviewAvailabilityCache = useMemo(
    () => new Map<string, FilePreviewAvailabilityCacheEntry>(),
    [previewSessionKey],
  );
  const filePreviewAvailabilityRevision = messageCount;
  const resolveFilePreviewAvailability = useCallback((path: string) => {
    if (!previewSessionKey) return Promise.resolve(false);
    const cached = filePreviewAvailabilityCache.get(path);
    if (
      cached
      && (cached.available !== false || cached.revision === filePreviewAvailabilityRevision)
    ) {
      return cached.promise;
    }
    const request = temporary
      ? client.requestMutation<{ available: boolean }>("temporary_chat.file_preview", {
        chat_id: chatId, path, probe: true,
      }).then((result) => result.available)
      : fetchFilePreviewAvailability(getToken(), previewSessionKey, path);
    const pending = request.catch(
      (error: unknown) => {
        if (error instanceof ApiError) {
          if ([400, 403, 404, 413, 415].includes(error.status)) return false;
        }
        return false;
      },
    );
    const entry: FilePreviewAvailabilityCacheEntry = {
      promise: pending,
      revision: filePreviewAvailabilityRevision,
    };
    filePreviewAvailabilityCache.set(path, entry);
    void pending.then((available) => {
      if (filePreviewAvailabilityCache.get(path) === entry) {
        entry.available = available;
      }
    });
    return pending;
  }, [
    filePreviewAvailabilityCache,
    filePreviewAvailabilityRevision,
    getToken,
    previewSessionKey,
    temporary,
    client,
    chatId,
  ]);

  const loadTemporaryFilePreview = useCallback((path: string) =>
    client.requestMutation<FilePreviewPayload>("temporary_chat.file_preview", {
      chat_id: chatId, path,
    }).catch((error: unknown) => {
      if (error instanceof Error && "status" in error && typeof error.status === "number") {
        throw new ApiError(error.status, error.message);
      }
      throw error;
    }), [client, chatId]);

  const handleCloseFilePreview = useCallback(() => {
    if (!previewState.activeId || filePreviewClosing) return;
    filePreviewResizeCleanupRef.current?.();
    setClosingPreview({ key: previewStoreKey, state: previewState });
    // Record the closed state immediately, even if navigation interrupts the animation.
    closePreview();
    filePreviewCloseTimerRef.current = window.setTimeout(() => {
      filePreviewCloseTimerRef.current = null;
      setClosingPreview(null);
    }, FILE_PREVIEW_CLOSE_ANIMATION_MS);
  }, [previewStoreKey, filePreviewClosing, previewState, closePreview]);

  const cancelPreviewClose = useCallback(() => {
    filePreviewResizeCleanupRef.current?.();
    if (filePreviewCloseTimerRef.current !== null) {
      window.clearTimeout(filePreviewCloseTimerRef.current);
      filePreviewCloseTimerRef.current = null;
    }
    setClosingPreview(null);
  }, []);

  useEffect(() => {
    // A retained background tab must not replay a closed pane's exit animation.
    if (!headerActive) cancelPreviewClose();
  }, [headerActive, cancelPreviewClose]);

  const handleOpenFilePreview = useCallback((path: string) => {
    if (workspaceOpen && !temporary) {
      workspaceOpen("file", { path, sessionKey: previewSessionKey, scope: workspaceScope });
      return;
    }
    cancelPreviewClose();
    openFile(path);
  }, [cancelPreviewClose, openFile, workspaceOpen, temporary, previewSessionKey, workspaceScope]);

  const handleClosePreviewTab = useCallback((id: string) => {
    if (previewState.tabs.length === 1) handleCloseFilePreview();
    else {
      filePreviewResizeCleanupRef.current?.();
      closeTab(id);
    }
  }, [previewState.tabs.length, handleCloseFilePreview, closeTab]);

  // Markdown blocks can retain rendered links while their text is unchanged.
  // Keep their callback stable, but always act on the current pane/session state.
  const openFilePreviewRef = useRef(handleOpenFilePreview);
  openFilePreviewRef.current = handleOpenFilePreview;
  const openFilePreview = useCallback((path: string) => openFilePreviewRef.current(path), []);
  const resolveFileMetadata = useCallback((path: string) => {
    if (!previewSessionKey) return Promise.reject(new Error("No active session"));
    return temporary
      ? client.requestMutation<FileReferenceMetadata>("temporary_chat.file_preview", {
        chat_id: chatId, path, metadata: true,
      })
      : fetchFileReferenceMetadata(getToken(), previewSessionKey, path);
  }, [chatId, client, getToken, previewSessionKey, temporary]);
  const loadFilePreview = useCallback((path: string) => {
    if (!previewSessionKey) return Promise.reject(new Error("No active session"));
    return temporary ? loadTemporaryFilePreview(path) : fetchFilePreview(getToken(), previewSessionKey, path);
  }, [previewSessionKey, temporary, loadTemporaryFilePreview, getToken]);
  const filePreviews = useMemo(() => createFilePreviewResource(loadFilePreview), [loadFilePreview]);
  const fileActions = useMemo(() => ({
    resolveMetadata: resolveFileMetadata,
    loadPreview: filePreviews.load,
  }), [resolveFileMetadata, filePreviews]);

  useEffect(() => {
    if (!previewOpen || !headerActive) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented || event.isComposing) return;
      // Let a dialog/menu above the pane consume Escape without closing this preview.
      if (document.querySelector('[role="dialog"], [role="alertdialog"], [role="menu"], [role="listbox"], [data-radix-popper-content-wrapper]')) return;
      event.preventDefault();
      guardPreview(handleCloseFilePreview);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [previewOpen, headerActive, handleCloseFilePreview, browserDirty]);

  const handleFilePreviewResizeStart = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    filePreviewResizeCleanupRef.current?.();
    event.preventDefault();
    event.stopPropagation();
    const panel = event.currentTarget.closest<HTMLElement>("[data-file-preview-panel]");
    const shellRect = shellRef.current?.getBoundingClientRect();
    const rightEdge = shellRect?.right ?? window.innerWidth;
    const maxWidth = maxFilePreviewWidth(shellRect?.width ?? window.innerWidth);
    const originalBodyCursor = document.body.style.cursor;
    const originalBodyUserSelect = document.body.style.userSelect;
    const originalPanelTransition = panel?.style.transition ?? "";
    const frameElement = panel?.querySelector("iframe");
    const originalFramePointerEvents = frameElement?.style.pointerEvents ?? "";
    let nextWidth = filePreviewWidthRef.current;
    let frame: number | null = null;

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    if (panel) panel.style.transition = "none";
    if (frameElement) frameElement.style.pointerEvents = "none";

    const applyWidth = (clientX: number) => {
      nextWidth = clampFilePreviewWidth(rightEdge - clientX, maxWidth);
      filePreviewWidthRef.current = nextWidth;
      if (frame !== null) return;
      frame = window.requestAnimationFrame(() => {
        frame = null;
        panel?.style.setProperty("--file-preview-width", `${nextWidth}px`);
        panel?.style.setProperty("--file-preview-slot-width", `${nextWidth}px`);
      });
    };
    const handlePointerMove = (moveEvent: PointerEvent) => {
      moveEvent.preventDefault();
      applyWidth(moveEvent.clientX);
    };
    const stopResize = (commit: boolean) => {
      if (frame !== null) {
        window.cancelAnimationFrame(frame);
        frame = null;
      }
      panel?.style.setProperty("--file-preview-width", `${nextWidth}px`);
      panel?.style.setProperty("--file-preview-slot-width", `${nextWidth}px`);
      if (panel) panel.style.transition = originalPanelTransition;
      if (frameElement) frameElement.style.pointerEvents = originalFramePointerEvents;
      if (commit) setFilePreviewWidth(nextWidth);
      document.body.style.cursor = originalBodyCursor;
      document.body.style.userSelect = originalBodyUserSelect;
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
      filePreviewResizeCleanupRef.current = null;
    };
    const handlePointerUp = () => stopResize(true);
    filePreviewResizeCleanupRef.current = () => stopResize(false);

    applyWidth(event.clientX);
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);
  }, [setFilePreviewWidth]);

  useEffect(() => {
    if (!previewOpen) return;
    const clampToShell = () => {
      const shellWidth = shellRef.current?.getBoundingClientRect().width ?? window.innerWidth;
      const maxWidth = maxFilePreviewWidth(shellWidth);
      setFilePreviewMaxWidth(maxWidth);
    };
    clampToShell();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(clampToShell);
    if (shellRef.current) observer?.observe(shellRef.current);
    window.addEventListener("resize", clampToShell);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", clampToShell);
    };
  }, [previewOpen]);

  const openFiles = () => {
    if (workspaceOpen && !temporary) {
      workspaceOpen("files", { sessionKey: previewSessionKey, scope: workspaceScope });
    } else {
      guardPreview(() => { cancelPreviewClose(); openBrowser(); });
    }
  };
  return {
    shellRef, previewOpen, fileActions, resolveFilePreviewAvailability, openFilePreview, openFiles,
    activePreview, previewStoreKey, visiblePreview, filePreviewWidth, filePreviewClosing, guardPreview,
    selectTab, handleClosePreviewTab, handleCloseFilePreview, handleFilePreviewResizeStart,
    workspaceScope, client, previewSessionKey, setBrowserDirty, token, filePreviews, resolveFile,
    pendingPreviewAction, setPendingPreviewAction,
  };
}
