import type { WebUIMutationTransport } from "@/lib/api";
import type {
  TelegramBinding,
  TelegramPin,
  TelegramPreferences,
} from "@/lib/contracts/telegram";
export function createTelegramService(client: WebUIMutationTransport) {
  const action = <T>(name: string, values = {}) =>
    client.requestMutation<T>("instance.action", {
      action: `telegram.${name}`,
      values,
    });
  return {
    status: () => action<TelegramBinding>("status"),
    pin: () => action<TelegramPin>("pin"),
    update: (values: TelegramPreferences) =>
      action<TelegramBinding>("settings", values),
    unbind: () => action<TelegramBinding>("unbind"),
  };
}
export type TelegramService = ReturnType<typeof createTelegramService>;
