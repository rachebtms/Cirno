import { Suspense } from "react";
import { StartupShell } from "@/components/StartupShell";
import type { WorkspaceRoute } from "@/features/workbench/contracts";
import { InboxPage, SettingsView, isSettingsSectionKey } from "./navigation";
import { WorkbenchConversation } from "./WorkbenchConversation";
import type { ShellSurfaceProps } from "./surface-contract";

export function WorkbenchRoute({ route, visible, focused, surface }: {
  route: WorkspaceRoute; visible: boolean; focused: boolean; surface: ShellSurfaceProps;
}) {
  const { workspaceState: state, conversationActions: actions, conversationLifecycle: lifecycle,
    workspaceActions, runtimeActions, inputs } = surface;
  if (route.view === "chat") return <WorkbenchConversation {...{ route, visible, focused, surface }} />;
  return <Suspense fallback={<StartupShell embedded surface={route.view === "automations" ? "automations" : "settings"} />}>
    {route.view === "inbox" ? <InboxPage returnKey={route.activeKey} onBack={actions.onBackToChat}
      onSelect={workspaceActions.onSelectChat} onSettings={() => actions.onOpenSettings("notifications")} /> :
      <SettingsView registerExitGuard={state.registerSettingsExitGuard} themePreference={state.themePreference}
        initialSection={isSettingsSectionKey(route.settingsSection) ? route.settingsSection : "overview"} initialSettings={state.settingsSnapshot} showSidebar={route.view === "settings"}
        onChangeTheme={state.setTheme} onBackToChat={actions.onBackToChat} onModelNameChange={inputs.onModelNameChange}
        onSettingsChange={state.setSettingsSnapshot} skills={state.skills} skillsLoading={state.skillsLoading} skillsError={state.skillsError}
        onStartAutomationChat={lifecycle.onStartAutomationChat} titleOverrides={state.sidebarState.title_overrides} sessions={state.topicSessions}
        onSectionChange={actions.onSettingsSectionChange} onLogout={inputs.onLogout} onRestart={runtimeActions.onRestart} isRestarting={state.isRestarting} />}
  </Suspense>;
}
