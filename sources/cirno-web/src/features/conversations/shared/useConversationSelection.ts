import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type RefObject,
} from "react";
import { useTranslation } from "react-i18next";
import type {
  ConversationDeleteActions,
  ConversationDeleteDecision,
  ConversationDeleteItem,
} from "./contracts";
import { selectionRange } from "./selection";

interface SelectionInputs extends ConversationDeleteActions {
  deleteItemsByKey: ReadonlyMap<string, ConversationDeleteItem>;
  selectableDeleteKeys: string[];
  archived: ReadonlySet<string>;
  archivedPanes: ReadonlySet<string>;
  scrollViewportRef: RefObject<HTMLElement | null>;
}

export function useConversationSelection({
  deleteItemsByKey,
  selectableDeleteKeys,
  archived,
  archivedPanes,
  scrollViewportRef,
  onRequestDelete,
  onRequestDeleteMany,
}: SelectionInputs) {
  const { t } = useTranslation();
  const selectionBarRef = useRef<HTMLDivElement>(null);
  const [selectionError, setSelectionError] = useState("");
  const [deleteSelectionMode, setDeleteSelectionMode] = useState(false);
  const [deleteConfirmationPending, setDeleteConfirmationPending] =
    useState(false);
  const [pendingArchive, setPendingArchive] = useState<{
    keys: string[];
    archive: boolean;
  } | null>(null);
  const [selectedDeleteKeys, setSelectedDeleteKeys] = useState<Set<string>>(
    () => new Set(),
  );
  const deleteSelectionAnchorRef = useRef<string | null>(null);
  const selectionConfirmationPending =
    pendingArchive !== null || deleteConfirmationPending;
  useEffect(() => {
    setSelectedDeleteKeys((current) => {
      const retained = new Set(
        [...current].filter((key) => deleteItemsByKey.has(key)),
      );
      return retained.size === current.size ? current : retained;
    });
    if (
      deleteSelectionAnchorRef.current &&
      !deleteItemsByKey.has(deleteSelectionAnchorRef.current)
    )
      deleteSelectionAnchorRef.current = null;
  }, [deleteItemsByKey]);
  const closeDeleteSelection = useCallback(() => {
    setPendingArchive(null);
    setDeleteSelectionMode(false);
    setSelectionError("");
    setSelectedDeleteKeys(new Set());
    deleteSelectionAnchorRef.current = null;
  }, []);

  useEffect(() => {
    if (!deleteSelectionMode) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || selectionConfirmationPending) return;
      closeDeleteSelection();
    };
    const onClick = (event: MouseEvent) => {
      if (selectionConfirmationPending) return;
      const target = event.target;
      if (target instanceof Node && selectionBarRef.current?.contains(target))
        return;
      const row =
        target instanceof Element
          ? target.closest("[data-chat-row], [data-workbench-tab]")
          : null;
      if (row && scrollViewportRef.current?.contains(row)) return;
      closeDeleteSelection();
    };
    window.addEventListener("keydown", onKeyDown);
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("click", onClick, true);
    };
  }, [
    closeDeleteSelection,
    deleteSelectionMode,
    selectionConfirmationPending,
    scrollViewportRef,
  ]);

  const beginDeleteSelection = (keys: string[]) => {
    const validKeys = keys.filter((key) => deleteItemsByKey.has(key));
    setDeleteSelectionMode(true);
    setSelectedDeleteKeys(new Set(validKeys));
    deleteSelectionAnchorRef.current = validKeys[0] ?? null;
  };
  const toggleDeleteSelection = (
    keys: string[],
    shiftKey = false,
    targetKey = keys[0],
  ) => {
    if (selectionConfirmationPending) return;
    const validKeys = keys.filter((key) => deleteItemsByKey.has(key));
    const anchorKey = deleteSelectionAnchorRef.current;
    const range =
      shiftKey && anchorKey && targetKey
        ? selectionRange(selectableDeleteKeys, anchorKey, targetKey)
        : null;
    setSelectedDeleteKeys((current) => {
      const next = new Set(current);
      if (range) {
        for (const key of range) next.add(key);
        for (const key of validKeys) next.add(key);
        return next;
      }
      const remove =
        validKeys.length > 0 && validKeys.every((key) => next.has(key));
      for (const key of validKeys) {
        if (remove) next.delete(key);
        else next.add(key);
      }
      return next;
    });
    if (!range) deleteSelectionAnchorRef.current = targetKey ?? null;
  };
  const requestDeleteItems = (
    items: ConversationDeleteItem[],
    onDecision?: ConversationDeleteDecision,
  ) => {
    if (items.length === 0) return false;
    if (items.length > 1 && !onRequestDeleteMany) {
      setSelectionError(
        t("chat.bulkDeleteUnavailable", {
          defaultValue: "This view can only delete one conversation at a time.",
        }),
      );
      return false;
    }
    if (onRequestDeleteMany) onRequestDeleteMany(items, onDecision);
    else onRequestDelete(items[0].key, items[0].label, onDecision);
    return true;
  };
  const requestDeleteKeys = (
    keys: string[],
    onDecision?: ConversationDeleteDecision,
  ) => {
    return requestDeleteItems(
      keys
        .map((key) => deleteItemsByKey.get(key))
        .filter((item): item is ConversationDeleteItem => item !== undefined),
      onDecision,
    );
  };
  const confirmDeleteSelection = () => {
    setDeleteConfirmationPending(true);
    const started = requestDeleteKeys(
      Array.from(selectedDeleteKeys),
      (confirmed) => {
        setDeleteConfirmationPending(false);
        if (confirmed) closeDeleteSelection();
      },
    );
    if (!started) setDeleteConfirmationPending(false);
  };
  const allSelectedArchived =
    selectedDeleteKeys.size > 0 &&
    Array.from(selectedDeleteKeys).every(
      (key) => archivedPanes.has(key) || archived.has(key),
    );

  return {
    deleteSelectionMode,
    deleteConfirmationPending,
    pendingArchive,
    setPendingArchive,
    selectedDeleteKeys,
    selectionConfirmationPending,
    closeDeleteSelection,
    beginDeleteSelection,
    toggleDeleteSelection,
    requestDeleteKeys,
    confirmDeleteSelection,
    allSelectedArchived,
    selectionBarRef,
    selectionError,
  };
}

export type ConversationSelection = ReturnType<typeof useConversationSelection>;
