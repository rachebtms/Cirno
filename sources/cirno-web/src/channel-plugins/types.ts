import type { ComponentType } from "react";

import type { ChannelPresentation } from "@/channel-plugins/catalog";
import type {
  CirnoFeatureInfo,
  CirnoFeaturesPayload,
} from "@/lib/types";

export type ChannelFeatureActionOptions = {
  confirmed?: boolean;
  installOnly?: boolean;
};

export type ChannelFeatureAction = (
  action: "enable" | "disable",
  name: string,
  options?: ChannelFeatureActionOptions,
) => void;

export type ChannelPluginPanelProps = {
  connectRequestId?: number;
  token: string;
  feature: CirnoFeatureInfo;
  actionKey: string | null;
  showBrandLogos: boolean;
  onAction: ChannelFeatureAction;
  onFeaturesUpdate: (payload: CirnoFeaturesPayload) => void;
  onConfigureMcp?: (name: string) => void;
  onBeforeCloseChange?: (handler: (() => Promise<boolean>) | null) => void;
};

export type ChannelPluginConnectFlowProps = {
  token: string;
  feature: CirnoFeatureInfo;
  idleLabel?: string;
  connectRequestId?: number;
  onOpenAdvanced?: () => void;
  onFeaturesUpdate: (payload: CirnoFeaturesPayload) => void;
};

export type ChannelPluginHelpProps = {
  feature: CirnoFeatureInfo;
};

export type ChannelUiContribution = {
  presentation: ChannelPresentation;
  aliases?: Record<string, Partial<ChannelPresentation>>;
  Panel?: ComponentType<ChannelPluginPanelProps>;
  HelpContent?: ComponentType<ChannelPluginHelpProps>;
  ConnectFlow?: ComponentType<ChannelPluginConnectFlowProps>;
  canConnectBeforeConfigured?: boolean;
};

export type RegisteredChannelUiContribution = {
  channel: string;
  webui: string;
  contribution: ChannelUiContribution;
};
