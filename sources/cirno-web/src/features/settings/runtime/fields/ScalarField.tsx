import { Description, FieldError, Input, Label, TextArea, TextField } from "@heroui/react";
import { ToggleField } from "@/ui/fields/ToggleField";
import { useTranslation } from "react-i18next";
import type { ConfigurationFieldProps } from "./contracts";

export function ScalarField({ field, state, disabled }: ConfigurationFieldProps) {
  const { t } = useTranslation();
  const path = `settings.runtimeConfig.fields.${field.path.replaceAll(".", "_")}`;
  const multiline = field.kind === "multiline" || field.kind === "list";
  const error = state.invalidField === field.path ? state.errors[field.group] : undefined;
  return <TextField className="configuration-field" value={String(state.value(field.path))}
    isDisabled={disabled} isInvalid={Boolean(error)} onChange={value => state.change(field, value)}>
    <Label>{t(`${path}.label`)}</Label>
    <Description>{t(`${path}.help`)}</Description>
    {multiline ? <TextArea id={`runtime-${field.path}`} rows={4} className="configuration-textarea" autoComplete="off" />
      : <Input id={`runtime-${field.path}`} type={field.kind === "number" ? "number" : field.kind === "password" ? "password" : "text"}
        min={field.min} max={field.max} step={1} autoComplete={field.kind === "password" ? "new-password" : "off"} />}
    <FieldError>{error}</FieldError>
  </TextField>;
}

export function BooleanField({ field, state, disabled }: ConfigurationFieldProps) {
  const { t } = useTranslation();
  const path = `settings.runtimeConfig.fields.${field.path.replaceAll(".", "_")}`;
  const selected = field.kind === "toggle" ? state.value(field.path) === field.options?.[1] : state.value(field.path) === true;
  return <ToggleField id={`runtime-${field.path}`} label={t(`${path}.label`)} description={t(`${path}.help`)} className="configuration-switch" disabled={disabled} selected={selected}
    onChange={next => state.change(field, field.kind === "toggle" ? field.options![next ? 1 : 0] : next)} />;
}
