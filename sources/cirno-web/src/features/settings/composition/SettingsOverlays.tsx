import type { RefObject } from "react";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import type { SettingsController } from "../useSettingsController";
import { ModelPresetDeleteDialog } from "../models/ModelPresetDeleteDialog";
import { ProviderOAuthLoginDialog } from "../providers/ProviderOAuthLoginDialog";
import { CirnoFeatureInstallDialog } from "../shared/SettingsControls";
import { AutomationDeleteDialog, AutomationEditDialog } from "@/features/automations";

export function SettingsOverlays({ controller, presetDeletedCallback, onAutomationReturn: setAutomationDetailReturn }: {
  controller: SettingsController; presetDeletedCallback: RefObject<(() => void) | null>;
  onAutomationReturn: (job: SessionAutomationJob | null) => void;
}) {
  const { settings, modelState, modelActions, systemState, systemActions, remoteBrowserAccess, providerAuthorization } = controller;
  const providerOAuthFlow = providerAuthorization.flow;
  return <>
    <ModelPresetDeleteDialog
      preset={modelState.modelPresetPendingDelete}
      deleting={modelState.saving}
      onOpenChange={(open) => {
        if (!open) {
          modelState.setModelPresetPendingDelete(null);
          presetDeletedCallback.current = null;
        }
      }}
      onConfirm={async () => {
        if (await modelActions.handleDeleteModelConfiguration()) {
          presetDeletedCallback.current?.();
          presetDeletedCallback.current = null;
        }
      }}
    />

    <ProviderOAuthLoginDialog
      flow={providerOAuthFlow}
      providerLabel={
        providerOAuthFlow
          ? settings?.providers.find((provider) => provider.id === providerOAuthFlow.provider)
            ?.name ?? providerOAuthFlow.provider
          : ""
      }
      authorizationResponse={providerAuthorization.response}
      completing={providerAuthorization.completing}
      cancelling={providerAuthorization.cancelling}
      canComplete={providerAuthorization.canComplete}
      error={providerAuthorization.error}
      remoteBrowserAccess={remoteBrowserAccess}
      onAuthorizationResponseChange={(value) => {
        providerAuthorization.setResponse(value);
      }}
      onOpenAuthorization={() => {
        if (!providerOAuthFlow) return;
        const opened = window.open(
          providerOAuthFlow.authorization_url,
          "_blank",
          "noopener,noreferrer",
        );
        if (opened) opened.opener = null;
      }}
      onComplete={() => void providerAuthorization.complete()}
      onRetry={() => void providerAuthorization.retry()}
      onClose={() => void providerAuthorization.close()}
    />

    <CirnoFeatureInstallDialog
      feature={systemState.cirnoFeatureConfirm?.feature ?? null}
      installOnly={systemState.cirnoFeatureConfirm?.installOnly ?? false}
      installing={systemState.cirnoFeatureAction === `${systemState.cirnoFeatureConfirm?.installOnly ? "install" : "enable"}:${systemState.cirnoFeatureConfirm?.feature.name ?? ""}`}
      onOpenChange={(open) => {
        if (!open) systemState.setCirnoFeatureConfirm(null);
      }}
      onConfirm={(feature) => systemActions.handleCirnoFeatureAction("enable", feature.name, {
        confirmed: true,
        installOnly: systemState.cirnoFeatureConfirm?.installOnly,
      })}
    />

    <AutomationDeleteDialog
      job={systemState.automationPendingDelete}
      error={systemState.automationsError}
      deleting={systemState.automationAction === `delete:${systemState.automationPendingDelete?.id ?? ""}`}
      onOpenChange={(open) => {
        if (!open) systemState.setAutomationPendingDelete(null);
      }}
      onConfirm={(job) => systemActions.handleAutomationAction("delete", job)}
    />

    <AutomationEditDialog
      job={systemState.automationPendingEdit}
      error={systemState.automationsError}
      saving={systemState.automationAction === `update:${systemState.automationPendingEdit?.id ?? ""}`}
      onOpenChange={(open) => {
        if (!open) systemState.setAutomationPendingEdit(null);
      }}
      onCancel={(job) => setAutomationDetailReturn(job)}
      onSave={systemActions.handleAutomationEdit}
    />
  </>;
}
