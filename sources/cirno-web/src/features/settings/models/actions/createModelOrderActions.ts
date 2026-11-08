import { updateModelCallOrder, deleteModelConfiguration } from "@/lib/api";
import type { ModelSettingsActionsOptions } from "../../modelOperations";
export function createModelOrderActions({
  state,
  settings,
  client,
  applyPayload,
  setError,
  onModelNameChange,
}: ModelSettingsActionsOptions) {
  const {
    modelCallOrder,
    modelCallOrderSaving,
    modelConfigurationSaving,
    modelPresetPendingDelete,
    saving,
    setModelCallOrder,
    setModelCallOrderSaving,
    setSaving,
    setModelPresetPendingDelete,
  } = state;
  const changeModelCallOrder = async (nextOrder: string[]) => {
    const unchanged =
      nextOrder.length === modelCallOrder.length &&
      nextOrder.every((name, index) => name === modelCallOrder[index]);
    if (
      !settings ||
      saving ||
      modelCallOrderSaving ||
      modelConfigurationSaving ||
      nextOrder.length === 0 ||
      unchanged
    ) {
      return;
    }
    const previousOrder = [...modelCallOrder];
    setModelCallOrder(nextOrder);
    setModelCallOrderSaving(true);
    try {
      const payload = await updateModelCallOrder(client, nextOrder);
      applyPayload(payload, {
        preserveAgentForm: true,
        preserveCapabilityForms: true,
      });
      onModelNameChange(payload.agent.model || null);
      setError(null);
    } catch (err) {
      setModelCallOrder(previousOrder);
      setError((err as Error).message);
    } finally {
      setModelCallOrderSaving(false);
    }
  };

  const handleDeleteModelConfiguration = async () => {
    if (!modelPresetPendingDelete || saving || modelCallOrderSaving || modelConfigurationSaving) {
      return false;
    }
    setSaving(true);
    try {
      const payload = await deleteModelConfiguration(client, modelPresetPendingDelete.id);
      applyPayload(payload, { preserveCapabilityForms: true });
      setModelPresetPendingDelete(null);
      setError(null);
      return true;
    } catch (err) {
      setError((err as Error).message);
      return false;
    } finally {
      setSaving(false);
    }
  };

  return { changeModelCallOrder, handleDeleteModelConfiguration };
}
