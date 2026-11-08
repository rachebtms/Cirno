import { deriveTemporaryChatTitle } from "@/lib/temporary-chat";
import { useEffect, useMemo } from "react";
import type { ConversationCatalog } from "@/features/conversations/catalog/context";
import { conversationActivityState } from "@/features/conversations/catalog/activity";
import type { useConversationActions } from "./useConversationActions";
import type { useConversationState } from "./useConversationState";
import type { useNavigationActions } from "./useNavigationActions";
import type { useWorkspaceActions } from "./useWorkspaceActions";
import type { useWorkspaceState } from "./useWorkspaceState";
import type { ShellView } from "./navigation";

const UTILITY_TITLES: Partial<Record<ShellView, string>> = {
  settings: "settings.sidebar.title",
  apps: "settings.nav.apps",
  automations: "settings.nav.automations",
  channels: "settings.nav.channels",
  skills: "settings.nav.skills",
};

/** Compose the current catalog from domain actions without a legacy navigation adapter. */
export function useWorkspacePresentation({
  workspaceState: state, conversationState,
  workspaceActions, navigationActions, conversationActions,
}: {
  workspaceState: ReturnType<typeof useWorkspaceState>;
  conversationState: ReturnType<typeof useConversationState>;
  workspaceActions: ReturnType<typeof useWorkspaceActions>;
  navigationActions: ReturnType<typeof useNavigationActions>;
  conversationActions: ReturnType<typeof useConversationActions>;
}) {
  const { view, t, i18n, sessions, activeKey, runningChatIds, updatedChatIds, workspaceRouteVisible } = state;
  const { activeSession, recoveryChatIdList } = conversationState;
  const headerTitle = state.temporaryChatActive
    ? deriveTemporaryChatTitle(activeSession?.preview, t("temporaryChat.title"))
    : activeSession ? navigationActions.titleForSession(activeSession) : t("app.brand");
  useEffect(() => {
    const utility = UTILITY_TITLES[view];
    document.title = view === "inbox" ? t("inbox.title")
      : utility ? t("app.documentTitle.chat", { title: t(utility) })
      : activeSession ? t("app.documentTitle.chat", { title: headerTitle })
      : t("app.documentTitle.base");
  }, [activeSession, headerTitle, i18n.resolvedLanguage, t, view]);
  const activity = useMemo(() => {
    const states = { running: runningChatIds, updated: updatedChatIds, recovery: new Set(recoveryChatIdList) };
    return Object.fromEntries(sessions.map(session => [session.key, conversationActivityState(
      session.chatId, workspaceRouteVisible && view === "chat" && session.key === activeKey, states,
    )]));
  }, [sessions, runningChatIds, updatedChatIds, recoveryChatIdList, workspaceRouteVisible, view, activeKey]);

  const catalog: ConversationCatalog = {
    owner: state.client,
    sessions, projects: state.projects,
    loading: state.loading || state.sidebarStateLoading || state.projectCatalog.loading,
    error: state.projectError || state.conversationPreferencesError || state.workspaceError || state.sessionsError,
    preferencesError: state.conversationPreferencesError,
    projectError: state.projectError,
    assigning: state.projectCatalog.assigning,
    retryPreferences: state.retryConversationPreferences,
    preferences: state.sidebarState, activity,
    open: workspaceActions.onSelectChat,
    create: project => project ? workspaceActions.onNewChatInProject(project.id, project.name) : workspaceActions.onNewChat(),
    saveProject: state.projectCatalog.save,
    deleteProject: state.projectCatalog.remove,
    assign: (key, id) => void state.projectCatalog.assign(key, id),
    retryProjects: state.projectCatalog.retry,
    showArchived: state.sidebarState.view.show_archived,
    toggleArchived: conversationActions.onToggleArchived,
    rename: state.onRequestRename,
    togglePin: workspaceActions.onTogglePin,
    toggleArchive: conversationActions.onToggleArchive,
    deleteConversation: navigationActions.onRequestDelete,
    deleteMany: navigationActions.onRequestDeleteMany,
    archiveMany: conversationActions.onArchiveMany,
    setSort: sort => { void state.updateSidebarState(current => ({ ...current, view: { ...current.view, sort } })); },
  };
  return { catalog, headerTitle, inboxUnread: Object.values(state.inboxSnapshot.unread).reduce((sum, count) => sum + count, 0) };
}
