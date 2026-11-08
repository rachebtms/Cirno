import { Button } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type {
  ChannelConfigField,
  ChannelProviderPreset,
} from "@/channel-plugins/catalog";
import { ChannelProviderPresets } from "./ChannelSetupHelpers";
import { ChannelFields } from "../fields/ChannelFields";
import type { ChannelFieldsProps } from "../fields/contracts";
export function ChannelAdvanced({
  fields,
  savedSecrets,
  presets,
  presetLabel,
  onApplyPreset,
  ...form
}: {
  fields: ChannelConfigField[];
  savedSecrets: ChannelConfigField[];
  presets: ChannelProviderPreset[];
  presetLabel?: string;
  onApplyPreset: (preset: ChannelProviderPreset) => void;
} & Omit<ChannelFieldsProps, "fields">) {
  const { t } = useTranslation();
  return (
    <div className="channel-advanced">
      <ChannelProviderPresets
        presets={presets}
        onApply={onApplyPreset}
        label={presetLabel}
        disabled={form.disabled}
      />
      {savedSecrets
        .filter((field) => !form.values[field.key]?.trim())
        .map((field) => (
          <div key={field.key} className="channel-secret-action">
            <span>{field.label}</span>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              isDisabled={form.disabled || form.secretActionsDisabled}
              onPress={() =>
                form.onClearSecret?.(
                  field.key,
                  !form.clearedSecrets?.has(field.key),
                )
              }
            >
              {t(
                form.clearedSecrets?.has(field.key)
                  ? "settings.channels.keepSavedSecret"
                  : "settings.channels.removeSavedSecret",
              )}
            </Button>
          </div>
        ))}
      <ChannelFields fields={fields} {...form} />
    </div>
  );
}
