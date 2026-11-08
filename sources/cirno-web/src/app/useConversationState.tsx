import type { ChatSummary } from "@/lib/contracts/conversations";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import { normalizeWorkspaceScope } from "./workspace-layout";
import { conversationScope } from "./conversation-scope";
import { useEffect, useMemo } from "react";
import type { useWorkspaceState } from "./useWorkspaceState";
import { useWorkspaceDirectoryCatalog } from "./useWorkspaceDirectoryCatalog";

export function useConversationState({
  workspaceState,
}: {
  workspaceState: ReturnType<typeof useWorkspaceState>;
}) {
  const {
    pageVisible,
    view,
    workspaceRouteVisible,
    client,
    activeKey,
    temporarySessions,
    sessions,
    runningChatIds,
    updatedChatIds,
    activeChatIdRef,
    setUpdatedChatIds,
    temporaryChatRequested,
    workspaces,
    workspaceOverrides,
    draftWorkspaceScope,
    getToken,
    setWorkspaces,
    sessionsLoaded,
    setWorkspaceOverrides,
    setWorkspaceError,
  } = workspaceState;
  const activeSession = useMemo<ChatSummary | null>(() => {
    if (!activeKey) return null;
    if (temporarySessions[activeKey]) return temporarySessions[activeKey];
    return sessions.find((s) => s.key === activeKey) ?? null;
  }, [sessions, activeKey, temporarySessions]);
  const activePaneSession = activeSession;
  const runningChatIdList = useMemo(
    () => Array.from(runningChatIds),
    [runningChatIds],
  );
  const updatedChatIdList = useMemo(
    () => Array.from(updatedChatIds),
    [updatedChatIds],
  );
  const recoveryChatIdList = useMemo(
    () =>
      sessions
        .filter(
          (session) =>
            session.recoveryState?.status === "awaiting_user" ||
            session.recoveryState?.status === "failed",
        )
        .map((session) => session.chatId),
    [sessions],
  );
  const activeChatId = activePaneSession?.chatId ?? null;
  const viewedChatId =
    view === "chat" && workspaceRouteVisible ? activeChatId : null;
  useEffect(() => {
    activeChatIdRef.current = viewedChatId;
    if (!viewedChatId) return;
    setUpdatedChatIds((current) => {
      if (!current.has(viewedChatId)) return current;
      const next = new Set(current);
      next.delete(viewedChatId);
      return next;
    });
  }, [viewedChatId]);
  const activeWorkspaceScope = useMemo<WorkspaceScopePayload | null>(() => conversationScope({
    session: activePaneSession, temporary: temporaryChatRequested,
    defaultScope: workspaces?.default_scope, draftScope: draftWorkspaceScope, overrides: workspaceOverrides,
  }), [
    activeChatId,
    activePaneSession?.workspaceScope,
    draftWorkspaceScope,
    temporaryChatRequested,
    workspaceOverrides,
    workspaces?.default_scope,
  ]);
  const activeChatRunning = activeChatId
    ? runningChatIds.has(activeChatId)
    : false;
  const {
    refresh: refreshWorkspaces,
    error: workspaceDirectoryError,
    pending: workspaceDirectoriesLoading,
  } = useWorkspaceDirectoryCatalog(getToken, setWorkspaces);
  useEffect(() => {
    if (pageVisible) void refreshWorkspaces();
    return client.onReady(() => {
      void refreshWorkspaces();
    });
  }, [client, pageVisible, refreshWorkspaces]);
  useEffect(() => {
    if (!sessionsLoaded) return;
    const knownChatIds = new Set(sessions.map((session) => session.chatId));
    setUpdatedChatIds((current) => {
      const next = new Set(
        Array.from(current).filter((chatId) => knownChatIds.has(chatId)),
      );
      return next.size === current.size ? current : next;
    });
    setWorkspaceOverrides((current) => {
      const entries = Object.entries(current).filter(([chatId]) =>
        knownChatIds.has(chatId),
      );
      return entries.length === Object.keys(current).length
        ? current
        : Object.fromEntries(entries);
    });
  }, [sessionsLoaded, sessions]);
  useEffect(() => {
    return client.onSessionUpdate((chatId, scope, workspaceScope) => {
      if (scope === "thread") {
        setUpdatedChatIds((current) => {
          const next = new Set(current);
          if (activeChatIdRef.current === chatId) {
            next.delete(chatId);
          } else {
            next.add(chatId);
          }
          return next.size === current.size &&
            next.has(chatId) === current.has(chatId)
            ? current
            : next;
        });
      }
      if (!workspaceScope) return;
      const next = normalizeWorkspaceScope(workspaceScope);
      setWorkspaceOverrides((current) => ({
        ...current,
        [chatId]: next,
      }));
      if (activeChatIdRef.current === chatId) setWorkspaceError(null);
      void refreshWorkspaces();
    });
  }, [client, refreshWorkspaces]);
  return {
    refreshWorkspaces,
    workspaceDirectoryError,
    workspaceDirectoriesLoading,
    activeChatId,
    activeChatRunning,
    activeWorkspaceScope,
    activeSession,
    activePaneSession,
    runningChatIdList,
    updatedChatIdList,
    recoveryChatIdList,
  };
}
