import type { SettingsSectionKey } from "@/features/settings/SettingsView";
import { matchAppShortcut } from "@/lib/app-shortcuts";
import { useCallback, useEffect } from "react";
import { ShellRoute } from "./navigation";
import type { useConversationProjection } from "./useConversationProjection";
import type { useWorkspaceActions } from "./useWorkspaceActions";
import type { useWorkspaceState } from "./useWorkspaceState";

export function useConversationActions({
  workspaceState,
  conversationProjection,
  workspaceActions,
}: {
  workspaceState: ReturnType<typeof useWorkspaceState>;
  conversationProjection: ReturnType<typeof useConversationProjection>;
  workspaceActions: ReturnType<typeof useWorkspaceActions>;
}) {
  const {
    updateSidebarState,
    workspaceRouteVisible,
    activeKey,
    sidebarState,
    topicSessions,
    setSessionSearchOpen,
    temporarySessionsRef,
    currentShellRouteRef,
  } = workspaceState;
  const { navigate, commitNavigation } = conversationProjection;
  const { onSelectChat, onNewChat } = workspaceActions;
  const onArchiveMany = useCallback(
    (keys: string[], archive: boolean) => {
      const selected = new Set(keys);
      void updateSidebarState((current) => {
        const archived = new Set(current.archived_keys);
        for (const key of selected) {
          if (archive) archived.add(key);
          else archived.delete(key);
        }
        return {
          ...current,
          pinned_keys: current.pinned_keys.filter((key) => !selected.has(key)),
          archived_keys: Array.from(archived),
        };
      });
      if (archive && workspaceRouteVisible && activeKey && selected.has(activeKey)) {
        const archived = new Set([...sidebarState.archived_keys, ...selected]);
        const next = topicSessions.find(
          (session) => !archived.has(session.key),
        );
        navigate({
          view: "chat",
          activeKey: next?.key ?? null,
          settingsSection: "overview",
        });
      }
    },
    [
      activeKey,
      navigate,
      sidebarState.archived_keys,
      topicSessions,
      updateSidebarState,
      workspaceRouteVisible,
    ],
  );
  const onToggleArchive = useCallback(
    (key: string) => {
      onArchiveMany([key], !sidebarState.archived_keys.includes(key));
    },
    [onArchiveMany, sidebarState.archived_keys],
  );
  const onToggleArchived = useCallback(() => {
    void updateSidebarState((current) => ({
      ...current,
      view: {
        ...current.view,
        show_archived: !current.view.show_archived,
      },
    }));
  }, [updateSidebarState]);
  const onOpenSessionSearch = useCallback(() => {
    setSessionSearchOpen(true);
  }, []);
  const onSelectSearchResult = useCallback(
    (key: string) => {
      setSessionSearchOpen(false);
      onSelectChat(key);
    },
    [onSelectChat],
  );
  const onOpenSettings = useCallback(
    (section: SettingsSectionKey = "overview") => {
      setSessionSearchOpen(false);
      navigate({ view: "settings", activeKey, settingsSection: section });
    },
    [activeKey, navigate],
  );
  const onOpenModelSettings = useCallback(() => {
    onOpenSettings("models");
  }, [onOpenSettings]);
  const onOpenApps = useCallback(() => {
    setSessionSearchOpen(false);
    navigate({ view: "apps", activeKey, settingsSection: "apps" });
  }, [activeKey, navigate]);
  const onOpenAutomations = useCallback(() => {
    setSessionSearchOpen(false);
    navigate({
      view: "automations",
      activeKey,
      settingsSection: "automations",
    });
  }, [activeKey, navigate]);
  const onOpenChannels = useCallback(() => {
    setSessionSearchOpen(false);
    navigate({ view: "channels", activeKey, settingsSection: "channels" });
  }, [activeKey, navigate]);
  const onOpenSkills = useCallback(() => {
    setSessionSearchOpen(false);
    navigate({ view: "skills", activeKey, settingsSection: "skills" });
  }, [activeKey, navigate]);
  useEffect(() => {
    const actions = {
      newChat: onNewChat,
      search: onOpenSessionSearch,
      apps: onOpenApps,
      skills: onOpenSkills,
      automations: onOpenAutomations,
      channels: onOpenChannels,
      settings: () => onOpenSettings(),
    };
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      const action = matchAppShortcut(event);
      if (!action) return;
      event.preventDefault();
      actions[action]();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    onNewChat,
    onOpenSessionSearch,
    onOpenApps,
    onOpenSkills,
    onOpenAutomations,
    onOpenChannels,
    onOpenSettings,
  ]);
  const onSettingsSectionChange = useCallback(
    (section: SettingsSectionKey) => {
      const route: ShellRoute = {
        view: "settings",
        activeKey,
        settingsSection: section,
      };
      // The page has completed or retained its outgoing drafts for in-page transitions.
      if (currentShellRouteRef.current.view === route.view)
        commitNavigation(route);
      else navigate(route);
    },
    [activeKey, commitNavigation, navigate],
  );
  const returnChatRoute = useCallback((): ShellRoute => {
    const nextKey =
      activeKey &&
        (temporarySessionsRef.current[activeKey] ||
          topicSessions.some((session) => session.key === activeKey))
        ? activeKey
        : null;
    return {
      view: "chat",
      activeKey: nextKey,
      temporary: Boolean(nextKey && temporarySessionsRef.current[nextKey]),
      settingsSection: "overview",
    };
  }, [activeKey, topicSessions]);
  const onBackToChat = useCallback(() => {
    navigate(returnChatRoute());
  }, [navigate, returnChatRoute]);
  return {
    onToggleArchive,
    onArchiveMany,
    onOpenSettings,
    onOpenApps,
    onOpenAutomations,
    onOpenChannels,
    onOpenSkills,
    onOpenSessionSearch,
    onToggleArchived,
    onSelectSearchResult,
    onOpenModelSettings,
    onBackToChat,
    onSettingsSectionChange,
  };
}
