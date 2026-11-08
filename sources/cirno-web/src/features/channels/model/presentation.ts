import i18n, { type TFunction } from "i18next";
import {
  channelFieldMessageKey,
  channelTranslator,
} from "@/channel-plugins/i18n";
import { channelLocaleMessages } from "@/channel-plugins/locale-registry";
import {
  channelUiOwner,
  channelUiPresentation,
} from "@/channel-plugins/registry";
import type {
  ChannelConfigField,
  ChannelFieldPresentation,
  ChannelSetupPresentation,
} from "@/channel-plugins/catalog";
import { normalizeLocale } from "@/i18n/config";
import type { CirnoFeatureInfo } from "@/lib/contracts/channels";
export function channelSetup(
  feature: CirnoFeatureInfo,
  locale = "en",
): ChannelSetupPresentation {
  const definition = channelUiPresentation(feature.name, feature.webui)?.setup;
  const owner = channelUiOwner(feature.name);
  const messages = channelLocaleMessages(owner, normalizeLocale(locale));
  const setupMessages = messages?.setup;
  const localizeField = (key: string): ChannelConfigField => {
    const copy =
      setupMessages?.fields?.[channelFieldMessageKey(feature.name, key)];
    return {
      key,
      label: copy?.label ?? fieldLabel(key.split(".").at(-1) ?? key),
      placeholder: copy?.placeholder,
    };
  };
  const localizePresentedField = (
    field: ChannelFieldPresentation,
  ): ChannelConfigField => ({
    ...localizeField(field.key),
    section: field.section,
    control: field.control,
  });
  const presentation: ChannelSetupPresentation = {
    ...definition,
    privacyNotice: setupMessages?.privacyNotice,
    primaryActionLabel: setupMessages?.primaryAction,
    docsLabel: setupMessages?.docsLabel,
    officialLabel: setupMessages?.officialLabel,
    presetLabel: setupMessages?.presetLabel,
    sectionLabels: setupMessages?.sections,
    fields: definition?.fields?.map(localizePresentedField),
    manualFields: definition?.manualFields?.map(localizePresentedField),
    actions: definition?.actions?.map((action) => ({
      ...action,
      label: setupMessages?.actions?.[action.id] ?? fieldLabel(action.id),
    })),
    presets: definition?.presets?.map((preset) => ({
      ...preset,
      label: setupMessages?.presets?.[preset.id] ?? fieldLabel(preset.id),
    })),
  };
  const contract = feature.setup;
  if (!contract) return presentation;

  const primaryFields = new Map(
    (presentation.fields ?? []).map((field) => [field.key, field]),
  );
  const manualFields = new Map(
    (presentation.manualFields ?? []).map((field) => [field.key, field]),
  );
  const authoritativeFields = contract.fields.map(
    (field): ChannelConfigField => {
      const local = primaryFields.get(field.key) ?? manualFields.get(field.key);
      const copy = local ?? localizeField(field.key);
      const choiceLabels =
        setupMessages?.fields?.[channelFieldMessageKey(feature.name, field.key)]
          ?.choices ?? {};
      const choices =
        field.kind === "bool"
          ? field.inheritable
            ? ["", "true", "false"]
            : ["true", "false"]
          : field.choices;
      return {
        ...copy,
        key: field.key,
        label: copy.label,
        section: copy.section ?? (field.required ? "credentials" : "advanced"),
        secret: field.kind === "secret",
        optional: !field.required,
        kind: field.kind,
        inputType: channelFieldInputType(field.field, field.kind),
        defaultValue: field.default_value,
        options:
          field.kind === "enum" || field.kind === "bool"
            ? choices.map((choice) => ({
                value: choice,
                label:
                  choiceLabels[choice] ??
                  (choice === ""
                    ? i18n.t("settings.values.default", {
                        lng: locale,
                        ns: "common",
                      })
                    : fieldLabel(choice)),
              }))
            : undefined,
      };
    },
  );
  const manualKeys = new Set(manualFields.keys());
  const fields = authoritativeFields.filter(
    (field) => !manualKeys.has(field.key),
  );
  const manual = authoritativeFields.filter((field) =>
    manualKeys.has(field.key),
  );

  return {
    ...presentation,
    officialUrl: contract.official_url,
    officialLabel:
      presentation.officialLabel ??
      (contract.official_url ? "Open official setup" : undefined),
    requirements: contract.requirements,
    fields: fields.length ? fields : undefined,
    manualFields: manual.length ? manual : undefined,
  };
}

function channelFieldInputType(
  field: string,
  kind: string,
): ChannelConfigField["inputType"] {
  if (kind === "int" || kind === "float") return "number";
  const normalized = field.toLowerCase();
  if (normalized.includes("url")) return "url";
  if (normalized.includes("email") || normalized.includes("address"))
    return "email";
  if (normalized.includes("phone")) return "tel";
  return undefined;
}

function fieldLabel(value: string): string {
  const spaced = value
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .trim();
  return spaced ? spaced[0].toUpperCase() + spaced.slice(1) : value;
}

function channelDisplayName(feature: CirnoFeatureInfo): string {
  return (
    channelUiPresentation(feature.name, feature.webui)?.displayName ??
    feature.display_name
  );
}

export function localizedChannelDisplayName(
  feature: CirnoFeatureInfo,
  t: TFunction,
): string {
  const fallback = channelDisplayName(feature);
  return channelTranslator(t, channelUiOwner(feature.name))(
    "displayName",
    fallback,
  );
}
