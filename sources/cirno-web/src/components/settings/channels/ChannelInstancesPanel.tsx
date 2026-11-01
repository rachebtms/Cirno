import type { ReactNode } from "react";

import {
  configureChannel,
  disableCirnoFeature,
  enableCirnoFeature,
} from "@/lib/api";
import type { CirnoChannelInstanceInfo, CirnoFeatureInfo, CirnoFeaturesPayload } from "@/lib/types";
import { useClient } from "@/providers/ClientProvider";
import {
  ChannelInstancesPanelView,
  type ChannelInstancesPanelCustomization,
  type ChannelInstancesPanelViewProps,
} from "./ChannelInstancesPanelView";

export type { ChannelInstancesPanelCustomization } from "./ChannelInstancesPanelView";

export function ChannelInstancesPanel({
  feature,
  showBrandLogos,
  instances,
  onFeaturesUpdate,
  customization,
  renderView,
}: {
  feature: CirnoFeatureInfo;
  showBrandLogos: boolean;
  instances?: CirnoChannelInstanceInfo[];
  onFeaturesUpdate: (payload: CirnoFeaturesPayload) => void;
  customization?: ChannelInstancesPanelCustomization;
  renderView?: (props: ChannelInstancesPanelViewProps) => ReactNode;
}) {
  const { client } = useClient();
  const viewProps: ChannelInstancesPanelViewProps = {
    feature,
    showBrandLogos,
    instances,
    customization,
    onToggleInstance: async (instance, checked) => {
      const payload = checked
        ? await enableCirnoFeature(client, feature.name, { instanceId: instance.id })
        : await disableCirnoFeature(client, feature.name, { instanceId: instance.id });
      onFeaturesUpdate(payload);
    },
    onSaveInstance: async (instance, values) => {
      const payload = await configureChannel(client, feature.name, values, {
        enable: instance.enabled,
        instanceId: instance.id,
      });
      if (payload.cirno_features) onFeaturesUpdate(payload.cirno_features);
    },
  };
  return renderView ? renderView(viewProps) : <ChannelInstancesPanelView {...viewProps} />;
}
