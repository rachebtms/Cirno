import type { ModelSettingsActionsOptions } from "../modelOperations";
import { usePresetActions } from "./actions/usePresetActions";
import { createModelOrderActions } from "./actions/createModelOrderActions";
import { createProviderMutations } from "../providers/actions/createProviderMutations";
import { useProviderDraftActions } from "../providers/actions/useProviderDraftActions";

export function useModelSettingsActions(options: ModelSettingsActionsOptions) {
  const presets = usePresetActions(options),
    drafts = useProviderDraftActions(options);
  return {
    ...presets,
    ...createModelOrderActions(options),
    ...createProviderMutations(options),
    ...drafts,
  };
}
