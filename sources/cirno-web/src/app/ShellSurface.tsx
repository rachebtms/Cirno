import { Button } from "@/components/ui/button";
import { Workbench } from "@/features/workbench/Workbench";
import { ThemeProvider } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";
import { Suspense, useMemo } from "react";
import { WorkbenchRoute } from "./WorkbenchRoute";
import {
  SessionSearchDialog,
  ShellRoute,
} from "./navigation";
import type { ShellSurfaceProps } from "./surface-contract";
import { WorkspaceDialogs } from "./WorkspaceDialogs";
import { ConversationCatalogContext } from "@/features/conversations/catalog/context";

export function ShellSurface(surface: ShellSurfaceProps) {
  const {
  workspaceState,
  workspacePresentation,
  conversationActions,
  conversationState,
  conversationProjection,
  workspaceActions,
  navigationActions,
} = surface;
  const {
    theme,
    view,
    sessionSearchOpen,
    setSessionSearchOpen,
    topicSessions,
    activeKey,
    loading,
    sidebarState,
    threadMessageCache,
    client,
    settingsInitialSection,
    temporaryChatRequested,
    workspaceRouteTabId,
    navigationSequence,
    runningChatIds,
    sessions,
    temporarySessions,
    setWorkspaceRouteVisible,
    settingsExitGuardRef,
  } = workspaceState;
  const { catalog, inboxUnread, headerTitle } = workspacePresentation;
  const { onSelectSearchResult } = conversationActions;
  const { activeWorkspaceScope } = conversationState;
  const { navigate } = conversationProjection;
  const { onNewChat } = workspaceActions;
  const tabSessions = useMemo(
    () =>
      [...sessions, ...Object.values(temporarySessions)].map((session) =>
        sidebarState.title_overrides[session.key]
          ? { ...session, title: sidebarState.title_overrides[session.key] }
          : session,
      ),
    [sessions, temporarySessions, sidebarState.title_overrides],
  );
  return (
    <ThemeProvider theme={theme}>
      <div className={cn("relative h-full w-full overflow-hidden")}>
        <div className={cn("relative flex h-full w-full overflow-hidden")}>
          {sessionSearchOpen ? (
            <Suspense fallback={null}>
              <SessionSearchDialog
                open
                onOpenChange={setSessionSearchOpen}
                sessions={topicSessions}
                activeKey={activeKey}
                loading={loading}
                titleOverrides={sidebarState.title_overrides}
                messageCache={threadMessageCache}
                onSelect={onSelectSearchResult}
              />
            </Suspense>
          ) : null}
          <main
            data-theme-surface
            className={cn(
              "relative flex h-full min-w-0 flex-1 flex-col overflow-hidden bg-background",
            )}
          >
            <ConversationCatalogContext.Provider value={catalog}>
              {conversationState.workspaceDirectoryError && (
                <div
                  role="alert"
                  className="flex shrink-0 items-center gap-3 border-b border-border px-3 py-2 text-sm text-destructive"
                >
                  <p className="min-w-0 flex-1 break-words">
                    {workspaceState.t("workspace.directoryRefreshError")}:{" "}
                    {conversationState.workspaceDirectoryError}
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={conversationState.workspaceDirectoriesLoading}
                    onClick={() => void conversationState.refreshWorkspaces()}
                  >
                    {workspaceState.t("common.retry")}
                  </Button>
                </div>
              )}
              <div className="min-h-0 flex-1">
                <Workbench
                  client={client}
                  route={{
                    view,
                    activeKey,
                    settingsSection: settingsInitialSection,
                    temporary: temporaryChatRequested,
                    tabId: workspaceRouteTabId,
                  }}
                  navigationSequence={navigationSequence}
                  sessionsLoaded={workspaceState.sessionsLoaded}
                  admittedSessionKey={workspaceState.pendingCreatedSessionKeyRef.current}
                  title={headerTitle}
                  inboxUnread={inboxUnread}
                  runningChatIds={runningChatIds}
                  sessions={tabSessions}
                  scope={activeWorkspaceScope}
                  onRoute={(route) => navigate(route as ShellRoute)}
                  onNewChat={onNewChat}
                  onCloseTemporaryChat={(key) =>
                    workspaceActions.onCloseTemporaryChat(key, {
                      navigate: false,
                    })
                  }
                  onRouteVisibleChange={setWorkspaceRouteVisible}
                  beforeActivate={(action) => {
                    if (view !== "chat" && settingsExitGuardRef.current)
                      settingsExitGuardRef.current(action, {
                        promptRestart: false,
                      });
                    else action();
                  }}
                  renderRoute={(route, visible, focused) => <WorkbenchRoute {...{ route, visible, focused, surface }} />}
                />
              </div>
            </ConversationCatalogContext.Provider>
          </main>
        </div>

        <WorkspaceDialogs
          workspaceState={workspaceState}
          navigationActions={navigationActions}
        />
      </div>
    </ThemeProvider>
  );
}
