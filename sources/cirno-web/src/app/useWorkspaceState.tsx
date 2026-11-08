import { useProjects } from "@/features/conversations/projects/useProjects";
import type { ConversationDeleteDecision, ConversationDeleteItem } from "@/features/conversations/shared/contracts";

import type { SettingsExitGuard } from "@/features/settings/contracts";
import type { SettingsSectionKey } from "@/features/settings/SettingsView";
import { connectPreferences } from "@/features/preferences/store";
import type { SendAttachment, SendOptions } from "@/hooks/useCirnoStream";
import { FilePreviewStore } from "@/hooks/useFilePreviewState";
import { useInbox } from "@/features/inbox/model/store";
import { usePageVisibility } from "@/hooks/usePageVisibility";
import { useReconnectRuns } from "@/hooks/useReconnectRuns";
import { useSessions } from "@/hooks/useSessions";
import { useSidebarState } from "@/hooks/useSidebarState";
import { useSkills } from "@/hooks/useSkills";
import { useTheme } from "@/hooks/useTheme";
import { ComposerDraftStore } from "@/lib/composer-draft";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { SettingsPayload } from "@/lib/contracts/settings";
import type { WorkspaceScopePayload, WorkspacesPayload } from "@/lib/contracts/workspaces";
import { ThreadMessageCache } from "@/lib/thread-message-cache";
import { useClient } from "@/providers/ClientProvider";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { writeShellRoute } from "./route-history";
import { ShellRoute, ShellView, readShellRoute } from "./navigation";
import { readSessionUpdateChatIds } from "./workspace-layout";

export function useWorkspaceState() {
  const { t, i18n } = useTranslation();
  const { theme, preference: themePreference, toggle, setTheme } = useTheme();
  const { client, getToken } = useClient();
  useEffect(() => connectPreferences(client), [client]);
  const { snapshot: inboxSnapshot } = useInbox();
  useReconnectRuns(client, getToken);
  const {
    sessions,
    loading,
    initialLoading: sessionsInitialLoading,
    error: sessionsError,
    refresh,
    createChat,
    forkChat,
    deleteChat,
    getSessionAutomations,
  } = useSessions();
  const sessionsLoaded = !loading && sessionsError === null;
  const {
    state: sidebarState,
    loading: sidebarStateLoading,
    update: updateSidebarState,
    rename: onRequestRename,
    error: conversationPreferencesError,
    retry: retryConversationPreferences,
  } = useSidebarState(sessions, sessionsLoaded);
  const initialRouteRef = useRef<ShellRoute | null>(null);
  if (!initialRouteRef.current) initialRouteRef.current = readShellRoute();
  const [activeKey, setActiveKey] = useState<string | null>(
    initialRouteRef.current.activeKey,
  );
  const [view, setView] = useState<ShellView>(initialRouteRef.current.view);
  const [navigationSequence, setNavigationSequence] = useState(0);
  const [workspaceRouteTabId, setWorkspaceRouteTabId] = useState(initialRouteRef.current.tabId);
  const [workspaceRouteVisible, setWorkspaceRouteVisible] = useState(true);
  const [chatVisited, setChatVisited] = useState(
    initialRouteRef.current.view === "chat",
  );
  useEffect(() => {
    if (view === "chat") setChatVisited(true);
  }, [view]);
  useEffect(() => {
    // Normalize legacy links while retaining their return destination in history.
    if (new URLSearchParams(window.location.hash.split("?")[1]).has("chat")) {
      writeShellRoute(initialRouteRef.current!, true);
    }
  }, []);
  const [temporarySessions, setTemporarySessions] = useState<
    Record<string, ChatSummary>
  >({});
  const [temporaryChatEnabled, setTemporaryChatEnabled] = useState(false);
  const [ptcModeEnabled, setPtcModeEnabled] = useState(false);
  const [settingsInitialSection, setSettingsInitialSection] =
    useState<SettingsSectionKey>(initialRouteRef.current.settingsSection);
  const [sessionSearchOpen, setSessionSearchOpen] = useState(false);
  const topicSessions = sessions;
  const [pendingDelete, setPendingDelete] = useState<{
    items: ConversationDeleteItem[];
    automations?: SessionAutomationJob[];
    onDecision?: ConversationDeleteDecision;
  } | null>(null);
  const restartSawDisconnectRef = useRef(false);
  const restartStartedAtRef = useRef(0);
  const [restartToast, setRestartToast] = useState<string | null>(null);
  const [isRestarting, setIsRestarting] = useState(false);
  const [runningChatIds, setRunningChatIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [updatedChatIds, setUpdatedChatIds] = useState<Set<string>>(
    readSessionUpdateChatIds,
  );
  const [workspaces, setWorkspaces] = useState<WorkspacesPayload | null>(null);
  const {
    skills,
    loading: skillsLoading,
    error: skillsError,
  } = useSkills(getToken);
  const pageVisible = usePageVisibility();
  const [settingsSnapshot, setSettingsSnapshot] =
    useState<SettingsPayload | null>(null);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const settingsRefreshGenerationRef = useRef(0);
  const [pendingAutomationMessage, setPendingAutomationMessage] = useState<{
    id: string;
    chatId: string;
    content: string;
    images?: SendAttachment[];
    options?: SendOptions;
  } | null>(null);
  const settingsExitGuardRef = useRef<SettingsExitGuard | null>(null);
  const currentShellRouteRef = useRef<ShellRoute>({
    view,
    activeKey,
    settingsSection: settingsInitialSection,
  });
  currentShellRouteRef.current = {
    tabId: workspaceRouteTabId,
    view,
    activeKey,
    settingsSection: settingsInitialSection,
    temporary: Boolean(activeKey && temporarySessions[activeKey]),
  };
  const registerSettingsExitGuard = useCallback(
    (guard: SettingsExitGuard | null) => {
      settingsExitGuardRef.current = guard;
    },
    [],
  );
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const projectCatalog = useProjects(client, refresh);
  const { projects, error: projectError, assign: assignProject } = projectCatalog;
  const [draftProjectId, setDraftProjectId] = useState<string | null>(null);
  const [draftWorkspaceScope, setDraftWorkspaceScope] =
    useState<WorkspaceScopePayload | null>(null);
  const [workspaceOverrides, setWorkspaceOverrides] = useState<
    Record<string, WorkspaceScopePayload>
  >({});
  const runningChatIdsRef = useRef<Set<string>>(new Set());
  const activeChatIdRef = useRef<string | null>(null);
  const pendingCreatedSessionKeyRef = useRef<string | null>(null);
  const temporarySessionsRef = useRef<Record<string, ChatSummary>>({});
  const activeTemporarySession = activeKey
    ? (temporarySessions[activeKey] ?? null)
    : null;
  const temporaryChatId = activeTemporarySession?.chatId ?? null;
  const temporaryChatActive = temporaryChatId !== null;
  const temporaryChatRequested = temporaryChatActive || temporaryChatEnabled;
  const temporarySessionList = useMemo(
    () =>
      Object.values(temporarySessions).sort(
        (a, b) => Date.parse(b.createdAt ?? "") - Date.parse(a.createdAt ?? ""),
      ),
    [temporarySessions],
  );
  const temporaryChatIds = useMemo(
    () => temporarySessionList.map((session) => session.chatId),
    [temporarySessionList],
  );
  const retainedTemporaryChatIdsRef = useRef(new Set<string>());
  const [draftStore] = useState(() => new ComposerDraftStore());
  const [filePreviewStore] = useState(() => new FilePreviewStore());
  const [threadMessageCache] = useState(
    () =>
      new ThreadMessageCache((key) =>
        retainedTemporaryChatIdsRef.current.has(key),
      ),
  );
  return {
    temporaryChatIds,
    retainedTemporaryChatIdsRef,
    threadMessageCache,
    filePreviewStore,
    draftStore,
    currentShellRouteRef,
    setWorkspaceRouteTabId,
    setNavigationSequence,
    setActiveKey,
    setView,
    setSettingsInitialSection,
    temporarySessionsRef,
    settingsExitGuardRef,
    setWorkspaceError,
    setDraftWorkspaceScope,
    temporarySessions,
    view,
    activeKey,
    setTemporaryChatEnabled,
    client,
    settingsRefreshGenerationRef,
    setSettingsLoading,
    getToken,
    setSettingsSnapshot,
    updatedChatIds,
    pageVisible,
    sessions,
    sessionsError,
    runningChatIds,
    activeChatIdRef,
    setUpdatedChatIds,
    temporaryChatRequested,
    workspaces,
    workspaceOverrides,
    draftWorkspaceScope,
    setWorkspaces,
    sessionsLoaded,
    setWorkspaceOverrides,
    sidebarStateLoading,
    loading,
    pendingCreatedSessionKeyRef,
    t,
    temporaryChatActive,
    setTemporarySessions,
    createChat,
    draftProjectId,
    ptcModeEnabled,
    assignProject,
    setPendingAutomationMessage,
    setSessionSearchOpen,
    sidebarState,
    forkChat,
    setDraftProjectId,
    projects,
    projectCatalog,
    temporarySessionList,
    updateSidebarState,
    topicSessions,
    restartSawDisconnectRef,
    restartStartedAtRef,
    setIsRestarting,
    setRestartToast,
    runningChatIdsRef,
    setRunningChatIds,
    refresh,
    pendingDelete,
    deleteChat,
    setPendingDelete,
    getSessionAutomations,
    i18n,
    sessionsInitialLoading,
    onRequestRename,
    inboxSnapshot,
    theme,
    toggle,
    sessionSearchOpen,
    settingsInitialSection,
    workspaceRouteTabId,
    navigationSequence,
    setWorkspaceRouteVisible,
    chatVisited,
    workspaceRouteVisible,
    setPtcModeEnabled,
    temporaryChatEnabled,
    pendingAutomationMessage,
    workspaceError,
    projectError,
    conversationPreferencesError,
    retryConversationPreferences,
    settingsSnapshot,
    settingsLoading,
    skills,
    registerSettingsExitGuard,
    themePreference,
    setTheme,
    skillsLoading,
    skillsError,
    isRestarting,
    restartToast,
  };
}
