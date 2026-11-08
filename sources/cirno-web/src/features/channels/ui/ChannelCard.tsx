import { Button, Card } from "@heroui/react";
import { ToggleField } from "@/ui/fields/ToggleField";
import { Download, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CirnoFeatureInfo } from "@/lib/contracts/channels";
import type { ChannelFeatureAction } from "@/channel-plugins/types";
import { ChannelLogo } from "@/features/channels/ui/ChannelLogo";
import {
  channelStatusLabel,
  channelToggleChecked,
} from "@/features/channels/model/status";
import { localizedChannelDisplayName } from "@/features/channels/model/presentation";
export function ChannelCard({
  feature,
  showBrandLogos,
  onSelect,
  actionKey,
  onAction,
  restartRequired = false,
  onRestart,
  isRestarting = false,
}: {
  feature: CirnoFeatureInfo;
  showBrandLogos: boolean;
  onSelect: (connect?: boolean) => void;
  actionKey: string | null;
  onAction: ChannelFeatureAction;
  restartRequired?: boolean;
  onRestart?: () => void;
  isRestarting?: boolean;
}) {
  const { t } = useTranslation(),
    name = localizedChannelDisplayName(feature, t);
  const pending =
    actionKey === `enable:${feature.name}`
      ? true
      : actionKey === `disable:${feature.name}`
        ? false
        : null;
  const checked =
    feature.capabilities?.includes("always_enabled") ||
    (pending ?? channelToggleChecked(feature));
  const disabled = Boolean(actionKey) || restartRequired || isRestarting;
  return (
    <Card className="channel-card">
      <Card.Content>
        <div className="channel-card-identity">
          <Button
            variant="ghost"
            className="channel-open"
            aria-label={t("settings.channels.selectChannel", { name })}
            aria-haspopup="dialog"
            onPress={() => onSelect()}
          >
            <ChannelLogo feature={feature} showBrandLogos={showBrandLogos} />
            <span>
              <strong>{name}</strong>
              <span data-failed={feature.runtime_status === "failed"}>
                {channelStatusLabel(feature, (key, fallback) =>
                  t(key, { defaultValue: fallback }),
                )}
              </span>
            </span>
          </Button>
          {!feature.installed ? (
            <Button
              variant="secondary"
              size="sm"
              isDisabled={disabled || !feature.install_supported}
              isPending={actionKey === `install:${feature.name}`}
              aria-label={t("settings.channels.installChannel", { name })}
              onPress={() =>
                onAction("enable", feature.name, {
                  installOnly: true,
                  confirmed: true,
                })
              }
            >
              <Download size={16} />
              {t("settings.channels.install")}
            </Button>
          ) : feature.restart_pending ? (
            <Button
              variant="secondary"
              size="sm"
              isDisabled={Boolean(actionKey) || isRestarting || !onRestart}
              isPending={isRestarting}
              onPress={onRestart}
            >
              <RotateCcw size={16} />
              {t("app.system.restart")}
            </Button>
          ) : (
            <ToggleField
              label={t("settings.channels.toggleChannel", { name })}
              labelHidden
              selected={Boolean(checked)}
              disabled={
                disabled || feature.capabilities?.includes("always_enabled")
              }
              onChange={(enabled) => {
                if (enabled && feature.configured === false) onSelect(true);
                else onAction(enabled ? "enable" : "disable", feature.name);
              }}
            />
          )}
        </div>
      </Card.Content>
    </Card>
  );
}
