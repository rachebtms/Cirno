import type { ReactNode } from "react";
import type {
  ChannelConfigField,
  ChannelProviderPreset,
  ChannelSetupPresentation,
} from "@/channel-plugins/catalog";
import type {
  ChannelValidationPayload,
  CirnoFeatureInfo,
} from "@/lib/contracts/channels";
export interface ChannelSetupViewProps {
  header: ReactNode;
  feature: CirnoFeatureInfo;
  setup: ChannelSetupPresentation;
  primaryFields: ChannelConfigField[];
  advancedFields: ChannelConfigField[];
  savedSecretFields: ChannelConfigField[];
  availablePresets: ChannelProviderPreset[];
  configuredFields: Set<string>;
  fieldValues: Record<string, string>;
  visibleSecrets: Record<string, boolean>;
  clearedSecrets: Set<string>;
  fieldErrors: Record<string, string>;
  actionPending: boolean;
  dirty: boolean;
  enabled: boolean;
  autoSaving: boolean;
  autoSaveState: "idle" | "saved";
  advancedOpen: boolean;
  validation: ChannelValidationPayload | null;
  validating: boolean;
  notice: string | null;
  noticeTone?: "danger" | "success" | "info";
  connectFlow?: ReactNode;
  onAdvancedOpenChange: (open: boolean) => void;
  onChangeField: (key: string, value: string) => void;
  onToggleSecret: (key: string) => void;
  onClearSecret: (key: string, clear: boolean) => void;
  onApplyPreset: (preset: ChannelProviderPreset) => void;
  onSubmit: () => void;
  onCheckConnection: () => void;
  onToggleEnabled: (enabled: boolean) => void;
  onCopyCommand: () => void;
  onNotice: (notice: string | null) => void;
}
