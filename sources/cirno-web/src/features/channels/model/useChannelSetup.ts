import { useEffect, useMemo, useState } from "react";
import type { ChannelSetupPresentation } from "@/channel-plugins/catalog";
import type {
  CirnoFeatureInfo,
  CirnoFeaturesPayload,
} from "@/lib/contracts/channels";
import { useClient } from "@/providers/ClientProvider";
import { useEditCompletion } from "@/features/settings/shared/useEditCompletion";
import { setupLayout } from "./setupLayout";
import { createChannelSetupService } from "./setupService";
import { useChannelDraft } from "./useChannelDraft";
import { useChannelActions } from "./useChannelActions";
import { useChannelIntent } from "./useChannelIntent";
export function useChannelSetup(
  feature: CirnoFeatureInfo,
  setup: ChannelSetupPresentation,
  onFeaturesUpdate: (payload: CirnoFeaturesPayload) => void,
  register?: (handler: (() => Promise<boolean>) | null) => void,
) {
  const { client } = useClient(),
    service = useMemo(
      () => createChannelSetupService(client, feature.name),
      [client, feature.name],
    );
  const layout = setupLayout(setup, feature),
    draft = useChannelDraft(service, layout.editable, feature.config_values);
  const [expanded, setExpanded] = useState<{
    service: typeof service;
    open: boolean;
  }>({ service, open: false });
  const showAdvanced = () => setExpanded({ service, open: true });
  const actions = useChannelActions(
    service,
    feature,
    setup,
    layout,
    draft,
    onFeaturesUpdate,
    showAdvanced,
  );
  const completion = useEditCompletion(
    draft.revision,
    draft.dirty,
    actions.save,
    true,
    feature.name,
  );
  const intent = useChannelIntent(service, actions, completion);
  useEffect(() => {
    register?.(
      draft.dirty || actions.mutation.busy || intent.busy
        ? () =>
            intent.busy || (actions.mutation.busy && actions.kind !== "save")
              ? Promise.resolve(false)
              : completion.commit()
        : null,
    );
    return () => register?.(null);
  }, [
    register,
    draft.dirty,
    actions.mutation.busy,
    actions.kind,
    intent.busy,
    completion.commit,
  ]);
  return {
    layout,
    draft,
    actions,
    intent,
    completion,
    advanced: {
      open: expanded.service === service && expanded.open,
      change: async (open: boolean) => {
        if (
          !open &&
          completion.needsCompletion() &&
          !(await completion.commit())
        )
          return;
        setExpanded({ service, open });
      },
    },
  };
}
export type ChannelSetupState = ReturnType<typeof useChannelSetup>;
