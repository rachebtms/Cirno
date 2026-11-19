import { routerLabel } from "@/lib/conversation-role";
import type { ConversationDeleteDecision, ConversationDeleteItem } from "@/features/conversations/shared/contracts";

import { displayTitle } from "@/lib/chat-groups";
import type { ChatSummary } from "@/lib/contracts/conversations";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useLifetime } from "@/ui/resources/useLifetime";
import type { useWorkspaceState } from "./useWorkspaceState";

export function useNavigationActions({
  workspaceState,
}: {
  workspaceState: ReturnType<typeof useWorkspaceState>;
}) {
  const {
    client,
    pendingDelete,
    deleteChat,
    setPendingDelete,
    filePreviewStore,
    draftStore,
    getSessionAutomations,
    t,
    sidebarState,
  } = workspaceState;
  const owner = useMemo(() => ({ client, sequence: 0, deleting: false,
    pending: null as typeof pendingDelete, decision: undefined as ConversationDeleteDecision | undefined }), [client]);
  const current = useLifetime(owner);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [stateOwner, setStateOwner] = useState(owner);
  if (stateOwner !== owner) { setStateOwner(owner); setDeleteBusy(false); setDeleteError(null); }
  useEffect(() => {
    setPendingDelete(previous => previous?.owner === client ? previous : null);
    return () => {
      owner.sequence++;
      owner.decision?.(false);
      owner.decision = undefined;
    };
  }, [owner, client, setPendingDelete]);
  const onConfirmDelete = useCallback(async () => {
    if (!current() || !pendingDelete || pendingDelete.owner !== client || owner.pending !== pendingDelete || owner.deleting) return;
    owner.deleting = true;
    setDeleteBusy(true);
    setDeleteError(null);
    const items = pendingDelete.items;
    const hasAutomations = (pendingDelete.automations?.length ?? 0) > 0;
    let index = 0;
    try {
      pendingDelete.onDecision?.(true);
      for (;index < items.length;index += 1) {
        if (!current()) return;
        const item = items[index];
        const result = await deleteChat(item.key, hasAutomations ? { deleteAutomations: true } : undefined);
        if (!current()) return;
        if (result.blocked_by_automations) {
          owner.pending = { owner: client, items: items.slice(index), automations: result.automations ?? [] };
          owner.decision = undefined;
          setPendingDelete(owner.pending);
          return;
        }
        if (!result.deleted) throw new Error(t("deleteConfirm.notConfirmed", {
          defaultValue: "Conversation deletion was not confirmed. Please retry.",
        }));
        filePreviewStore.delete(item.key);
        draftStore.delete(item.key);
      }
      owner.pending = null; owner.decision = undefined;
      setPendingDelete(null);
    } catch (e) {
      if (current()) {
        owner.pending = { ...pendingDelete, items: items.slice(index) };
        setPendingDelete(owner.pending);
        setDeleteError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      owner.deleting = false;
      if (current()) setDeleteBusy(false);
    }
  }, [current, owner, client, pendingDelete, deleteChat, filePreviewStore, draftStore, setPendingDelete, t]);
  const onCancelDelete = useCallback(() => {
    if (!current() || owner.deleting || !pendingDelete || owner.pending !== pendingDelete || pendingDelete.owner !== client) return;
    owner.sequence++;
    owner.pending = null;
    owner.decision?.(false); owner.decision = undefined;
    setPendingDelete(null); setDeleteError(null);
  }, [current, owner, pendingDelete, client, setPendingDelete]);
  const onRequestDeleteMany = useCallback(
    async (items: ConversationDeleteItem[], onDecision?: ConversationDeleteDecision) => {
      let decision = onDecision;
      const notify: ConversationDeleteDecision = confirmed => {
        const callback = decision; decision = undefined; callback?.(confirmed);
      };
      const uniqueItems = Array.from(new Map(items.map(item => [item.key, item])).values());
      if (!current() || owner.deleting || uniqueItems.length === 0) { notify(false); return; }
      const ticket = ++owner.sequence;
      owner.decision?.(false);
      owner.decision = notify; owner.pending = null;
      setPendingDelete(null); setDeleteError(null);
      const automationResults = await Promise.allSettled(uniqueItems.map(item => getSessionAutomations(item.key)));
      if (!current() || ticket !== owner.sequence) { notify(false); return; }
      const automations = automationResults.flatMap(result => result.status === "fulfilled" ? result.value : []);
      const failures = automationResults.flatMap(result => result.status === "rejected" ? [String(result.reason instanceof Error ? result.reason.message : result.reason)] : []);
      if (failures.length) setDeleteError(failures.join("\n"));
      owner.pending = { owner: client, items: uniqueItems, automations, onDecision: notify };
      setPendingDelete(owner.pending);
    }, [current, owner, client, getSessionAutomations, setPendingDelete],
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
    onCancelDelete,
    deleteBusy,
    deleteError,
  };
}
