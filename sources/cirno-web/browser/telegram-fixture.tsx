import { Button } from "@heroui/react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { TelegramSettings } from "@/features/telegram/TelegramSettings";
import { useTheme } from "@/hooks/useTheme";
import type { TelegramBinding } from "@/lib/contracts/telegram";
import type { WebUIMutationTransport } from "@/lib/api";
export function TelegramFixture() {
  useTheme();
  const { t } = useTranslation();
  const [actions, setActions] = useState<{ action: string; values: unknown }[]>([]),
    [configured, setConfigured] = useState(false);
  const state = useMemo(() => {
    let data: TelegramBinding = {
      bound: false,
      enabled: true,
      notifications: ["router", "operations", "conversations", "system"],
      webui_url: "",
    };
    const calls = new Map<string, number>();
    const requestMutation = async <T,>(
      _method: string,
      { action, values }: { action: string; values: Record<string, unknown> },
    ) => {
      setActions((previous) => [...previous, { action, values }]);
      const count = (calls.get(action) ?? 0) + 1;
      calls.set(action, count);
      if (action === "telegram.status") {
        if (count === 1) throw new Error("Fixture Telegram status offline");
        return { ...data } as T;
      }
      if (action === "telegram.pin") {
        if (count === 1) throw new Error("Fixture PIN generation failed");
        return {
          pin: count === 2 ? "12345678" : "87654321",
          expires_at: Date.now() + 30000,
          ttl_seconds: 30,
        } as T;
      }
      if (action === "telegram.settings") {
        if (count === 1) throw new Error("Fixture Telegram settings failed");
        data = { ...data, ...values };
        return { ...data } as T;
      }
      if (action === "telegram.unbind") {
        if (count === 1) throw new Error("Fixture Telegram disconnect failed");
        data = { ...data, bound: false, username: undefined, user_id: undefined };
        return { ...data } as T;
      }
      throw new Error(`Unknown fixture action: ${action}`);
    };
    return {
      client: { requestMutation } as WebUIMutationTransport,
      verify: () => {
        data = { ...data, bound: true, username: "fixture_owner", user_id: "123" };
      },
    };
  }, []);
  return (
    <main className="min-h-screen bg-background p-4 text-foreground sm:p-8">
      <div className="mx-auto max-w-3xl">
        <h1 className="mb-6 text-xl font-semibold">{t("settings.nav.telegram")}</h1>
        <TelegramSettings client={state.client} onConfigure={() => setConfigured(true)} />
        <div className="mt-8">
          <Button variant="ghost" size="sm" onPress={state.verify}>
            Simulate Telegram verification
          </Button>
          {configured && <p>Fixture channel setup requested</p>}
        </div>
        <output hidden data-testid="telegram-actions">
          {JSON.stringify(actions)}
        </output>
      </div>
    </main>
  );
}
