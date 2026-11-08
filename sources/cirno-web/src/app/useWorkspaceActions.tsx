import { projectNameFromPath } from "@/lib/workspace";
import { useCallback } from "react";
import { defaultShellRoute } from "./navigation";
import type { useConversationProjection } from "./useConversationProjection";
import type { useConversationState } from "./useConversationState";
import type { useWorkspaceState } from "./useWorkspaceState";
import { normalizeWorkspaceScope } from "./workspace-layout";

export function useWorkspaceActions({
  conversationProjection,
  workspaceState,
  conversationState,
}: {
  conversationProjection: ReturnType<typeof useConversationProjection>;
  workspaceState: ReturnType<typeof useWorkspaceState>;
  conversationState: ReturnType<typeof useConversationState>;
}) {
  const { navigate } = conversationProjection;
  const {
    setTemporaryChatEnabled,
    setDraftWorkspaceScope,
    setDraftProjectId,
    setWorkspaceError,
    setSessionSearchOpen,
    view,
    activeKey,
    workspaces,
    projects,
    temporarySessionsRef,
    sessions,
    setUpdatedChatIds,
    temporarySessionList,
    setTemporarySessions,
    client,
    updateSidebarState,
  } = workspaceState;
  const { activeWorkspaceScope } = conversationState;
  const onNewChat = useCallback(() => {
    navigate(defaultShellRoute());
    setTemporaryChatEnabled(false);
    setDraftWorkspaceScope(null);
    setDraftProjectId(null);
    setWorkspaceError(null);
    setSessionSearchOpen(false);
  }, [navigate]);
  const onTemporaryChatEnabledChange = useCallback(
    (enabled: boolean) => {
      if (view !== "chat" || activeKey) return;
      setTemporaryChatEnabled(enabled);
      setDraftWorkspaceScope(null);
      setWorkspaceError(null);
    },
    [activeKey, view],
  );
  const onNewChatInProject = useCallback(
    (projectPath: string, projectName: string) => {
      const base = workspaces?.default_scope ?? activeWorkspaceScope;
      const project = projects.find((item) => item.id === projectPath);
      setDraftProjectId(project?.id ?? null);
      const trimmed =
        project?.working_directory?.trim() || base?.project_path || "";
      if (!base || !trimmed) {
        onNewChat();
        setDraftProjectId(project?.id ?? null);
        return;
      }
      setTemporaryChatEnabled(false);
      navigate(defaultShellRoute());
      setDraftWorkspaceScope(
        normalizeWorkspaceScope({
          project_path: trimmed,
          project_name: projectName || projectNameFromPath(trimmed),
          access_mode: base.access_mode,
          restrict_to_workspace: base.access_mode !== "full",
        }),
      );
      setWorkspaceError(null);
    },
    [
      activeWorkspaceScope,
      navigate,
      onNewChat,
      workspaces?.default_scope,
      projects,
    ],
  );
  const onSelectChat = useCallback(
    (key: string) => {
      const selectedTemporary = temporarySessionsRef.current[key];
      const selected =
        selectedTemporary ?? sessions.find((session) => session.key === key);
      if (!selected) return;
      const selectedChatId = selected.chatId;
      if (selectedChatId) {
        setUpdatedChatIds((current) => {
          if (!current.has(selectedChatId)) return current;
          const next = new Set(current);
          next.delete(selectedChatId);
          return next;
        });
      }
      setWorkspaceError(null);
      navigate({
        view: "chat",
        activeKey: key,
        settingsSection: "overview",
        ...(selectedTemporary ? { temporary: true } : {}),
      });
    },
    [navigate, sessions],
  );
  const onCloseTemporaryChat = useCallback(
    (key: string, options?: { navigate?: boolean }) => {
      const session = temporarySessionsRef.current[key];
      if (!session) return;
      const remaining = temporarySessionList.filter((item) => item.key !== key);
      const nextSessions = Object.fromEntries(
        remaining.map((item) => [item.key, item]),
      );
      temporarySessionsRef.current = nextSessions;
      setTemporarySessions(nextSessions);
      client.discardTemporaryChat(session.chatId);
      if (activeKey === key) {
        if (remaining.length === 0) setDraftWorkspaceScope(null);
        setWorkspaceError(null);
        if (options?.navigate !== false) navigate(
          {
            view: "chat",
            activeKey: remaining[0]?.key ?? null,
            settingsSection: "overview",
            ...(remaining[0] ? { temporary: true } : {}),
          },
          { replace: true },
        );
      }
    },
    [activeKey, client, navigate, temporarySessionList],
  );
  const onTogglePin = useCallback(
    (key: string) => {
      void updateSidebarState((current) => {
        const pinned = new Set(current.pinned_keys);
        if (pinned.has(key)) {
          pinned.delete(key);
        } else {
          pinned.add(key);
        }
        return {
          ...current,
          pinned_keys: Array.from(pinned),
        };
      });
    },
    [updateSidebarState],
  );
  return {
    onSelectChat,
    onNewChat,
    onCloseTemporaryChat,
    onTogglePin,
    onNewChatInProject,
    onTemporaryChatEnabledChange,
  };
}
