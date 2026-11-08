import { routerLabel } from "@/lib/conversation-role";
import type { ConversationDeleteDecision, ConversationDeleteItem } from "@/features/conversations/shared/contracts";

import { displayTitle } from "@/lib/chat-groups";
import type { ChatSummary } from "@/lib/contracts/conversations";
import { useCallback, useRef, useState } from "react";
import type { useWorkspaceState } from "./useWorkspaceState";

export function useNavigationActions({
  workspaceState,
}: {
  workspaceState: ReturnType<typeof useWorkspaceState>;
}) {
  const {
    pendingDelete,
    deleteChat,
    setPendingDelete,
    filePreviewStore,
    draftStore,
    getSessionAutomations,
    t,
    sidebarState,
  } = workspaceState;
  const deletingRef = useRef(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const onConfirmDelete = useCallback(async () => {
    if (!pendingDelete || deletingRef.current) return;
    deletingRef.current = true;
    setDeleteBusy(true);
    setDeleteError(null);
    pendingDelete.onDecision?.(true);
    const items = pendingDelete.items;
    const hasAutomations = (pendingDelete.automations?.length ?? 0) > 0;
    let index = 0;
    try {
      for (;index < items.length;index += 1) {
        const item = items[index];
        const result = await deleteChat(
          item.key,
          hasAutomations ? { deleteAutomations: true } : undefined,
        );
        if (result.blocked_by_automations) {
          setPendingDelete({
            items: items.slice(index),
            automations: result.automations ?? [],
          });
          return;
        }
        filePreviewStore.delete(item.key);
        draftStore.delete(item.key);
      }
      setPendingDelete(null);
    } catch (e) {
      setPendingDelete({ ...pendingDelete, items: items.slice(index) });
      setDeleteError(e instanceof Error ? e.message : String(e));
    } finally {
      deletingRef.current = false;
      setDeleteBusy(false);
    }
  }, [
    pendingDelete,
    deleteChat,
    filePreviewStore,
    draftStore,
  ]);
  const onRequestDeleteMany = useCallback(
    async (items: ConversationDeleteItem[], onDecision?: ConversationDeleteDecision) => {
      if (deletingRef.current) return;
      setDeleteError(null);
      const uniqueItems = Array.from(
        new Map(items.map((item) => [item.key, item])).values(),
      );
      if (uniqueItems.length === 0) return;
      const automationResults = await Promise.allSettled(
        uniqueItems.map((item) => getSessionAutomations(item.key)),
      );
      const automations = automationResults.flatMap((result) =>
        result.status === "fulfilled" ? result.value : [],
      );
      const failures = automationResults.flatMap(result => result.status === "rejected" ? [String(result.reason instanceof Error ? result.reason.message : result.reason)] : []);
      if (failures.length) setDeleteError(failures.join("\n"));
      let decision = onDecision;
      setPendingDelete({
        items: uniqueItems,
        automations,
        onDecision: (confirmed) => {
          const notify = decision;
          decision = undefined;
          notify?.(confirmed);
        },
      });
    },
    [getSessionAutomations],
  );
  const onRequestDelete = useCallback(
    (key: string, label: string, onDecision?: ConversationDeleteDecision) => {
      void onRequestDeleteMany([{ key, label }], onDecision);
    },
    [onRequestDeleteMany],
  );
  const titleForSession = useCallback(
    (session: ChatSummary) =>
      session.role === "router" ? routerLabel([session]) : displayTitle(session, sidebarState.title_overrides, t("chat.newChat")),
    [sidebarState.title_overrides, t],
  );
  return {
    titleForSession,
    onRequestDelete,
    onRequestDeleteMany,
    onConfirmDelete,
    deleteBusy,
    deleteError,
  };
}
