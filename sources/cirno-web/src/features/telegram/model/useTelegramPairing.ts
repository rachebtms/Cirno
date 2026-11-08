import { useCallback, useEffect, useState } from "react";
import { usePageVisibility } from "@/hooks/usePageVisibility";
import type { TelegramPin } from "@/lib/contracts/telegram";
import { useMutation } from "@/ui/resources/useMutation";
import type { TelegramBindingState } from "./useTelegramBinding";
import type { TelegramService } from "./service";
export function useTelegramPairing(binding: TelegramBindingState) {
  const { service, refresh } = binding;
  const operation = useMutation(service),
    visible = usePageVisibility();
  const { run } = operation;
  const [challenge, setChallenge] = useState<{
    service: TelegramService;
    pin: TelegramPin;
  } | null>(null);
  const [pollEpoch, setPollEpoch] = useState(0);
  const pin = challenge?.service === service ? challenge.pin : null;
  const issue = useCallback(
    () => run(service.pin, (pin) => setChallenge({ service, pin })),
    [service, run],
  );
  useEffect(() => {
    if (binding.status.value?.bound) setChallenge(null);
  }, [binding.status.value?.bound]);
  useEffect(() => {
    if (
      !pin ||
      !visible ||
      operation.busy ||
      operation.error ||
      binding.mutation.busy
    )
      return;
    let disposed = false,
      timer: number;
    const poll = async () => {
      const value = await refresh();
      if (disposed || !value) return;
      if (value.bound) {
        setChallenge(null);
        return;
      }
      if (Date.now() >= pin.expires_at) {
        await issue();
        return;
      }
      timer = window.setTimeout(() => {
        void poll();
      }, 1000);
    };
    timer = window.setTimeout(() => {
      void poll();
    }, 1000);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [
    pin,
    visible,
    operation.busy,
    operation.error,
    binding.mutation.busy,
    refresh,
    issue,
    pollEpoch,
  ]);
  return {
    pin,
    operation,
    issue,
    retryStatus: () => {
      if (pin) setPollEpoch((value) => value + 1);
      else void refresh();
    },
    disconnect: async () => {
      const value = await binding.unbind();
      if (value) setChallenge(null);
    },
  };
}
export type TelegramPairingState = ReturnType<typeof useTelegramPairing>;
