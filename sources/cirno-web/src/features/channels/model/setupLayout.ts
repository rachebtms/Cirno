import type { ChannelSetupPresentation } from "@/channel-plugins/catalog";
import type { CirnoFeatureInfo } from "@/lib/contracts/channels";
export function setupLayout(
  setup: ChannelSetupPresentation,
  feature: CirnoFeatureInfo,
) {
  const mode = setup.mode ?? "credentials",
    fields = setup.fields ?? [],
    manual = setup.manualFields ?? [];
  const required = new Set(
    (setup.requirements ?? []).flatMap((requirement) =>
      requirement.alternatives.flat(),
    ),
  );
  const primary = fields.filter(
    (field) => !field.optional || required.has(field.key),
  );
  const advanced =
    mode === "connect"
      ? manual
      : fields.filter((field) => !primary.includes(field));
  return {
    mode,
    fields,
    primary,
    advanced,
    editable:
      mode === "credentials" ? fields : mode === "connect" ? manual : [],
    presets: feature.configured ? [] : (setup.presets ?? []),
  };
}
export type ChannelSetupLayout = ReturnType<typeof setupLayout>;
