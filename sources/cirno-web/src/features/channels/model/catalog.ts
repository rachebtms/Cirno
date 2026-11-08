import type { TFunction } from "i18next";
import type {
  CirnoFeatureInfo,
  CirnoFeaturesPayload,
} from "@/lib/contracts/channels";
import { localizedChannelDisplayName } from "@/features/channels/model/presentation";
export type ChannelFilter = "all" | "enabled";
export function channelCatalog(
  payload: CirnoFeaturesPayload | null,
  t: TFunction,
) {
  return (payload?.features ?? [])
    .filter(
      (feature) =>
        feature.type === "channel" && feature.settings_visible !== false,
    )
    .sort(
      (a, b) =>
        Number(!a.ready) - Number(!b.ready) ||
        localizedChannelDisplayName(a, t).localeCompare(
          localizedChannelDisplayName(b, t),
        ),
    );
}
export function defaultChannelFilter(
  channels: CirnoFeatureInfo[],
): ChannelFilter {
  return channels.some(
    (feature) =>
      feature.enabled && !feature.capabilities?.includes("always_enabled"),
  )
    ? "enabled"
    : "all";
}
export function channelGroups(
  channels: CirnoFeatureInfo[],
  query: string,
  filter: ChannelFilter,
  t: TFunction,
) {
  const text = query.trim().toLocaleLowerCase();
  const visible = channels.filter(
    (feature) =>
      (filter === "all" || feature.enabled) &&
      `${feature.name} ${localizedChannelDisplayName(feature, t)}`
        .toLocaleLowerCase()
        .includes(text),
  );
  return filter === "enabled"
    ? [
        {
          key: "enabled",
          label: t("settings.channels.filterEnabled"),
          channels: visible,
        },
      ].filter((group) => group.channels.length)
    : [
        {
          key: "builtin",
          label: t("settings.channels.noInstallNeeded"),
          channels: visible.filter((feature) => !feature.requires_dependencies),
        },
        {
          key: "dependencies",
          label: t("settings.channels.installNeeded"),
          channels: visible.filter((feature) => feature.requires_dependencies),
        },
      ].filter((group) => group.channels.length);
}
