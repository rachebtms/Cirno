import { Description, Input, Label, ListBox, Select, TextField } from "@heroui/react";
import { useTranslation } from "react-i18next";
import { ToggleField } from "@/ui/fields/ToggleField";
import type { ProviderBalanceConfig } from "@/lib/contracts/models";
export function ProviderBalanceFields({ value, providerId, onChange }: {
  value: ProviderBalanceConfig | null; providerId: string; onChange: (value: ProviderBalanceConfig | null) => void;
}) {
  const { t } = useTranslation();
  const change = (patch: Partial<ProviderBalanceConfig>) => { if (value) onChange({ ...value, ...patch }); };
  const fields = [{ key: "endpoint", label: "endpoint", help: "endpointHelp" },
    ...(value?.format === "json" ? [{ key: "amount_path", label: "amountPath" }, { key: "currency", label: "currency" }] : []),
    { key: "api_key", label: "apiKey", help: "apiKeyHelp" }] as const;
  return <div className="provider-fields"><ToggleField label={t("settings.balance.enabled")} selected={value !== null} onChange={enabled => onChange(enabled ? {
    endpoint: providerId === "deepseek" ? "https://api.deepseek.com/user/balance" : "", format: providerId === "deepseek" ? "deepseek" : "json", amount_path: "/balance", currency: "USD", api_key: null,
  } : null)} />
    {value && <><Select value={value.format} onChange={format => change({ format: format as ProviderBalanceConfig["format"] })}>
      <Label>{t("settings.balance.format")}</Label><Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
      <Select.Popover><ListBox><ListBox.Item id="deepseek" textValue="DeepSeek">DeepSeek<ListBox.ItemIndicator /></ListBox.Item>
        <ListBox.Item id="json" textValue={t("settings.balance.json")}>{t("settings.balance.json")}<ListBox.ItemIndicator /></ListBox.Item></ListBox></Select.Popover>
    </Select>
      {fields.map(field => <TextField key={field.key} value={value[field.key as keyof ProviderBalanceConfig] ?? ""} onChange={text => change({ [field.key]: text || (field.key === "api_key" ? null : "") })}>
        <Label>{t(`settings.balance.${field.label}`)}</Label>{"help" in field && <Description>{t(`settings.balance.${field.help}`)}</Description>}
        <Input type={field.key === "api_key" ? "password" : "text"} autoComplete={field.key === "api_key" ? "new-password" : "off"} spellCheck={false} />
      </TextField>)}
    </>}
  </div>;
}
