import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ThreadComposer } from "@/components/thread/ThreadComposer";
import {
  modelPresetOptionsFromSettings,
  toModelBadgeInfo,
} from "@/components/thread/model-preset";
import type { AutomationsPageProps } from "../model/contracts";

export function AutomationComposer({
  settingsSnapshot,
  onStartChat,
  onManageModels,
}: Pick<
  AutomationsPageProps,
  "settingsSnapshot" | "onStartChat" | "onManageModels"
>) {
  const { t } = useTranslation();
  const [model, setModel] = useState<string | null>(null);
  const selected =
    model &&
    (!settingsSnapshot ||
      settingsSnapshot.model_presets.some((row) => row.id === model))
      ? model
      : (settingsSnapshot?.agent.model_preset ?? null);
  const badge = toModelBadgeInfo(
    settingsSnapshot?.agent.model ?? null,
    settingsSnapshot ?? null,
    selected,
  );
  if (!onStartChat) return null;
  return (
    <div
      className="automation-create-composer"
      aria-label={t("settings.automations.create")}
    >
      <ThreadComposer
        onSend={(content, images, options) =>
          onStartChat(
            content.trim(),
            images,
            { ...options, intent: "create_automation" },
            selected,
          )
        }
        inputAriaLabel={t("settings.automations.createInput")}
        placeholder={t("settings.automations.createPrompt")}
        variant="thread"
        compactWhenIdle
        modelLabel={
          badge.needsSetup ? t("thread.composer.chooseAI") : badge.label
        }
        modelDetail={badge.model}
        modelPreset={selected}
        modelPresets={modelPresetOptionsFromSettings(settingsSnapshot ?? null)}
        onModelPresetChange={setModel}
        modelProvider={badge.provider}
        modelProviderLabel={badge.providerLabel}
        modelNeedsSetup={badge.needsSetup}
        onModelBadgeClick={badge.needsSetup ? onManageModels : undefined}
        onManageModels={onManageModels}
      />
    </div>
  );
}
