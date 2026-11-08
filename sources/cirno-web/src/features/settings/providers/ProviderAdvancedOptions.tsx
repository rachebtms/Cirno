import { Accordion, Button, Input, Label, ListBox, Select, TextField } from "@heroui/react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ToggleField } from "@/ui/fields/ToggleField";
import { ProviderParameterFields } from "./ProviderParameterFields";
import type { ProviderAdvancedField, ProviderForm } from "./providerForm";
export function ProviderAdvancedOptions({ fields, form, onChange, onConfigureProxy, children }: {
  fields: ProviderAdvancedField[]; form: ProviderForm; onChange: (patch: Partial<ProviderForm>) => void;
  onConfigureProxy?: () => void; children?: ReactNode;
}) {
  const { t } = useTranslation();
  const enabled = new Set(fields);
  if (!enabled.size && !children) return null;
  const styles = [{ id: ":default", name: t("settings.values.default") }, ...["thinking_type", "enable_thinking", "reasoning_split"].map(id => ({ id, name: id }))];
  return <Accordion><Accordion.Item id="advanced"><Accordion.Heading><Accordion.Trigger>{t("settings.providers.advancedOptions")}<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
    <Accordion.Panel><Accordion.Body className="provider-fields">{children}
      {enabled.has("thinking_style") && <Select value={form.thinkingStyle || ":default"} onChange={key => onChange({ thinkingStyle: key === ":default" ? "" : String(key) })}>
        <Label>{t("settings.providers.thinkingStyle")}</Label><Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
        <Select.Popover><ListBox items={styles}>{style => <ListBox.Item id={style.id} textValue={style.name}>{style.name}<ListBox.ItemIndicator /></ListBox.Item>}</ListBox></Select.Popover>
      </Select>}
      {enabled.has("use_proxy") && <div className="provider-proxy">
        <ToggleField selected={form.useProxy} onChange={useProxy => onChange({ useProxy })} label={t("settings.network.useProxy")} description={t("settings.network.useProxyHelp")} />{onConfigureProxy && <Button variant="secondary" onPress={onConfigureProxy}>{t("settings.network.configureProxy")}</Button>}
      </div>}
      {(["region", "profile"] as const).filter(key => enabled.has(key)).map(key => <TextField key={key} value={form[key]} onChange={value => onChange({ [key]: value })}>
        <Label>{t(`settings.providers.${key}`)}</Label><Input placeholder={key === "region" ? "us-east-1" : "default"} autoComplete="off" spellCheck={false} />
      </TextField>)}
      <ProviderParameterFields fields={fields} form={form} onChange={onChange} />
    </Accordion.Body></Accordion.Panel>
  </Accordion.Item></Accordion>;
}
