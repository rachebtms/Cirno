export interface ModelPresetOption {
  id: string;
  name?: string;
  contextWindowTokens?: number;
  reasoningEffort?: string | null;
  model?: string | null;
  provider?: string | null;
}

export interface ModelSelectorProps {
  label: string;
  modelDetail?: string | null;
  modelPreset?: string | null;
  modelPresets?: ModelPresetOption[];
  onPresetChange?: (id: string) => void;
  onManageModels?: () => void;
  onRequestComposerFocus?: () => void;
  provider?: string | null;
  providerLabel?: string | null;
  needsSetup?: boolean;
  attentionRequest?: number;
  onClick?: () => void;
}
