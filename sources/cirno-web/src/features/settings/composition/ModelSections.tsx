import { ModelsSettings } from "../models/ModelsSettings";
import { ProvidersOverview } from "../providers/ProvidersOverview";
import type { SectionRenderer, SectionRenderers } from "./contracts";
import type { SettingsComposition } from "./useSettingsComposition";

export function createModelSections(bindings: SettingsComposition): SectionRenderers {
  const { controller, modelState, modelActions, error, displayPreferences, modelDirty, settings, token, selectSection, renderProviderPanel, openProviderPanel, presetDeletedCallback } = bindings;
  if (!settings) return {};
  const renderProviders: SectionRenderer = () => {
    return <div className="settings-stack">
      <ProvidersOverview restoreFocus={bindings.providerFocus} onFocusRestored={bindings.consumeProviderFocus} onSettingsChange={(payload) => controller.applyPayload(payload, { preserveAgentForm: true, preserveCapabilityForms: true })} providers={settings.providers} showBrandLogos={displayPreferences.brandLogos}
        onAdd={(trigger) => openProviderPanel({ kind: "add", origin: "providers" }, trigger)}
        onEdit={(provider, trigger) => {
          modelActions.resetProviderDraft(provider);
          openProviderPanel({ kind: "edit", provider, origin: "providers" }, trigger);
        }} />
      {renderProviderPanel()}
    </div>;
  };

  const renderModels: SectionRenderer = () => {
    return (
      <div className="settings-stack">
        <ModelsSettings
          editCompletion={controller.modelEdits}
          token={token}
          form={modelState.form}
          setForm={modelState.setForm}
          editingPresetId={modelState.modelPresetEditingId}
          presetNameError={modelState.modelPresetNameError}
          error={error}
          settings={settings}
          dirty={modelDirty}
          creating={modelState.modelPresetCreating}
          creatingSaving={modelState.modelConfigurationSaving}
          callOrder={modelState.modelCallOrder}
          saving={modelState.saving}
          orderSaving={modelState.modelCallOrderSaving || modelState.modelConfigurationSaving}
          showBrandLogos={displayPreferences.brandLogos}
          providerSaving={controller.providerAuthorization.operation?.action === "login" ? controller.providerAuthorization.operation.provider : null}
          onChangeCallOrder={modelActions.changeModelCallOrder}
          onProviderOAuthLogin={(provider) => controller.providerAuthorization.login(provider)}
          onAddProvider={(trigger, onAdded) => openProviderPanel({ kind: "add" }, trigger, onAdded)}
          onConfigureProvider={(provider, trigger) => {
            modelActions.resetProviderDraft(provider);
            openProviderPanel({ kind: "edit", provider }, trigger);
          }}
          onManageProviders={() => selectSection("providers")}
          onSave={modelActions.saveModelSettings}
          onSaveRequestSettings={modelActions.saveModelRequestSettings}
          onBeginCreate={modelActions.beginModelPresetCreation}
          onCancelCreate={modelActions.cancelModelPresetCreation}
          onClearPresetNameError={() => modelState.setModelPresetNameError(null)}
          onSelectConfiguration={(name) => {
            modelState.setModelPresetCreating(false);
            modelState.setModelPresetEditingId(name);
            modelState.setModelPresetNameError(null);
            modelState.modelPresetBeforeCreateRef.current = null;
          }}
          onDeleteConfiguration={(preset, onDeleted) => {
            presetDeletedCallback.current = onDeleted;
            modelState.setModelPresetPendingDelete(preset);
          }}
        />
        {renderProviderPanel()}
      </div>
    );
  };

  return {
    "providers": renderProviders,
    "models": renderModels,
  };
}
