import type { ChannelFeatureAction } from "@/channel-plugins/types";
import type { CirnoFeaturesPayload } from "@/lib/contracts/channels";
export interface ChannelsSettingsProps {
  token: string;
  cirnoFeatures: CirnoFeaturesPayload | null;
  loading: boolean;
  actionKey: string | null;
  chatAppsDocsUrl?: string;
  showBrandLogos: boolean;
  error: string | null;
  requiresRestartPending: boolean;
  onAction: ChannelFeatureAction;
  onFeaturesUpdate: (payload: CirnoFeaturesPayload) => void;
  onDismissStatus: () => void;
  onConfigureMcp?: (name: string) => void;
  onBeforeCloseChange?: (handler: (() => Promise<boolean>) | null) => void;
  onRestart?: () => void;
  isRestarting?: boolean;
}
