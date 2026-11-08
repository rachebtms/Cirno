import type { ChannelConfigField } from "@/channel-plugins/catalog";

export function channelFieldValue(
  field: ChannelConfigField,
  values: Record<string, string>,
): string {
  return (
    values[field.key] ?? field.defaultValue ?? field.options?.[0]?.value ?? ""
  );
}

export function channelFieldInputId(key: string): string {
  return `channel-field-${key.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

export function defaultChannelFieldValues(
  fields: ChannelConfigField[],
  configValues: Record<string, string> | undefined = undefined,
): Record<string, string> {
  return Object.fromEntries(
    fields.map((field) => [
      field.key,
      configValues?.[field.key] ??
        field.defaultValue ??
        field.options?.[0]?.value ??
        "",
    ]),
  );
}

export function channelValuesForSubmit(
  fields: ChannelConfigField[],
  values: Record<string, string>,
  touchedFields: Set<string>,
  clearedSecrets: Set<string> = new Set(),
): Record<string, string | null> {
  const payload: Record<string, string | null> = {};
  for (const field of fields) {
    if (field.secret && clearedSecrets.has(field.key)) {
      payload[field.key] = null;
      continue;
    }
    if (!touchedFields.has(field.key)) continue;
    const value = channelFieldValue(field, values);
    if (field.secret && !value.trim()) continue;
    payload[field.key] = value;
  }
  return payload;
}
