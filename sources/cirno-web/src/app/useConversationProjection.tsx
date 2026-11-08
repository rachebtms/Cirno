import { fetchSettings } from "@/lib/api";
import { useCallback, useEffect } from "react";
import { writeShellRoute } from "./route-history";
import {
  ShellRoute,
  changesSettingsSurface,
  readShellRoute,
} from "./navigation";
import type { useWorkspaceState } from "./useWorkspaceState";
import { writeSessionUpdateChatIds } from "./workspace-layout";

export function useConversationProjection({
  workspaceState,
}: {
  workspaceState: ReturnType<typeof useWorkspaceState>;
}) {
  const {
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
  } = workspaceState;
  useEffect(() => {
    const retained = new Set(temporaryChatIds);
    for (const chatId of retainedTemporaryChatIdsRef.current) {
      if (!retained.has(chatId)) {
        threadMessageCache.delete(chatId);
        filePreviewStore.delete(`websocket:${chatId}`);
        draftStore.delete(`websocket:${chatId}`);
      }
    }
    retainedTemporaryChatIdsRef.current = retained;
  }, [temporaryChatIds, threadMessageCache, filePreviewStore, draftStore]);
  const commitNavigation = useCallback(
    (route: ShellRoute, options?: { replace?: boolean; activate?: boolean }) => {
      const tabId =
        route.tabId ??
        (route.view === currentShellRouteRef.current.view
          ? currentShellRouteRef.current.tabId
          : undefined);
      setWorkspaceRouteTabId(tabId);
      if (options?.activate !== false) setNavigationSequence((value) => value + 1);
      setActiveKey(route.activeKey);
      setView(route.view);
      setSettingsInitialSection(route.settingsSection);
      writeShellRoute(
        {
          ...route,
          tabId,
          temporary:
            route.temporary ||
            Boolean(
              route.activeKey && temporarySessionsRef.current[route.activeKey],
            ),
        },
        options?.replace,
      );
    },
    [],
  );
  const navigate = useCallback(
    (route: ShellRoute, options?: { replace?: boolean; activate?: boolean }) => {
      const leave = () => commitNavigation(route, options);
      const current = currentShellRouteRef.current;
      if (
        changesSettingsSurface(current, route) &&
        settingsExitGuardRef.current
      ) {
        settingsExitGuardRef.current(leave, {
          promptRestart: current.view !== route.view,
        });
      } else leave();
    },
    [commitNavigation],
  );
  useEffect(() => {
    const applyRoute = () => {
      const route = readShellRoute();
      const current = currentShellRouteRef.current;
      if (
        changesSettingsSurface(current, route) &&
        settingsExitGuardRef.current
      ) {
        writeShellRoute(current, true);
        settingsExitGuardRef.current(
          () => {
            setWorkspaceRouteTabId(route.tabId);
            setNavigationSequence((value) => value + 1);
            setActiveKey(route.activeKey);
            setView(route.view);
            setSettingsInitialSection(route.settingsSection);
            writeShellRoute(route, true);
            setWorkspaceError(null);
            if (route.view === "chat" && !route.activeKey)
              setDraftWorkspaceScope(null);
          },
          { promptRestart: current.view !== route.view },
        );
        return;
      }
      setWorkspaceRouteTabId(route.tabId);
      setNavigationSequence((value) => value + 1);
      setActiveKey(route.activeKey);
      setView(route.view);
      setSettingsInitialSection(route.settingsSection);
      setWorkspaceError(null);
      if (route.view === "chat" && !route.activeKey) {
        setDraftWorkspaceScope(null);
      }
    };
    window.addEventListener("hashchange", applyRoute);
    window.addEventListener("popstate", applyRoute);
    return () => {
      window.removeEventListener("hashchange", applyRoute);
      window.removeEventListener("popstate", applyRoute);
    };
  }, []);
  useEffect(() => {
    temporarySessionsRef.current = temporarySessions;
  }, [temporarySessions]);
  useEffect(() => {
    if (view === "chat" && !activeKey) return;
    setTemporaryChatEnabled(false);
  }, [activeKey, view]);
  useEffect(
    () => () => {
      for (const session of Object.values(temporarySessionsRef.current)) {
        client.discardTemporaryChat(session.chatId);
      }
    },
    [client],
  );
  useEffect(() => {
    let cancelled = false;
    const requestGeneration = settingsRefreshGenerationRef.current;
    setSettingsLoading(true);
    fetchSettings(getToken())
      .then((payload) => {
        if (
          !cancelled &&
          requestGeneration === settingsRefreshGenerationRef.current
        ) {
          setSettingsSnapshot(payload);
        }
      })
      .catch(() => {
        if (
          !cancelled &&
          requestGeneration === settingsRefreshGenerationRef.current
        ) {
          setSettingsSnapshot(null);
        }
      })
      .finally(() => {
        if (!cancelled) setSettingsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [getToken]);
  useEffect(() => {
    writeSessionUpdateChatIds(updatedChatIds);
  }, [updatedChatIds]);
  return { navigate, commitNavigation };
}
