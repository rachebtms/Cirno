import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  type RefObject,
} from "react";
import { useTranslation } from "react-i18next";
import { useResourceScope } from "@/ui/resources/useResourceScope";
import { useScopedState } from "@/ui/resources/useScopedState";
import type {
  ConversationDeleteActions,
  ConversationDeleteDecision,
  ConversationDeleteItem,
} from "./contracts";
import { selectionRange } from "./selection";

interface SelectionInputs extends ConversationDeleteActions {
  owner: object;
  deleteItemsByKey: ReadonlyMap<string, ConversationDeleteItem>;
  selectableDeleteKeys: string[];
  archived: ReadonlySet<string>;
  archivedPanes: ReadonlySet<string>;
  scrollViewportRef: RefObject<HTMLElement | null>;
}

interface SelectionState {
  selectionError: string;
  deleteSelectionMode: boolean;
  deleteConfirmationPending: boolean;
  pendingArchive: { keys: string[]; archive: boolean } | null;
  selectedDeleteKeys: Set<string>;
}

function emptySelection(): SelectionState {
  return {
    selectionError: "",
    deleteSelectionMode: false,
    deleteConfirmationPending: false,
    pendingArchive: null,
    selectedDeleteKeys: new Set(),
  };
}

export function useConversationSelection({
  owner,
  deleteItemsByKey,
  selectableDeleteKeys,
  archived,
  archivedPanes,
  scrollViewportRef,
  onRequestDelete,
  onRequestDeleteMany,
}: SelectionInputs) {
  const { t } = useTranslation();
  const scope = useResourceScope(owner);
  const { isCurrent } = scope;
  const [selection, setSelection] = useScopedState(scope, emptySelection);
  const { selectionError, deleteSelectionMode, deleteConfirmationPending,
    pendingArchive, selectedDeleteKeys } = selection;
  const selectionBarRef = useRef<HTMLDivElement>(null);
  const deleteSelectionAnchorRef = useMemo<{ current: string | null }>(
    () => ({ current: null }), [scope],
  );
  const selectionConfirmationPending =
    pendingArchive !== null || deleteConfirmationPending;
  useEffect(() => {
    if (!isCurrent()) return;
    setSelection((current) => {
      const retained = new Set(
        [...current.selectedDeleteKeys].filter((key) => deleteItemsByKey.has(key)),
      );
      return retained.size === current.selectedDeleteKeys.size
        ? current : { ...current, selectedDeleteKeys: retained };
    });
    if (
      deleteSelectionAnchorRef.current &&
      !deleteItemsByKey.has(deleteSelectionAnchorRef.current)
    )
      deleteSelectionAnchorRef.current = null;
  }, [deleteItemsByKey, isCurrent, setSelection, deleteSelectionAnchorRef]);
  const closeDeleteSelection = useCallback(() => {
    setSelection((current) => ({ ...emptySelection(),
      deleteConfirmationPending: current.deleteConfirmationPending }));
    deleteSelectionAnchorRef.current = null;
  }, [setSelection, deleteSelectionAnchorRef]);

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
    setSelection((current) => ({ ...current,
      deleteSelectionMode: true, selectedDeleteKeys: new Set(validKeys) }));
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
    setSelection((current) => {
      const next = new Set(current.selectedDeleteKeys);
      if (range) {
        for (const key of range) next.add(key);
        for (const key of validKeys) next.add(key);
        return { ...current, selectedDeleteKeys: next };
      }
      const remove =
        validKeys.length > 0 && validKeys.every((key) => next.has(key));
      for (const key of validKeys) {
        if (remove) next.delete(key);
        else next.add(key);
      }
      return { ...current, selectedDeleteKeys: next };
    });
    if (!range) deleteSelectionAnchorRef.current = targetKey ?? null;
  };
  const requestDeleteItems = (
    items: ConversationDeleteItem[],
    onDecision?: ConversationDeleteDecision,
  ) => {
    if (!isCurrent() || items.length === 0) return false;
    if (items.length > 1 && !onRequestDeleteMany) {
      setSelection((current) => ({ ...current, selectionError:
        t("chat.bulkDeleteUnavailable", {
          defaultValue: "This view can only delete one conversation at a time.",
        }),
      }));
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
    if (!isCurrent() || selectionConfirmationPending) return;
    setSelection((current) => ({ ...current, deleteConfirmationPending: true }));
    const started = requestDeleteKeys(
      Array.from(selectedDeleteKeys),
      (confirmed) => {
        setSelection((current) => ({ ...current, deleteConfirmationPending: false }));
        if (confirmed) closeDeleteSelection();
      },
    );
    if (!started) setSelection((current) => ({ ...current, deleteConfirmationPending: false }));
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
    setPendingArchive: (value: typeof pendingArchive) => {
      setSelection((current) => ({ ...current, pendingArchive: value }));
    },
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
