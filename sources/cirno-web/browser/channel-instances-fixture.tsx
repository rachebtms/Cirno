import { useMemo, useRef, useState } from "react";
import { ChannelsSettings } from "@/features/channels/ChannelsSettings";
import { useTheme } from "@/hooks/useTheme";
import { ClientProvider } from "@/providers/ClientProvider";
import type {
  CirnoFeatureInfo,
  CirnoFeaturesPayload,
} from "@/lib/contracts/channels";
import type { CirnoClient } from "@/lib/cirno-client";
const key = "channels.multiplugin.region";
const feature: CirnoFeatureInfo = {
  name: "multiplugin",
  display_name: "Research connections",
  type: "channel",
  enabled: true,
  runtime_status: "running",
  configured: true,
  installed: true,
  ready: true,
  status: "enabled",
  install_supported: true,
  requires_restart: false,
  setup: {
    fields: [
      {
        key,
        field: "region",
        kind: "enum",
        choices: ["eu", "us"],
        required: false,
      },
    ],
  },
  instances: [
    {
      id: "first",
      name: "Worker A",
      configured: true,
      enabled: true,
      runtime_status: "running",
      config_values: { [key]: "eu" },
      configured_fields: [],
    },
    {
      id: "second",
      name: "Worker B",
      configured: true,
      enabled: false,
      runtime_status: "stopped",
      config_values: { [key]: "us" },
      configured_fields: [],
    },
  ],
};
export function ChannelInstancesFixture() {
  useTheme();
  const [data, setData] = useState<CirnoFeaturesPayload>({
      features: [feature],
      enabled_count: 1,
    }),
    [writes, setWrites] = useState<unknown[]>([]);
  const remote = useRef(data),
    counts = useRef({ save: 0, toggle: 0 });
  const client = useMemo(
    () =>
      ({
        requestMutation: async <T,>(
          action: string,
          payload: Record<string, unknown>,
        ) => {
          setWrites((previous) => [...previous, { action, payload }]);
          await new Promise((resolve) => setTimeout(resolve, 40));
          const save = action === "settings.channel.configure";
          if (save && ++counts.current.save === 1)
            throw new Error("Fixture instance save rejected");
          if (!save && ++counts.current.toggle === 1)
            throw new Error("Fixture instance toggle rejected");
          if (
            !save &&
            !["settings.feature.enable", "settings.feature.disable"].includes(
              action,
            )
          )
            throw new Error(`Unknown fixture action ${action}`);
          const next = {
            features: [
              {
                ...remote.current.features[0],
                instances: remote.current.features[0].instances!.map(
                  (instance) =>
                    instance.id === payload.instance_id
                      ? save
                        ? {
                            ...instance,
                            config_values: {
                              ...instance.config_values,
                              ...(payload.values as Record<string, string>),
                            },
                          }
                        : {
                            ...instance,
                            enabled: action === "settings.feature.enable",
                            runtime_status:
                              action === "settings.feature.enable"
                                ? "running"
                                : "stopped",
                          }
                      : instance,
                ),
              },
            ],
            enabled_count: 1,
          };
          remote.current = next;
          return (
            save
              ? { name: "multiplugin", saved: true, cirno_features: next }
              : next
          ) as T;
        },
      }) as CirnoClient,
    [],
  );
  return (
    <ClientProvider client={client} token="fixture">
      <main className="min-h-screen bg-background p-4 text-foreground sm:p-8">
        <div className="mx-auto max-w-4xl">
          <h1 className="mb-6 text-xl font-semibold">Research connections</h1>
          <ChannelsSettings
            token="fixture"
            cirnoFeatures={data}
            loading={false}
            actionKey={null}
            showBrandLogos={false}
            error={null}
            requiresRestartPending={false}
            onAction={() => {
              throw new Error("Unexpected catalog action");
            }}
            onFeaturesUpdate={setData}
            onDismissStatus={() => {}}
          />
          <output hidden data-testid="instance-writes">
            {JSON.stringify(writes)}
          </output>
        </div>
      </main>
    </ClientProvider>
  );
}
