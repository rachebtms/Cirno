import { ChannelsSettings } from "@/features/channels/ChannelsSettings";
import type { SectionRenderer, SectionRenderers } from "./contracts";
import type { SettingsComposition } from "./useSettingsComposition";

export function createChannelSections(bindings: SettingsComposition): SectionRenderers {
  const { systemState, systemActions, displayPreferences, settings, token, restartInProgress, selectSection, pendingRestartSections, registerChannelCompletion, setMcpSetupName, restartViaSettingsSurface } = bindings;
  const renderChannels: SectionRenderer = () => {
    return (
      <ChannelsSettings
        onBeforeCloseChange={registerChannelCompletion}
        onConfigureMcp={(name) => {
          setMcpSetupName(name);
          systemState.setAppsKindFilter("mcp");
          systemState.setAppsQuery(name);
          selectSection("mcp");
        }}
        token={token}
        cirnoFeatures={systemState.cirnoFeatures}
        loading={systemState.cirnoFeaturesLoading}
        actionKey={systemState.cirnoFeatureAction}
        chatAppsDocsUrl={settings?.docs?.chat_apps_url}
        showBrandLogos={displayPreferences.brandLogos}
        error={systemState.cirnoFeaturesError}
        requiresRestartPending={pendingRestartSections.runtime}
        onAction={systemActions.handleCirnoFeatureAction}
        onFeaturesUpdate={systemState.setCirnoFeatures}
        onDismissStatus={() => {
          systemState.setCirnoFeaturesError(null);
        }}
        onRestart={restartViaSettingsSurface}
        isRestarting={restartInProgress}
      />
    );
  };

  return {
    "channels": renderChannels,
  };
}
