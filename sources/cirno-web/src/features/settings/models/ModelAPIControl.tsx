import { Description, Label, ListBox, Select } from "@heroui/react";
import { ToggleField } from "@/ui/fields/ToggleField";
import { useTranslation } from "react-i18next";
import { modelAPIConfigurable, preferredModelAPI, REQUEST_API_LABELS } from "./modelAPI";
import type { ModelAPIConfig, ProviderRequestAPI } from "@/lib/contracts/models";
import type { SettingsPayload } from "@/lib/contracts/settings";
export function ModelAPIControl({
  provider,
  automaticAPI,
  title,
  description,
  value,
  onChange,
}: {
  provider: SettingsPayload["providers"][number] | undefined;
  automaticAPI?: ProviderRequestAPI;
  title?: string;
  description?: string;
  value: ModelAPIConfig | null;
  onChange: (value: ModelAPIConfig | null) => void;
}) {
  const { t } = useTranslation();
  const requestAPIs = provider?.request_apis;
  const configurable = modelAPIConfigurable(provider);
  const fixed = requestAPIs?.length === 1 ? requestAPIs[0] : undefined;
  const labels = {
    ...REQUEST_API_LABELS,
    bedrock_converse: "Bedrock Converse",
  };
  const selected = preferredModelAPI(value);
  const supported = (["responses", "chat_completions", "anthropic_messages"] as const).filter(
    (api) => (requestAPIs ? requestAPIs.includes(api) : api !== "anthropic_messages"),
  );
  const options = [
    {
      id: "auto",
      name: automaticAPI
        ? `${t("settings.models.apiAuto")} (${labels[automaticAPI]})`
        : t("settings.models.apiAuto"),
    },
    ...supported.map((id) => ({ id, name: labels[id] })),
  ];
  if (!configurable && !fixed) return null;
  return (
    <div className="provider-fields">
      {configurable ? (
        <Select
          value={selected}
          onChange={(key) => {
            if (key === "auto") onChange(null);
            else {
              const api = supported.find((item) => item === key);
              if (api) onChange({ supported_apis: [api], preferred_api: api });
            }
          }}
        >
          <Label>{title ?? t("settings.models.requestAPI")}</Label>
          <Description>{description ?? t("settings.models.requestAPIDescription")}</Description>
          <Select.Trigger>
            <Select.Value />
            <Select.Indicator />
          </Select.Trigger>
          <Select.Popover>
            <ListBox items={options}>
              {(option) => (
                <ListBox.Item id={option.id} textValue={option.name}>
                  {option.name}
                  <ListBox.ItemIndicator />
                </ListBox.Item>
              )}
            </ListBox>
          </Select.Popover>
        </Select>
      ) : (
        <div>
          <Label>{title ?? t("settings.models.requestAPI")}</Label>
          <p>{labels[fixed!]}</p>
          <Description>
            {description ?? t("settings.models.fixedAPIDescription", { api: labels[fixed!] })}
          </Description>
        </div>
      )}
      {configurable &&
        selected === "responses" &&
        (!requestAPIs || requestAPIs.includes("chat_completions")) && (
          <ToggleField
            label={t("settings.models.apiFallback")}
            description={t("settings.models.apiFallbackDescription")}
            selected={value?.supported_apis.includes("chat_completions") === true}
            onChange={(enabled) =>
              onChange({
                supported_apis: enabled ? ["responses", "chat_completions"] : ["responses"],
                preferred_api: "responses",
              })
            }
          />
        )}
    </div>
  );
}
