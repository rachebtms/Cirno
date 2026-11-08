import { Checkbox, CheckboxGroup, Description, Label, ListBox, Select } from "@heroui/react";
import { useTranslation } from "react-i18next";
import { MODEL_REQUEST_APIS, REQUEST_API_LABELS } from "../models/modelAPI";
import type { ModelAPIConfig, ModelRequestAPI } from "@/lib/contracts/models";
export function ProviderAPIControl({ value, onChange }: { value: ModelAPIConfig | null; onChange: (value: ModelAPIConfig) => void }) {
  const { t } = useTranslation();
  const supported = value?.supported_apis ?? [...MODEL_REQUEST_APIS];
  const preferred = value?.preferred_api ?? supported[0];
  return <div className="provider-fields"><CheckboxGroup value={supported} onChange={keys => {
    const next = MODEL_REQUEST_APIS.filter(api => keys.includes(api));
    onChange({ supported_apis: next, preferred_api: next.includes(preferred) ? preferred : next[0] });
  }}><Label>{t("settings.providers.supportedAPIs")}</Label><Description>{t("settings.providers.supportedAPIsDescription")}</Description>
    {MODEL_REQUEST_APIS.map(api => <Checkbox key={api} value={api} isDisabled={supported.length === 1 && supported.includes(api)}><Checkbox.Content><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><Label>{REQUEST_API_LABELS[api]}</Label></Checkbox.Content></Checkbox>)}
  </CheckboxGroup>
  <Select value={preferred} onChange={key => onChange({ supported_apis: supported, preferred_api: String(key) as ModelRequestAPI })}>
    <Label>{t("settings.providers.defaultAPI")}</Label><Description>{t("settings.providers.defaultAPIDescription")}</Description><Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
    <Select.Popover><ListBox>{supported.map(api => <ListBox.Item key={api} id={api} textValue={REQUEST_API_LABELS[api]}>{REQUEST_API_LABELS[api]}<ListBox.ItemIndicator /></ListBox.Item>)}</ListBox></Select.Popover>
  </Select></div>;
}
