import { useEffect, useMemo, useState } from "react";
import { useClient } from "@/providers/ClientProvider";
import { useMutation } from "@/ui/resources/useMutation";
import {
  configureChannel,
  enableCirnoFeature,
  disableCirnoFeature,
} from "@/lib/api";
import type {
  CirnoChannelInstanceInfo,
  CirnoFeatureInfo,
  CirnoFeaturesPayload,
} from "@/lib/contracts/channels";
import { useChannelSelection } from "./useChannelSelection";
export function useChannelInstances(
  feature: CirnoFeatureInfo,
  onUpdate: (payload: CirnoFeaturesPayload) => void,
  register?: (handler: (() => Promise<boolean>) | null) => void,
) {
  const { client } = useClient(),
    owner = useMemo(
      () => ({ client, name: feature.name }),
      [client, feature.name],
    );
  const mutation = useMutation(owner),
    selection = useChannelSelection(owner);
  const [pending, setPending] = useState<{
    owner: unknown;
    id: string;
    kind: "toggle" | "save";
    checked?: boolean;
  } | null>(null);
  const operation = pending?.owner === owner && mutation.busy ? pending : null;
  useEffect(() => {
    register?.(() =>
      operation?.kind === "toggle"
        ? Promise.resolve(false)
        : selection.close().then(Boolean),
    );
    return () => register?.(null);
  }, [register, operation, selection.close]);
  return {
    owner,
    mutation,
    selection,
    operation,
    edit: async (id: string) => {
      if (selection.selected?.name === id) {
        await selection.close();
        return;
      }
      if (!selection.selected || (await selection.close()))
        selection.select(id);
    },
    toggle: (instance: CirnoChannelInstanceInfo, checked: boolean) =>
      mutation.run(async () => {
        setPending({ owner, id: instance.id, kind: "toggle", checked });
        return checked
          ? enableCirnoFeature(client, feature.name, {
              instanceId: instance.id,
            })
          : disableCirnoFeature(client, feature.name, {
              instanceId: instance.id,
            });
      }, onUpdate),
    save: (
      instance: CirnoChannelInstanceInfo,
      values: Record<string, string | null>,
    ) =>
      mutation.run(
        async () => {
          setPending({ owner, id: instance.id, kind: "save" });
          return configureChannel(client, feature.name, values, {
            enable: instance.enabled,
            instanceId: instance.id,
          });
        },
        (payload) => {
          if (payload.cirno_features) onUpdate(payload.cirno_features);
        },
      ),
  };
}
export type ChannelInstancesState = ReturnType<typeof useChannelInstances>;
