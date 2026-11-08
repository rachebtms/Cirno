import { Alert } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type {
  ChannelConfigField,
  ChannelSetupRequirement,
} from "@/channel-plugins/catalog";
import type { ChannelFieldsProps } from "./contracts";
import { ChannelFields } from "./ChannelFields";
const sections = [
  "account",
  "credentials",
  "connection",
  "access",
  "behavior",
  "security",
  "advanced",
];
type Props = Omit<ChannelFieldsProps, "fields"> & {
  fields: ChannelConfigField[];
  requirements: ChannelSetupRequirement[];
  sectionLabels?: Record<string, string>;
};
export function ChannelFieldGroups({
  fields,
  requirements,
  sectionLabels,
  ...form
}: Props) {
  const { t } = useTranslation(),
    groups = new Map<string, ChannelConfigField[]>(),
    labels = new Map(fields.map((field) => [field.key, field.label]));
  for (const field of fields) {
    const section = field.section ?? "credentials";
    groups.set(section, [...(groups.get(section) ?? []), field]);
  }
  const order = [
    ...sections,
    ...[...groups.keys()].filter((section) => !sections.includes(section)),
  ];
  return (
    <div className="channel-field-groups">
      {requirements
        .filter((requirement) => requirement.alternatives.length > 1)
        .map((requirement, index) => (
          <Alert key={index}>
            <Alert.Content>
              <Alert.Title>
                {t("settings.channels.chooseCredentialMethod")}
              </Alert.Title>
              <Alert.Description className="channel-credential-alternatives">
                {requirement.alternatives.map((alternative, position) => (
                  <span key={alternative.join("|")}>
                    {position > 0 && <span>{t("settings.channels.or")} </span>}
                    {alternative
                      .map((key) => labels.get(key) ?? key.split(".").at(-1))
                      .join(" + ")}
                  </span>
                ))}
              </Alert.Description>
            </Alert.Content>
          </Alert>
        ))}
      {order.map((section) => {
        const group = groups.get(section);
        return group?.length ? (
          <fieldset key={section} className="channel-field-group">
            <legend className={groups.size === 1 ? "sr-only" : undefined}>
              {sectionLabels?.[section] ??
                t(`settings.channels.sections.${section}`, {
                  defaultValue: section
                    .replace(/[_-]+/g, " ")
                    .replace(/^./, (letter) => letter.toUpperCase()),
                })}
            </legend>
            <ChannelFields fields={group} {...form} />
          </fieldset>
        ) : null;
      })}
    </div>
  );
}
