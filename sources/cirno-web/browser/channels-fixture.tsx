import { Button } from "@heroui/react";
import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChannelsSettings } from "@/features/channels/ChannelsSettings";
import { useTheme } from "@/hooks/useTheme";
import { ClientProvider } from "@/providers/ClientProvider";
import type {
  CirnoFeaturesPayload,
  CirnoFeatureInfo,
} from "@/lib/contracts/channels";
import type { CirnoClient } from "@/lib/cirno-client";
const base: CirnoFeatureInfo = {
  name: "telegram",
  display_name: "Telegram",
  type: "channel",
  enabled: false,
  installed: true,
  ready: true,
  status: "not_enabled",
  install_supported: true,
  requires_restart: false,
};
const initial: CirnoFeaturesPayload = {
  features: [
    {
      ...base,
      webui: "webui/index.ts",
      configured: false,
      setup: {
        verifies_connection: true,
        fields: [
          {
            key: "channels.telegram.token",
            field: "token",
            kind: "secret",
            choices: [],
            required: true,
          },
          {
            key: "channels.telegram.streamEditInterval",
            field: "streamEditInterval",
            kind: "float",
            choices: [],
            required: false,
            default_value: "0.6",
          },
        ],
        requirements: [{ alternatives: [["channels.telegram.token"]] }],
      },
    },
    {
      ...base,
      name: "websocket",
      display_name: "Cirno Web",
      webui: "webui/index.ts",
      enabled: true,
      runtime_status: "running",
      configured: true,
      capabilities: ["always_enabled"],
    },
    {
      ...base,
      name: "research-channel",
      display_name: "Research connection",
      installed: false,
      requires_dependencies: true,
      ready: false,
    },
  ],
  enabled_count: 1,
};
export function ChannelsFixture() {
  useTheme();
  const { t } = useTranslation();
  const [loading, setLoading] = useState(
    new URLSearchParams(location.search).has("loading"),
  );
  const [data, setData] = useState(initial),
    [error, setError] = useState<string | null>(null),
    [busy, setBusy] = useState<string | null>(null),
    [writes, setWrites] = useState<string[]>([]);
  const remote = useRef(initial),
    installs = useRef(0),
    saves = useRef(new URLSearchParams(location.search).has("accept-save") ? 1 : 0);
  const update = (payload: CirnoFeaturesPayload) => {
    remote.current = payload;
    setData(payload);
  };
  const client = useMemo(
    () =>
      ({
        requestMutation: async <T,>(action: string, args: Record<string, unknown>) => {
          setWrites((previous) => [...previous, action]);
          if (action === "settings.channel.validate")
            return { name: "telegram", status: "connected", can_enable: true, checks: [], missing_fields: [], requires_restart: false } as T;
          if (action === "settings.channel.configure") {
            if (new URLSearchParams(location.search).has("slow-save"))
              await new Promise((resolve) => setTimeout(resolve, 250));
            if (++saves.current === 1)
              throw new Error("Fixture channel draft save failed");
            const payload = {
              ...remote.current,
              features: remote.current.features.map((feature) =>
                feature.name === "telegram"
                  ? {
                      ...feature,
                      configured: true,
                      configured_fields: ["channels.telegram.token"],
                      enabled: args.enable === true || feature.enabled,
                      runtime_status: args.enable === true ? "running" : feature.runtime_status,
                    }
                  : feature,
              ),
            };
            remote.current = payload;
            return { cirno_features: payload } as T;
          }
          throw new Error(`Unknown fixture action: ${action}`);
        },
      }) as CirnoClient,
    [],
  );
  return (
    <ClientProvider client={client} token="fixture">
      <main className="min-h-screen bg-background p-4 text-foreground sm:p-8">
        <div className="mx-auto max-w-4xl">
          <h1 className="mb-6 text-xl font-semibold">
            {t("settings.nav.channels")}
          </h1>
          {loading && (
            <Button variant="secondary" onPress={() => setLoading(false)}>
              Finish catalog loading
            </Button>
          )}
          <ChannelsSettings
            token="fixture"
            cirnoFeatures={loading ? null : data}
            loading={loading}
            actionKey={busy}
            showBrandLogos={false}
            error={error}
            requiresRestartPending={false}
            onFeaturesUpdate={update}
            onDismissStatus={() => setError(null)}
            onAction={(_action, name) => {
              setBusy(`install:${name}`);
              setError(null);
              setWrites((previous) => [...previous, `install:${name}`]);
              void Promise.resolve().then(() => {
                if (++installs.current === 1)
                  setError("Fixture channel installation failed");
                else
                  update({
                    ...remote.current,
                    requires_restart: true,
                    features: remote.current.features.map((feature) =>
                      feature.name === name
                        ? { ...feature, installed: true, restart_pending: true }
                        : feature,
                    ),
                  });
                setBusy(null);
              });
            }}
            onRestart={() => {
              setWrites((previous) => [...previous, "restart"]);
              update({
                ...remote.current,
                requires_restart: false,
                features: remote.current.features.map((feature) => ({
                  ...feature,
                  restart_pending: false,
                })),
              });
            }}
          />
          <output data-testid="channel-writes" hidden>
            {JSON.stringify(writes)}
          </output>
        </div>
      </main>
    </ClientProvider>
  );
}
