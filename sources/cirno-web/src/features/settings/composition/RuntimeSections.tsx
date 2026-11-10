import { ProfileFiles } from "@/features/profile/ProfileFiles";
import { SettingsFeature } from "../shared/SettingsFeature";
import { RestartRequiredNotice, SettingsSectionTitle } from "../shared/SettingsControls";
import { WebSettings } from "../web/WebSettings";
import { RUNTIME_CONFIG_FIELDS } from "../system/runtime-config-fields";
import { RuntimeSettings } from "../system/RuntimeSettings";
import type { SectionRenderer, SectionRenderers } from "./contracts";
import type { SettingsComposition } from "./useSettingsComposition";

export function createRuntimeSections(bindings: SettingsComposition): SectionRenderers {
  const { controller, showSidebar, modelState, capabilityState, capabilityActions, systemState, activeSection, featureCatalog, displayPreferences, settings, t, restartInProgress, pendingRestartSections, runtimeConfiguration, restartViaSettingsSurface } = bindings;
  if (!settings) return {};
  const renderCapabilities: SectionRenderer = () => {
    const state = controller.runtimeConfigState;
    const toggleRuntime = (path: string, enabled: boolean) => {
      const field = RUNTIME_CONFIG_FIELDS.find((item) => item.path === path);
      if (field) state.change(field, enabled);
    };
    return (
      <section className="settings-stack">
        <div className="settings-section-heading">
          <SettingsSectionTitle>{t("settings.nav.capabilities")}</SettingsSectionTitle>
          {!showSidebar && settings.requires_restart ? <RestartRequiredNotice message={t("settings.status.savedRestartApply")}
            onRestart={restartViaSettingsSurface} isRestarting={restartInProgress} /> : null}
        </div>

        <SettingsFeature onBeforeClose={controller.webEdits.needsCompletion() ? controller.webEdits.commit : undefined} title={t("settings.runtimeConfig.groups.web.title")}
          enabled={settings.runtime_config ? state.value("tools.web.enable") === true : settings.web.enable}
          disabled={restartInProgress || state.saving === "web" || !settings.runtime_config}
          initialOpen={activeSection === "browser"} error={state.errors.web || capabilityState.capabilityErrors.web}
          onChange={(enabled) => toggleRuntime("tools.web.enable", enabled)}>
          {renderBrowser({ embedded: true })}
        </SettingsFeature>
        {!settings.runtime_config ? <p className="settings-list-inset text-[13px] text-muted-foreground">{t("settings.runtimeConfig.unavailable")}</p> : null}
      </section>
    );
  };

  const renderBrowser: SectionRenderer = ({ embedded }) => {
    return (
      <div className="settings-stack">
        {!embedded ? runtimeConfiguration("browser") : null}
        <WebSettings
          editCompletion={controller.webEdits}
          error={capabilityState.capabilityErrors.web || controller.runtimeConfigState.errors.web}
          embedded={embedded}
          enabled={settings.runtime_config
            ? controller.runtimeConfigState.value("tools.web.enable") !== false
            : settings.web.enable}
          settings={settings}
          form={capabilityState.webSearchForm}
          keyVisible={capabilityState.webSearchKeyVisible}
          keyEditing={capabilityState.webSearchKeyEditing}
          saving={capabilityState.webSearchSaving}
          onChangeForm={capabilityState.setWebSearchForm}
          onChangeProvider={capabilityActions.handleWebSearchProviderChange}
          onToggleKey={() => capabilityState.setWebSearchKeyVisible((visible) => !visible)}
          onToggleKeyEditing={() => {
            capabilityState.setWebSearchKeyEditing((editing) => !editing);
            capabilityState.setWebSearchKeyVisible(false);
            capabilityState.setWebSearchForm((prev) => ({ ...prev, apiKey: "" }));
          }}
          onReset={capabilityActions.resetWebSearchDraft}
          onSave={capabilityActions.saveWebSearch}
          showBrandLogos={displayPreferences.brandLogos}
          onRestart={restartViaSettingsSurface}
          isRestarting={restartInProgress}
          requiresRestartPending={pendingRestartSections.browser}
          olostepFeature={featureCatalog.find((feature) => feature.name === "olostep")}
          olostepInstalling={systemState.cirnoFeatureAction === "enable:olostep"}
          capabilityError={systemState.cirnoFeaturesError}
        >
          {settings.runtime_config ? runtimeConfiguration("web-network") : null}
        </WebSettings>
      </div>
    );
  };

  const renderHeartbeat: SectionRenderer = () => {
    return <div className="settings-stack"><p className="settings-list-inset text-sm leading-6 text-muted-foreground">{t("settings.heartbeat.help")}</p>
      {runtimeConfiguration("heartbeat")}<ProfileFiles client={controller.client} section="heartbeat" /></div>;
  };

  const renderCoordination: SectionRenderer = () => {
    return runtimeConfiguration("coordination");
  };

  const renderRegional: SectionRenderer = () => {
    return runtimeConfiguration("regional");
  };

  const renderRuntime: SectionRenderer = () => {
    return (
      <div className="settings-stack">
        {runtimeConfiguration("runtime")}
        <RuntimeSettings
          form={modelState.form}
          settings={settings}
          onRestart={showSidebar ? undefined : restartViaSettingsSurface}
          isRestarting={restartInProgress}
          requiresRestartPending={pendingRestartSections.runtime}
        />
      </div>
    );
  };

  const renderConsolidation: SectionRenderer = () => runtimeConfiguration("consolidation");

  const renderMemorySearch: SectionRenderer = () => {
    return runtimeConfiguration("memory-search");
  };

  const renderApproval: SectionRenderer = () => {
    return runtimeConfiguration("approval");
  };

  const renderExecution: SectionRenderer = () => {
    return runtimeConfiguration("execution");
  };

  const renderShell: SectionRenderer = () => {
    return runtimeConfiguration("shell");
  };

  const renderNetwork: SectionRenderer = () => {
    return runtimeConfiguration("network");
  };

  const renderAdvanced: SectionRenderer = () => {
    return runtimeConfiguration("advanced");
  };

  return {
    "capabilities": renderCapabilities,
    "browser": renderBrowser,
    "heartbeat": renderHeartbeat,
    "coordination": renderCoordination,
    "regional": renderRegional,
    "runtime": renderRuntime,
    "consolidation": renderConsolidation,
    "memory-search": renderMemorySearch,
    "approval": renderApproval,
    "execution": renderExecution,
    "shell": renderShell,
    "network": renderNetwork,
    "advanced": renderAdvanced,
  };
}
