import { ToggleField } from "@/ui/fields/ToggleField";
import { Description, Input, Label, ListBox, Select, TextField } from "@heroui/react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ConfigurationFieldProps } from "./contracts";

export function DurationField({ field, state, settings, disabled }: ConfigurationFieldProps) {
  const { t, i18n } = useTranslation();
  const value = String(state.value(field.path));
  const maximum = settings.advanced.exec_max_runtime_limit;
  const presets = [...new Set([900, 1800, 3600, 21600, 43200, 86400, ...(maximum === undefined ? [] : [maximum])])]
    .filter(seconds => maximum === undefined || seconds <= maximum);
  const [custom, setCustom] = useState(false);
  const isCustom = custom || (value !== "0" && !presets.includes(Number(value)));
  const path = `settings.runtimeConfig.fields.${field.path.replaceAll(".", "_")}`;
  const format = (seconds: number) => new Intl.NumberFormat(i18n.language, { style: "unit", unit: seconds % 3600 ? "minute" : "hour", unitDisplay: "long" })
    .format(seconds / (seconds % 3600 ? 60 : 3600));
  const options = [...presets.map(seconds => ({ id: String(seconds), label: format(seconds) })),
    { id: "0", label: t("settings.runtimeConfig.commandRuntime.noLimit") },
    { id: ":custom", label: t("settings.runtimeConfig.commandRuntime.custom") }];
  return <div className="configuration-field">
    <Select value={isCustom ? ":custom" : value} isDisabled={disabled} onChange={key => {
      setCustom(key === ":custom");
      if (key !== ":custom") state.change(field, String(key));
    }}>
      <Label>{t(`${path}.label`)}</Label><Description>{t(`${path}.help`)}</Description>
      <Select.Trigger id={isCustom ? undefined : `runtime-${field.path}`}><Select.Value /><Select.Indicator /></Select.Trigger>
      <Select.Popover><ListBox items={options}>{option => <ListBox.Item id={option.id} textValue={option.label}>{option.label}<ListBox.ItemIndicator /></ListBox.Item>}</ListBox></Select.Popover>
    </Select>
    {isCustom && <TextField value={value === "0" ? "" : value} isDisabled={disabled} isInvalid={state.invalidField === field.path}
      onChange={next => { setCustom(true); state.change(field, next); }}>
      <Label>{t("settings.runtimeConfig.commandRuntime.customLabel")}</Label>
      <Input id={`runtime-${field.path}`} type="number" min={1} max={maximum} step={1} />
    </TextField>}
    {maximum !== undefined && <Description>{t("settings.runtimeConfig.commandRuntime.limit", { duration: format(maximum) })}</Description>}
  </div>;
}

export function IdleCompactionField({ field, state, disabled }: ConfigurationFieldProps) {
  const { t } = useTranslation();
  const value = String(state.value(field.path));
  const previous = useRef(value !== "0" ? value : "15");
  const editing = useRef(false);
  const enabled = value !== "0" || (editing.current && state.dirty(field));
  const tr = (key: string) => t(`settings.runtimeConfig.idleCompaction.${key}`);
  const changeEnabled = (next: boolean) => {
    editing.current = false;
    if (/^\d+$/.test(value) && Number(value) > 0) previous.current = value;
    state.commit(field, next ? previous.current : "0");
  };
  return <div className="configuration-field">
    <ToggleField label={tr("label")} selected={enabled} onChange={changeEnabled} disabled={disabled} className="configuration-switch" description={tr("help")} />
    {enabled && <TextField value={value} isDisabled={disabled} isInvalid={state.invalidField === field.path}
      onChange={next => { editing.current = true; state.change(field, next); }}>
      <Label>{tr("wait")}</Label><Input id={`runtime-${field.path}`} inputMode="numeric" /><Description>{tr("minutes")}</Description>
    </TextField>}
  </div>;
}
