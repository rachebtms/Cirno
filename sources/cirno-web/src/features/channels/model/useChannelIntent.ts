import { useRef, useState } from "react";
import { useMutation } from "@/ui/resources/useMutation";
import type { EditCompletion } from "@/features/settings/shared/useEditCompletion";
import type { ChannelActions } from "./useChannelActions";
import type { ChannelSetupService } from "./setupService";

type Intent = "check" | "enable" | "disable";

/** A manual action follows the credential save started by leaving its input. */
export function useChannelIntent(
  service: ChannelSetupService,
  actions: ChannelActions,
  completion: EditCompletion,
) {
  const mutation = useMutation(service),
    latest = useRef({ service, actions, completion });
  latest.current = { service, actions, completion };
  const [pending, setPending] = useState({ service, kind: null as Intent | null });
  const perform = (kind: Intent) =>
    mutation.run(
      async () => {
        setPending({ service, kind });
        const saved = await completion.commit(),
          current = latest.current;
        if (
          current.service !== service ||
          !current.actions.isCurrent() ||
          (!saved && kind !== "disable")
        )
          return;
        return kind === "check"
          ? current.actions.check()
          : current.actions.toggle(kind === "enable");
      },
      () => {},
    );
  return {
    busy: mutation.busy,
    error: mutation.error,
    kind: mutation.busy && pending.service === service ? pending.kind : null,
    check: () => perform("check"),
    toggle: (enabled: boolean) => perform(enabled ? "enable" : "disable"),
  };
}
