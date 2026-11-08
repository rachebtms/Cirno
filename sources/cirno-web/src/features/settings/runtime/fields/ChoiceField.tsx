import { ComboBox, Description, Input, Label, ListBox, Select } from "@heroui/react";
import { ChevronDown } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { configurationOptions } from "../model";
import type { ConfigurationFieldProps } from "./contracts";

export function ChoiceField({ field, state, settings, disabled }: ConfigurationFieldProps) {
  const { t } = useTranslation();
  const path = `settings.runtimeConfig.fields.${field.path.replaceAll(".", "_")}`;
  const current = String(state.value(field.path));
  const options = configurationOptions(field, settings, current, t);
  return <Select className="configuration-field" value={current || ":none"} isDisabled={disabled}
    isInvalid={state.invalidField === field.path} onChange={key => state.change(field, key === ":none" ? "" : String(key))}>
    <Label>{t(`${path}.label`)}</Label><Description>{t(`${path}.help`)}</Description>
    <Select.Trigger id={`runtime-${field.path}`}><Select.Value /><Select.Indicator /></Select.Trigger>
    <Select.Popover><ListBox items={options}>{option => <ListBox.Item id={option.id} textValue={option.name}>
      {option.name}<ListBox.ItemIndicator />
    </ListBox.Item>}</ListBox></Select.Popover>
  </Select>;
}

export function TimezoneField({ field, state, disabled }: ConfigurationFieldProps) {
  const { t } = useTranslation();
  const current = String(state.value(field.path));
  const zones = useMemo(() => [...new Set(["UTC", ...Intl.supportedValuesOf("timeZone"), current])].filter(Boolean).sort()
    .map(zone => ({ id: zone })), [current]);
  const path = `settings.runtimeConfig.fields.${field.path.replaceAll(".", "_")}`;
  return <ComboBox className="configuration-field" selectedKey={current} defaultItems={zones} isDisabled={disabled}
    onSelectionChange={key => { if (key !== null) state.change(field, String(key)); }}>
    <Label>{t(`${path}.label`)}</Label><Description>{t(`${path}.help`)}</Description>
    <ComboBox.InputGroup><Input id={`runtime-${field.path}`} /><ComboBox.Trigger><ChevronDown size={16} /></ComboBox.Trigger></ComboBox.InputGroup>
    <ComboBox.Popover><ListBox<{ id: string }>>{zone => <ListBox.Item id={zone.id} textValue={zone.id}>{zone.id}<ListBox.ItemIndicator /></ListBox.Item>}</ListBox></ComboBox.Popover>
  </ComboBox>;
}
