import { AppsCatalogSettings } from "../apps/AppsCatalogSettings";
import type { SectionRenderer, SectionRenderers } from "./contracts";
import type { SettingsComposition } from "./useSettingsComposition";

export function createAppSections(bindings: SettingsComposition): SectionRenderers {
  const { showSidebar, onBackToChat, systemState, systemActions, activeSection, displayPreferences, configureProxy, restartInProgress, selectSection, pendingRestartSections, runtimeConfiguration, mcpSetupName, setMcpSetupName, restartViaSettingsSurface } = bindings;
  const renderMcp: SectionRenderer = () => {
    return (
      <div className="settings-stack">
        {activeSection === "apps" && showSidebar ? runtimeConfiguration("tools") : null}
        <AppsCatalogSettings
          hideFilters={showSidebar || activeSection === "mcp"}
          onConfigureProxy={configureProxy}
          setupName={mcpSetupName}
          onSetupOpened={() => setMcpSetupName(null)}
          cliApps={systemState.cliApps}
          mcpPresets={systemState.mcpPresets}
          cliAppsLoading={systemState.cliAppsLoading}
          mcpPresetsLoading={systemState.mcpPresetsLoading}
          query={systemState.appsQuery}
          filter={activeSection === "mcp" ? "mcp" : showSidebar ? "cli" : systemState.appsKindFilter}
          cliActionKey={systemState.cliAppsAction}
          mcpActionKey={systemState.mcpPresetAction}
          mcpOAuthFlow={systemState.mcpOAuthFlow}
          mcpOAuthPopupBlocked={systemState.mcpOAuthPopupBlocked}
          mcpOAuthCallbackUrl={systemState.mcpOAuthCallbackUrl}
          mcpOAuthCompleting={systemState.mcpOAuthCompleting}
          mcpOAuthCallbackError={systemState.mcpOAuthCallbackError}
          cliMessage={systemState.cliAppsMessage}
          cliError={systemState.cliAppsError}
          cliFocusName={systemState.cliAppsFocusName}
          mcpMessage={systemState.mcpMessage}
          mcpError={systemState.mcpError}
          mcpFieldValues={systemState.mcpFieldValues}
          customMcpForm={systemState.customMcpForm}
          mcpConfigImport={systemState.mcpConfigImport}
          showBrandLogos={displayPreferences.brandLogos}
          requiresRestartPending={pendingRestartSections.runtime}
          onQueryChange={systemState.setAppsQuery}
          onFilterChange={(kind) => { systemState.setAppsKindFilter(kind); if (kind === "mcp") selectSection("mcp"); else if (activeSection === "mcp") selectSection("apps"); }}
          onCliAction={systemActions.handleCliAppAction}
          onMcpAction={systemActions.handleMcpPresetAction}
          onMcpOAuthConnect={systemActions.handleMcpOAuthConnect}
          onMcpOAuthCancel={() => void systemActions.handleMcpOAuthCancel()}
          onMcpOAuthOpen={systemActions.handleMcpOAuthOpen}
          onMcpOAuthCallbackUrlChange={(value) => {
            systemState.setMcpOAuthCallbackUrl(value);
            systemState.setMcpOAuthCallbackError(null);
          }}
          onMcpOAuthComplete={() => void systemActions.handleMcpOAuthComplete()}
          onDismissStatus={() => {
            systemState.setCliAppsMessage(null);
            systemState.setCliAppsError(null);
            systemState.setMcpMessage(null);
            systemState.setMcpError(null);
          }}
          onBackToChat={onBackToChat}
          onMcpFieldChange={(presetName, fieldName, value) => {
            systemState.setMcpFieldValues((prev) => ({
              ...prev,
              [presetName]: {
                ...(prev[presetName] ?? {}),
                [fieldName]: value,
              },
            }));
          }}
          onCustomMcpFormChange={systemState.setCustomMcpForm}
          onMcpConfigImportChange={systemState.setMcpConfigImport}
          onSaveCustomMcp={systemActions.handleSaveCustomMcp}
          onImportMcpConfig={systemActions.handleImportMcpConfig}
          onMcpToolsChange={systemActions.handleMcpToolsChange}
          mcpConfigEditor={{ load: systemActions.handleReadMcpConfig, save: systemActions.handleSaveMcpConfig }}
          onRestart={restartViaSettingsSurface}
          isRestarting={restartInProgress}
        />
      </div>
    );
  };

  return {
    "mcp": renderMcp,
    "apps": renderMcp,
  };
}
