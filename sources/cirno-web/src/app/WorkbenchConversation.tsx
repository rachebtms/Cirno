import { conversationRole } from "@/lib/conversation-role";
import { Suspense } from "react";
import { ThreadVisibilityContext } from "@/hooks/useThreadVisibility";
import { useWorkspaceOpen } from "@/features/workbench/context";
import type { WorkspaceRoute } from "@/features/workbench/contracts";
import { ThreadShell } from "./navigation";
import type { ShellSurfaceProps } from "./surface-contract";
import { conversationScope } from "./conversation-scope";
import { deriveTemporaryChatTitle } from "@/lib/temporary-chat";
import { normalizeWorkspaceScope } from "./workspace-layout";

/** A chat tab owns its stream and composer, independently of the focused route. */
export function WorkbenchConversation({ route, visible, focused, surface }: {
  route: WorkspaceRoute; visible: boolean; focused: boolean; surface: ShellSurfaceProps;
}) {
  const { workspaceState: state, conversationLifecycle: lifecycle, workspaceActions: actions,
    conversationActions, navigationActions, runtimeActions } = surface;
  const open = useWorkspaceOpen();
  const session = route.activeKey ? state.sessions.find(item => item.key === route.activeKey) ?? state.temporarySessions[route.activeKey] ?? null : null;
  const temporary = !!route.temporary || !!(route.activeKey && state.temporarySessions[route.activeKey]) || (!session && focused && state.temporaryChatEnabled);
  const scope = conversationScope({ session, temporary, defaultScope: state.workspaces?.default_scope,
    draftScope: state.draftWorkspaceScope, overrides: state.workspaceOverrides });
  const running = !!session && state.runningChatIds.has(session.chatId);
  return <ThreadVisibilityContext.Provider value={visible}><Suspense fallback={null}>
    <ThreadShell session={session} sessions={state.sessions} titleOverrides={state.sidebarState.title_overrides}
      title={temporary && session ? deriveTemporaryChatTitle(session.preview, state.t("temporaryChat.title")) : session ? navigationActions.titleForSession(session) : state.t("sidebar.newChat")}
      temporary={temporary} temporaryChatIds={state.temporaryChatIds}
      messageCache={state.threadMessageCache} filePreviewStore={state.filePreviewStore} draftStore={state.draftStore}
      ptcModeEnabled={session?.ptcMode ?? state.ptcModeEnabled} onPtcModeEnabledChange={!session ? state.setPtcModeEnabled : undefined}
      temporaryChatEnabled={state.temporaryChatEnabled} onTemporaryChatEnabledChange={!session ? actions.onTemporaryChatEnabledChange : undefined}
      onToggleSidebar={() => open?.("conversations", { sessionKey: route.activeKey })}
      onCreateChat={state.temporaryChatEnabled ? lifecycle.onCreateTemporaryChat : lifecycle.onCreateChat}
      pendingFirstMessage={state.pendingAutomationMessage} onPendingFirstMessageConsumed={lifecycle.onPendingAutomationMessageConsumed}
      onForkChat={temporary || !conversationRole(session?.key).canFork ? undefined : lifecycle.onForkChat}
      onTurnEnd={focused ? runtimeActions.onTurnEnd : () => void state.refresh()}
      theme={state.theme} onToggleTheme={state.toggle} hideDesktopSidebarToggle headerActive={focused} composerActive={focused}
      workspaceScope={scope} workspaceDefaultScope={state.workspaces?.default_scope ?? null} workspaceControls={state.workspaces?.controls ?? null}
      workspaceScopeDisabled={running} workspaceError={focused ? state.workspaceError : null}
      onWorkspaceScopeChange={next => {
        if (!session) { state.setWorkspaceError(null); state.setDraftWorkspaceScope(normalizeWorkspaceScope(next)); return; }
        if (running) return;
        const normalized = normalizeWorkspaceScope(next);
        state.setWorkspaceError(null);
        state.setWorkspaceOverrides(current => ({ ...current, [session.chatId]: normalized }));
        state.client.setWorkspaceScope(session.chatId, normalized);
      }}
      settingsSnapshot={state.settingsSnapshot} settingsLoading={state.settingsLoading}
      onOpenModelSettings={conversationActions.onOpenModelSettings} skills={state.skills} />
  </Suspense></ThreadVisibilityContext.Provider>;
}
