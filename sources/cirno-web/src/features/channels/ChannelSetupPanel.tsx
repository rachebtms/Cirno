import { Button, Spinner } from "@heroui/react";
import { Suspense } from "react";
import { useTranslation } from "react-i18next";
import type { ChannelPluginPanelProps } from "@/channel-plugins/types";
import { channelUiContribution } from "@/channel-plugins/registry";
import { ChannelLogo } from "@/features/channels/ui/ChannelLogo";
import {
  channelSetup,
  localizedChannelDisplayName,
} from "@/features/channels/model/presentation";
import { ChannelInstances } from "./ChannelInstances";
import { ChannelSetupSurface } from "./ui/setup/ChannelSetupSurface";
import { InlineError } from "@/ui/feedback/InlineError";
export function ChannelSetupPanel(props: ChannelPluginPanelProps) {
  const { t, i18n } = useTranslation(),
    { feature } = props;
  const contribution = channelUiContribution(feature.name, feature.webui),
    Plugin = contribution?.Panel;
  const header = (
    <div className="channel-setup-identity">
      <ChannelLogo feature={feature} showBrandLogos={props.showBrandLogos} />
      <h3>{localizedChannelDisplayName(feature, t)}</h3>
    </div>
  );
  const loading = (
    <div role="status" className="channel-plugin-loading">
      <Spinner size="sm" />
      {t("settings.loading")}
    </div>
  );
  if (Plugin && feature.installed)
    return (
      <Suspense fallback={loading}>
        <Plugin {...props} />
      </Suspense>
    );
  if (feature.instances !== undefined && feature.installed)
    return (
      <ChannelInstances
        feature={feature}
        showBrandLogos={props.showBrandLogos}
        onFeaturesUpdate={props.onFeaturesUpdate}
        onBeforeCloseChange={props.onBeforeCloseChange}
      />
    );
  if (!feature.installed)
    return (
      <div className="channel-setup-missing">
        {header}
        <InlineError message={feature.runtime_error} />
        {feature.install_supported && (
          <Button
            size="sm"
            variant="secondary"
            isDisabled={Boolean(props.actionKey)}
            isPending={props.actionKey === `install:${feature.name}`}
            onPress={() =>
              props.onAction("enable", feature.name, {
                installOnly: true,
                confirmed: true,
              })
            }
          >
            {t("settings.channels.install")}
          </Button>
        )}
      </div>
    );
  return (
    <ChannelSetupSurface
      key={feature.name}
      {...props}
      header={header}
      setup={channelSetup(feature, i18n.resolvedLanguage ?? i18n.language)}
      ConnectFlow={contribution?.ConnectFlow}
    />
  );
}
