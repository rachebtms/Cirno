import { useRef } from "react";
import { ApiError } from "@/lib/api";
import type { ModelSettingsActionsOptions } from "../../modelOperations";
export function usePresetEditContext({
  state,
  settings,
  t,
  setError,
}: ModelSettingsActionsOptions) {
  const { modelPresetEditingId, setModelPresetNameError } = state;
  const latestSettings = useRef(settings);
  latestSettings.current = settings;
  // Queued edits remain attached to the configuration selected when they began.
  const editTargetSequence = useRef(0);
  const editTargetRef = useRef({ id: modelPresetEditingId, identity: 0 });
  if (editTargetRef.current.id !== modelPresetEditingId) {
    editTargetSequence.current += 1;
    editTargetRef.current = {
      id: modelPresetEditingId,
      identity: editTargetSequence.current,
    };
  }
  const editTarget = editTargetRef.current;

  const presetNameConflict = (name: string, currentName?: string) => {
    const normalized = name.toLowerCase();
    return (
      latestSettings.current?.model_presets.some(
        (preset) =>
          !preset.is_default &&
          preset.id !== currentName &&
          preset.name.toLowerCase() === normalized,
      ) ?? false
    );
  };

  const showPresetNameConflict = () => {
    setModelPresetNameError(
      t("settings.models.presetNameDuplicate", {
        defaultValue: "A preset with this name already exists.",
      }),
    );
    setError(null);
  };

  const handlePresetSaveError = (reason: unknown) => {
    if (reason instanceof ApiError && reason.status === 409) {
      showPresetNameConflict();
      return;
    }
    setError((reason as Error).message);
  };

  return {
    latestSettings,
    editTarget,
    editTargetRef,
    presetNameConflict,
    showPresetNameConflict,
    handlePresetSaveError,
  };
}
export type PresetEditContext = ReturnType<typeof usePresetEditContext>;
