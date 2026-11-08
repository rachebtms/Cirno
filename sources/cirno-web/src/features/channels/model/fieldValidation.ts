import type {
  ChannelConfigField,
  ChannelSetupRequirement,
} from "@/channel-plugins/catalog";
import { channelFieldInputId } from "./fieldValues";
export function channelRequirementErrors(
  fields: ChannelConfigField[],
  requirements: ChannelSetupRequirement[],
  values: Record<string, string>,
  configuredFields: Set<string>,
  clearedSecrets: Set<string>,
  message: string,
): Record<string, string> {
  const fieldByKey = new Map(fields.map((field) => [field.key, field]));
  const present = (key: string) => {
    const field = fieldByKey.get(key);
    if (!field || clearedSecrets.has(key)) return false;
    const value = (values[key] ?? "").trim();
    if (field.kind === "bool") return value === "true";
    if (value) return true;
    return Boolean(field.secret && configuredFields.has(key));
  };
  const errors: Record<string, string> = {};
  for (const requirement of requirements) {
    if (
      requirement.alternatives.some((alternative) => alternative.every(present))
    )
      continue;
    const closest =
      [...requirement.alternatives].sort(
        (left, right) =>
          left.filter((key) => !present(key)).length -
          right.filter((key) => !present(key)).length,
      )[0] ?? [];
    for (const key of closest) {
      if (!present(key) && fieldByKey.has(key)) errors[key] = message;
    }
  }
  return errors;
}

export function channelServerValidationErrors(
  fields: ChannelConfigField[],
  missingFields: string[],
  message: string,
): Record<string, string> {
  const missing = new Set(missingFields);
  return Object.fromEntries(
    fields
      .filter(
        (field) =>
          missing.has(field.key) ||
          missing.has(field.key.split(".").at(-1) ?? ""),
      )
      .map((field) => [field.key, message]),
  );
}

export function focusFirstChannelFieldError(
  errors: Record<string, string>,
  isCurrent = () => true,
) {
  const key = Object.keys(errors)[0];
  if (!key) return;
  window.requestAnimationFrame(() => {
    if (!isCurrent()) return;
    document.getElementById(channelFieldInputId(key))?.focus();
  });
}
