import { useMemo, useState } from "react";
import type { WebUIMutationTransport } from "@/lib/api";
import type { TelegramPreferences } from "@/lib/contracts/telegram";
import { useTelegramStatus } from "./useTelegramStatus";
import { useMutation } from "@/ui/resources/useMutation";
import { createTelegramService } from "./service";
export type TelegramArea = "account" | "delivery" | "links";
export function useTelegramBinding(client: WebUIMutationTransport) {
  const service = useMemo(() => createTelegramService(client), [client]);
  const { status, refresh } = useTelegramStatus(service),
    mutation = useMutation(service);
  const [area, setArea] = useState<TelegramArea>("account");
  const { assign } = status;
  return {
    service,
    status,
    mutation,
    refresh,
    errorFor: (target: TelegramArea) =>
      area === target ? mutation.error : null,
    update: (values: TelegramPreferences, target: TelegramArea) =>
      mutation.run(() => {
        setArea(target);
        return service.update(values);
      }, assign),
    unbind: () =>
      mutation.run(() => {
        setArea("account");
        return service.unbind();
      }, assign),
  };
}
export type TelegramBindingState = ReturnType<typeof useTelegramBinding>;
