import type { SendAttachment, SendOptions } from "@/hooks/useCirnoStream";
import { displayTitle } from "@/lib/chat-groups";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import { createTemporaryChatSession } from "@/lib/temporary-chat";
import { scopeWithAccessMode } from "@/lib/workspace";
import { useCallback, useEffect } from "react";
import type { useConversationProjection } from "./useConversationProjection";
import type { useConversationState } from "./useConversationState";
import type { useWorkspaceState } from "./useWorkspaceState";
import { normalizeWorkspaceScope } from "./workspace-layout";

export function useConversationLifecycle({
  workspaceState,
  conversationState,
  conversationProjection,
}: {
  workspaceState: ReturnType<typeof useWorkspaceState>;
  conversationState: ReturnType<typeof useConversationState>;
  conversationProjection: ReturnType<typeof useConversationProjection>;
}) {
  const {
    client,
    activeChatIdRef,
    setWorkspaceError,
    t,
    loading,
    sessions,
    temporaryChatActive,
    setTemporarySessions,
    activeKey,
    setDraftWorkspaceScope,
    createChat,
    draftProjectId,
    ptcModeEnabled,
    pendingCreatedSessionKeyRef,
    setWorkspaceOverrides,
    assignProject,
    setPendingAutomationMessage,
    setTemporaryChatEnabled,
    setSessionSearchOpen,
    sidebarState,
    forkChat,
  } = workspaceState;
  const {
    refreshWorkspaces,
    activeChatId,
    activeChatRunning,
    activeWorkspaceScope,
  } = conversationState;
  const { navigate } = conversationProjection;
  useEffect(() => {
    return client.onError((error) => {
      if (error.kind !== "workspace_scope_rejected") return;
      if (error.chatId && error.chatId !== activeChatIdRef.current) return;
      setWorkspaceError(t("errors.workspaceScopeRejected.body"));
      void refreshWorkspaces();
    });
  }, [client, refreshWorkspaces, t]);
  useEffect(() => {
    if (loading) return;
    const activeRunIds = sessions
      .filter((session) => typeof session.runStartedAt === "number")
      .map((session) => session.chatId);
    if (activeRunIds.length === 0) return;

    for (const chatId of activeRunIds) {
      client.attach(chatId);
    }
  }, [client, loading, sessions]);
  const applyWorkspaceScope = useCallback(
    (scope: WorkspaceScopePayload) => {
      const next = normalizeWorkspaceScope(scope);
      setWorkspaceError(null);
      if (activeChatId) {
        if (temporaryChatActive) {
          setTemporarySessions((current) => {
            if (!activeKey || !current[activeKey]) return current;
            return {
              ...current,
              [activeKey]: { ...current[activeKey], workspaceScope: next },
            };
          });
        } else if (!activeChatRunning) {
          client.setWorkspaceScope(activeChatId, next);
        }
        return;
      }
      setDraftWorkspaceScope(next);
    },
    [activeChatId, activeChatRunning, activeKey, client, temporaryChatActive],
  );
  const onCreateChat = useCallback(
    async (
      workspaceScope?: WorkspaceScopePayload | null,
      _initialMessage?: string,
      modelPreset?: string | null,
    ) => {
      try {
        const scope = workspaceScope ?? activeWorkspaceScope;
        const chatId = await createChat(
          scope,
          modelPreset,
          draftProjectId,
          ptcModeEnabled,
        );
        const key = `websocket:${chatId}`;
        pendingCreatedSessionKeyRef.current = key;
        navigate({
          view: "chat",
          activeKey: key,
          settingsSection: "overview",
        });
        if (scope) {
          setWorkspaceOverrides((current) => ({
            ...current,
            [chatId]: normalizeWorkspaceScope(scope),
          }));
        }
        return chatId;
      } catch (e) {
        if (
          e instanceof Error &&
          e.message.startsWith("workspace_scope_rejected:")
        ) {
          setWorkspaceError(t("errors.workspaceScopeRejected.body"));
        } else setWorkspaceError(e instanceof Error ? e.message : String(e));
        return null;
      }
    },
    [
      activeWorkspaceScope,
      createChat,
      navigate,
      t,
      draftProjectId,
      assignProject,
      ptcModeEnabled,
    ],
  );
  const onStartAutomationChat = useCallback(
    async (
      content: string,
      images?: SendAttachment[],
      options?: SendOptions,
      modelPreset?: string | null,
    ) => {
      const chatId = await onCreateChat(
        options?.workspaceScope ?? activeWorkspaceScope,
        content,
        modelPreset,
      );
      if (!chatId) return false;
      setPendingAutomationMessage({
        id: crypto.randomUUID(),
        chatId,
        content,
        images,
        options,
      });
      return true;
    },
    [activeWorkspaceScope, onCreateChat],
  );
  const onPendingAutomationMessageConsumed = useCallback((id: string) => {
    setPendingAutomationMessage((current) =>
      current?.id === id ? null : current,
    );
  }, []);
  const onCreateTemporaryChat = useCallback(
    async (
      workspaceScope?: WorkspaceScopePayload | null,
      initialMessage?: string,
      modelPreset?: string | null,
    ) => {
      try {
        const chatId = await client.newTemporaryChat(5_000, ptcModeEnabled);
        const session = createTemporaryChatSession(chatId);
        const restrictedScope = workspaceScope
          ? normalizeWorkspaceScope(
            scopeWithAccessMode(workspaceScope, "restricted"),
          )
          : null;
        const nextSession: ChatSummary = {
          ...session,
          ptcMode: ptcModeEnabled,
          preview: initialMessage ?? "",
          modelPreset: modelPreset ?? null,
          ...(restrictedScope ? { workspaceScope: restrictedScope } : {}),
        };
        pendingCreatedSessionKeyRef.current = nextSession.key;
        setTemporarySessions((current) => ({
          ...current,
          [nextSession.key]: nextSession,
        }));
        setTemporaryChatEnabled(false);
        setWorkspaceError(null);
        setSessionSearchOpen(false);
        navigate({
          view: "chat",
          activeKey: nextSession.key,
          settingsSection: "overview",
          temporary: true,
        });
        return nextSession.chatId;
      } catch (error) {
        setWorkspaceError(error instanceof Error ? error.message : String(error));
        return null;
      }
    },
    [client, navigate, ptcModeEnabled],
  );
  const onForkChat = useCallback(
    async (sourceChatId: string, beforeUserIndex: number) => {
      try {
        const sourceSession = sessions.find(
          (session) => session.chatId === sourceChatId,
        );
        const sourceTitle = sourceSession
          ? displayTitle(
            sourceSession,
            sidebarState.title_overrides,
            t("chat.newChat"),
          )
          : t("chat.newChat");
        const chatId = await forkChat(
          sourceChatId,
          beforeUserIndex,
          t("chat.forkTitle", { title: sourceTitle }),
        );
        navigate({
          view: "chat",
          activeKey: `websocket:${chatId}`,
          settingsSection: "overview",
        });
        return chatId;
      } catch (e) {
        setWorkspaceError(e instanceof Error ? e.message : String(e));
        return null;
      }
    },
    [forkChat, navigate, sessions, sidebarState.title_overrides, t],
  );
  return {
    onCreateTemporaryChat,
    onCreateChat,
    onPendingAutomationMessageConsumed,
    onForkChat,
    applyWorkspaceScope,
    onStartAutomationChat,
  };
}
