import { AutomationsPage } from "@/features/automations";
import type { SectionRenderer, SectionRenderers } from "./contracts";
import type { SettingsComposition } from "./useSettingsComposition";

export function createAutomationSections(
  bindings: SettingsComposition,
): SectionRenderers {
  const {
    controller,
    onStartAutomationChat,
    titleOverrides,
    sessions,
    systemState,
    systemActions,
    token,
    selectSection,
    automationDetailReturn,
    setAutomationDetailReturn,
  } = bindings;
  const renderAutomations: SectionRenderer = () => {
    return (
      <div className="settings-stack">
        <AutomationsPage
          token={token}
          payload={systemState.automations}
          titleOverrides={titleOverrides}
          sessions={sessions}
          settingsSnapshot={controller.settings}
          onStartChat={onStartAutomationChat}
          loading={systemState.automationsLoading}
          filter={systemState.automationsFilter}
          actionKey={systemState.automationAction}
          error={systemState.automationsError}
          onFilterChange={systemState.setAutomationsFilter}
          onAction={systemActions.handleAutomationAction}
          onRequestEdit={(job) => {
            systemState.setAutomationsError(null);
            setAutomationDetailReturn(null);
            systemState.setAutomationPendingEdit(job);
          }}
          onRequestDelete={(job) => {
            systemState.setAutomationsError(null);
            systemState.setAutomationPendingDelete(job);
          }}
          onChangeChat={systemActions.handleAutomationChat}
          onManageModels={() => selectSection("models")}
          returnToDetailJob={automationDetailReturn}
          onReturnToDetailHandled={() => setAutomationDetailReturn(null)}
        />
      </div>
    );
  };

  return {
    automations: renderAutomations,
  };
}
