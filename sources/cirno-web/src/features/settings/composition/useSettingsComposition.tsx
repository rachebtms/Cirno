import { useRef, useState } from "react";
import type { SettingsPageProps } from "./contracts";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import { AdvancedSettings } from "../capabilities/SecuritySettings";
import { RuntimeConfiguration } from "../runtime/RuntimeConfiguration";
import type { RuntimeConfigPage } from "../system/runtime-config-fields";
import { providerFormFromRow } from "../providers/providerForm";
import { ProvidersSettings, type ProviderSettingsEntry } from "../providers/ProvidersSettings";
import { useSettingsNavigation } from "./useSettingsNavigation";

export function useSettingsComposition(props: SettingsPageProps) {
  const { controller, showSidebar, registerExitGuard, onBackToChat, isRestarting } = props;
  const [dialogLayoutAnchor, setDialogLayoutAnchor] = useState<HTMLElement | null>(null);
  const [mcpSetupName, setMcpSetupName] = useState<string | null>(null);
  const presetDeletedCallback = useRef<(() => void) | null>(null);
  const [providerPanel, setProviderPanel] = useState<ProviderSettingsEntry | null>(null);
  const [providerFocus, setProviderFocus] = useState<string | null>(null);
  const [proxySetupOpen, setProxySetupOpen] = useState(false);
  const providerAddedCallback = useRef<((provider: string) => void) | null>(null);
  const openProviderPanel = (
    entry: ProviderSettingsEntry,
    trigger: HTMLButtonElement | null,
    onAdded?: (provider: string) => void,
  ) => {
    trigger?.focus({ preventScroll: true });
    providerAddedCallback.current = onAdded ?? null;
    setProviderPanel(entry);
  };
  const [automationDetailReturn, setAutomationDetailReturn] =
    useState<SessionAutomationJob | null>(null);
  const { modelState, modelActions, capabilityState, capabilityActions, systemState, activeSection, error,
    displayPreferences, networkSafetyDirty, pendingRestartSections: controllerPendingRestartSections,
    remoteBrowserAccess, restartViaSettingsSurface, settings } = controller;
  const configureProxy = settings?.runtime_config && !String(settings.runtime_config["network.proxy"] ?? "").trim()
    ? () => setProxySetupOpen(true)
    : undefined;

  const restartInProgress = isRestarting;
  const { selectSection, requestExit, pendingExit, setPendingExit, registerChannelCompletion } =
    useSettingsNavigation(controller, restartInProgress, registerExitGuard);
  const backToChat = () => registerExitGuard ? onBackToChat() : requestExit(onBackToChat);
  const pendingRestartSections = showSidebar
    ? { runtime: false, browser: false }
    : controllerPendingRestartSections;

  const runtimeConfiguration = (page: RuntimeConfigPage) => settings && (
    <RuntimeConfiguration page={page} settings={settings} state={controller.runtimeConfigState}
      onRestart={showSidebar ? undefined : restartViaSettingsSurface} isRestarting={restartInProgress}
    >
      {page === "advanced" ? (
        <AdvancedSettings
          editCompletion={controller.safetyEdits}
          error={capabilityState.capabilityErrors.safety}
          form={capabilityState.networkSafetyForm}
          dirty={networkSafetyDirty}
          saving={capabilityState.networkSafetySaving}

          onChangeForm={capabilityState.setNetworkSafetyForm}
          onSave={capabilityActions.saveNetworkSafetySettings}
          onRestart={restartViaSettingsSurface}
          isRestarting={restartInProgress}
          requiresRestartPending={pendingRestartSections.runtime}
        />
      ) : null}
    </RuntimeConfiguration>
  );

  const renderProviderPanel = () => {
    if (!settings || !providerPanel) return null;
    return <ProvidersSettings
      error={error}
      onConfigureProxy={configureProxy}
      entry={providerPanel}
      onClose={() => { setProviderPanel(null); providerAddedCallback.current = null; }}
      onProviderAdded={(provider) => {
        if (activeSection === "providers") setProviderFocus(provider);
        providerAddedCallback.current?.(provider);
      }}
      settings={settings}
      cirnoFeatures={systemState.cirnoFeatures}
      featureAction={systemState.cirnoFeatureAction}
      capabilityError={systemState.cirnoFeaturesError}
      providerForms={modelState.providerForms}
      visibleProviderKeys={modelState.visibleProviderKeys}
      editingProviderKeys={modelState.editingProviderKeys}
      providerSaving={controller.providerAuthorization.operation?.provider ?? modelState.providerSaving}
      showBrandLogos={displayPreferences.brandLogos}
      remoteBrowserAccess={remoteBrowserAccess}
      onResetProviderDraft={modelActions.resetProviderDraft}
      onToggleProviderKey={modelActions.toggleProviderKeyVisibility}
      onToggleProviderKeyEditing={modelActions.toggleProviderKeyEditing}
      onChangeProviderForm={(provider, value) => {
        const row = settings.providers.find((item) => item.id === provider);
        if (!row) return;
        modelState.setProviderForms((prev) => ({
          ...prev,
          [provider]: {
            ...(prev[provider] ?? providerFormFromRow(row)),
            ...value,
          },
        }));
      }}
      onSaveProvider={modelActions.saveProvider}
      onCreateCustomProvider={modelActions.createCustomProvider}
      providerOperation={controller.providerAuthorization.operation ?? modelState.providerOperation}
      onProviderOAuthLogin={(provider) => controller.providerAuthorization.login(provider)}
      onProviderOAuthLogout={(provider) => controller.providerAuthorization.logout(provider)}
    />;
  };

  return {
    ...props, ...controller, dialogLayoutAnchor, setDialogLayoutAnchor, mcpSetupName, setMcpSetupName,
    presetDeletedCallback, openProviderPanel, proxySetupOpen, setProxySetupOpen,
    automationDetailReturn, setAutomationDetailReturn, configureProxy, restartInProgress, selectSection, requestExit,
    pendingExit, setPendingExit, registerChannelCompletion, backToChat, pendingRestartSections,
    runtimeConfiguration, renderProviderPanel, providerFocus: providerPanel ? null : providerFocus,
    consumeProviderFocus: () => setProviderFocus(null),
  };
}
export type SettingsComposition = ReturnType<typeof useSettingsComposition>;
