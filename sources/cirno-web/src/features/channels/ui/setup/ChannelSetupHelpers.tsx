import { Button, Link } from "@heroui/react";
import { Clipboard } from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  ChannelProviderPreset,
  ChannelSetupPresentation,
} from "@/channel-plugins/catalog";
import { copyTextToClipboard } from "@/lib/clipboard";
import type { CirnoFeatureInfo } from "@/lib/contracts/channels";
export function ChannelSetupActions({
  setup,
  onNotice,
}: {
  feature?: CirnoFeatureInfo;
  setup: ChannelSetupPresentation;
  onNotice: (message: string | null) => void;
}) {
  const { t } = useTranslation();
  return setup.actions?.length ? (
    <div className="channel-setup-helpers">
      {setup.actions.map((action) =>
        action.copyText ? (
          <Button
            key={action.id}
            type="button"
            variant="secondary"
            size="sm"
            onPress={() => {
              void copyTextToClipboard(action.copyText!).then((ok) =>
                onNotice(
                  t(
                    ok
                      ? "settings.channels.helperCopied"
                      : "settings.channels.helperCopyFailed",
                    { name: action.label },
                  ),
                ),
              );
            }}
          >
            <Clipboard size={16} />
            {action.label}
          </Button>
        ) : action.url ? (
          <Link
            key={action.id}
            href={action.url}
            target="_blank"
            rel="noreferrer"
          >
            {action.label}
          </Link>
        ) : null,
      )}
    </div>
  ) : null;
}
export function ChannelProviderPresets({
  presets,
  onApply,
  label,
  disabled,
}: {
  presets: ChannelProviderPreset[];
  onApply: (preset: ChannelProviderPreset) => void;
  label?: string;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  return presets.length ? (
    <fieldset className="channel-presets">
      <legend>{label ?? t("settings.channels.providerPreset")}</legend>
      <div>
        {presets.map((preset) => (
          <Button
            key={preset.id}
            type="button"
            size="sm"
            variant="secondary"
            isDisabled={disabled}
            onPress={() => onApply(preset)}
          >
            {preset.label}
          </Button>
        ))}
      </div>
    </fieldset>
  ) : null;
}
