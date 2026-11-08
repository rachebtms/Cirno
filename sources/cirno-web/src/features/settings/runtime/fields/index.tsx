import type { ComponentType } from "react";
import type { RuntimeConfigField } from "../../system/runtime-config-fields";
import type { ConfigurationFieldProps } from "./contracts";
import { BooleanField, ScalarField } from "./ScalarField";
import { ChoiceField, TimezoneField } from "./ChoiceField";
import { DurationField, IdleCompactionField } from "./DurationField";
import { ProxyField } from "./ProxyField";

const kinds: Record<RuntimeConfigField["kind"], ComponentType<ConfigurationFieldProps>> = {
  boolean: BooleanField, toggle: BooleanField, select: ChoiceField, preset: ChoiceField,
  text: ScalarField, password: ScalarField, nullable: ScalarField, number: ScalarField,
  list: ScalarField, multiline: ScalarField, duration: DurationField, "idle-compaction": IdleCompactionField,
};
const specialized: Record<string, ComponentType<ConfigurationFieldProps>> = {
  "network.proxy": ProxyField, "agents.defaults.timezone": TimezoneField,
};
export function ConfigurationField(props: ConfigurationFieldProps) {
  const Field = specialized[props.field.path] ?? kinds[props.field.kind];
  return <Field {...props} />;
}
