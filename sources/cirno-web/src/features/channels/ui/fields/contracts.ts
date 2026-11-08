import type { ChannelConfigField } from "@/channel-plugins/catalog";
export type ChannelFieldsProps = {
  fields: ChannelConfigField[];
  values: Record<string, string>;
  configuredFields?: Set<string>;
  visibleSecrets: Record<string, boolean>;
  onChange: (key: string, value: string) => void;
  onFieldBlur?: (key: string) => void;
  onToggleSecret: (key: string) => void;
  errors?: Record<string, string>;
  clearedSecrets?: Set<string>;
  onClearSecret?: (key: string, clear: boolean) => void;
  showSecretActions?: boolean;
  secretActionsDisabled?: boolean;
  disabled?: boolean;
};

export type ChannelFieldProps = Omit<ChannelFieldsProps, "fields"> & {
  field: ChannelConfigField;
};
