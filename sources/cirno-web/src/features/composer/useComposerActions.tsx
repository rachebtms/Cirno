import { ComposerUsagePopover } from "@/components/thread/ComposerUsagePopover";
import { ModelSelector } from "@/features/model-selection/ModelSelector";

import type { ComponentInputs } from "./inputs";
import type { useComposerQueues } from "./useComposerQueues";
import type { useComposerState } from "./useComposerState";

export function useComposerActions({
  inputs,
  composerState,
  composerQueues,
}: {
  inputs: ComponentInputs;
  composerState: ReturnType<typeof useComposerState>;
  composerQueues: ReturnType<typeof useComposerQueues>;
}) {
  const {
    modelLabel,
    modelDetail,
    modelPreset,
    modelPresets,
    onModelPresetChange,
    onManageModels,
    modelProvider,
    modelProviderLabel,
    modelNeedsSetup,
    onModelBadgeClick,
    showContextUsage,
    contextUsage,
    contextUsageError,
    recentRoundUsage,
    isStreaming,
  } = inputs;
  const {
    textareaRef,
    modelSetupAttentionRequest,
    compactControls,
    mobileWorkspaceControls,
  } = composerState;
  const { showAnyPalette, slashPaletteLayout } = composerQueues;
  const modelControl = modelLabel ? (
    <ModelSelector
      label={modelLabel}
      modelDetail={modelDetail}
      modelPreset={modelPreset}
      modelPresets={modelPresets}
      onPresetChange={onModelPresetChange}
      onManageModels={onManageModels}
      onRequestComposerFocus={() => textareaRef.current?.focus()}
      provider={modelProvider}
      providerLabel={modelProviderLabel}
      needsSetup={modelNeedsSetup}
      attentionRequest={modelSetupAttentionRequest}
      onClick={modelNeedsSetup ? onModelBadgeClick : undefined}
    />
  ) : null;
  const usageInMeta = mobileWorkspaceControls || compactControls;
  const usageControl =
    showContextUsage ||
      contextUsage ||
      contextUsageError ||
      recentRoundUsage.length ||
      isStreaming ? (
      <ComposerUsagePopover
        pending={isStreaming}
        error={contextUsageError}
        context={contextUsage}
        rounds={recentRoundUsage}
        showLabel={usageInMeta}
        compactLabel={mobileWorkspaceControls}
        bottomSheet={usageInMeta}
      />
    ) : null;
  const paletteBeside =
    showAnyPalette && slashPaletteLayout.placement === "beside";
  return {
    paletteBeside,
    modelControl,
    usageInMeta,
    usageControl,
  };
}
