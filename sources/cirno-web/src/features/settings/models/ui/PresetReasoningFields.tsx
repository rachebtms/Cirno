import { Description, Label, ListBox, Select } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type { SettingsPayload } from "@/lib/contracts/settings";
import type { ModelSettings } from "../model/useModelSettings";
import type { ModelsSettingsProps } from "../model/contracts";
import { ReasoningEffortPicker } from "../ReasoningEffortPicker";

export function PresetReasoningFields({
  model,
  options,
  provider,
}: {
  model: ModelSettings;
  options: ModelsSettingsProps;
  provider?: SettingsPayload["providers"][number];
}) {
  const { t } = useTranslation();
  const { form, setForm } = options;
  const histories = (["auto", "preserve", "omit"] as const).filter(
    (value) =>
      value !== "omit" ||
      !(
        form.provider === "deepseek" ||
        (form.provider === "auto" && model.selectedPreset?.resolved_provider === "deepseek")
      ),
  );
  return (
    <>
      <ReasoningEffortPicker
        token={options.token}
        provider={provider}
        model={form.model}
        savedValues={
          form.model === model.selectedPreset?.model &&
          form.provider === model.selectedPreset.provider
            ? model.selectedPreset.reasoning_effort_values
            : undefined
        }
        value={form.reasoningEffort}
        onSelect={options.editCompletion.complete}
        onChange={(reasoningEffort) => setForm((previous) => ({ ...previous, reasoningEffort }))}
      />
      <Select
        value={form.reasoningHistory ?? "auto"}
        onChange={(key) =>
          setForm((previous) => ({
            ...previous,
            reasoningHistory: String(key) as typeof form.reasoningHistory,
          }))
        }
      >
        <Label>{t("settings.models.reasoningHistory")}</Label>
        <Description>{t("settings.models.reasoningHistoryHelp")}</Description>
        <Select.Trigger>
          <Select.Value />
          <Select.Indicator />
        </Select.Trigger>
        <Select.Popover>
          <ListBox>
            {histories.map((id) => (
              <ListBox.Item
                key={id}
                id={id}
                textValue={t(`settings.models.reasoningHistoryOptions.${id}`)}
              >
                {t(`settings.models.reasoningHistoryOptions.${id}`)}
                <ListBox.ItemIndicator />
              </ListBox.Item>
            ))}
          </ListBox>
        </Select.Popover>
      </Select>
    </>
  );
}
