import { useCallback, useEffect, useRef } from "react";
import { useRequest } from "@/ui/resources/useRequest";
import type { TelegramBinding } from "@/lib/contracts/telegram";
import type { TelegramService } from "./service";
interface Read {
  service: TelegramService;
  result: Promise<TelegramBinding | undefined>;
  next?: Promise<TelegramBinding | undefined>;
}
/** A wake or write can request one fresh read after an older status call finishes. */
export function useTelegramStatus(service: TelegramService) {
  const status = useRequest<TelegramBinding>(service),
    flight = useRef<Read | null>(null);
  const { load, isCurrent } = status;
  const refresh = useCallback(
    function refresh(): Promise<TelegramBinding | undefined> {
      if (!isCurrent()) return Promise.resolve(undefined);
      const previous = flight.current;
      if (previous?.service === service)
        return (previous.next ??= previous.result.then(refresh));
      const current: Read = { service, result: load(service.status) };
      flight.current = current;
      current.result = current.result.finally(() => {
        if (flight.current === current) flight.current = null;
      });
      return current.result;
    },
    [service, load, isCurrent],
  );
  useEffect(() => {
    void refresh();
  }, [refresh]);
  return { status, refresh };
}
