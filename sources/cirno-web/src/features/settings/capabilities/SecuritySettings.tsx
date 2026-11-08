import { useEditCompletion, type EditCompletion } from "@/features/settings/shared/useEditCompletion";
import type { Dispatch, SetStateAction } from "react";
import { useTranslation } from "react-i18next";

import {
  RestartSettingsFooter,
  SettingsGroup,
  SettingsRow,
  SettingsSectionTitle,
} from "@/features/settings/shared/SettingsControls";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { ToggleButton } from "@/components/ui/toggle-button";
import type { NetworkSafetySettingsUpdate, SettingsPayload } from "@/lib/contracts/settings";
import type { WebuiDefaultAccessMode } from "@/lib/contracts/workspaces";

export const DEFAULT_NETWORK_SAFETY_FORM: NetworkSafetySettingsUpdate = {
  webuiAllowLocalServiceAccess: true,
  webuiDefaultAccessMode: "default",
};

export function networkSafetyFormFromPayload(payload: SettingsPayload): NetworkSafetySettingsUpdate {
  return {
    webuiAllowLocalServiceAccess:
      payload.advanced.webui_allow_local_service_access ??
      true,
    webuiDefaultAccessMode: visibleWebuiDefaultAccessMode(
      payload.advanced.webui_default_access_mode,
    ),
  };
}

export function visibleWebuiDefaultAccessMode(mode: string | null | undefined): WebuiDefaultAccessMode {
  return mode === "full" || mode === "review" ? mode : "default";
}

export function AdvancedSettings({
  editCompletion,
  error,
  form,
  dirty,
  saving,
  requiresRestartPending,
  onChangeForm,
  onSave,
  onRestart,
  isRestarting,
}: {
  editCompletion?: EditCompletion;
  error?: string;
  form: NetworkSafetySettingsUpdate;
  dirty: boolean;
  saving: boolean;
  requiresRestartPending: boolean;
  onChangeForm: Dispatch<SetStateAction<NetworkSafetySettingsUpdate>>;
  onSave: () => void;
  onRestart?: () => void;
  isRestarting?: boolean;
}) {
  const { t } = useTranslation();
  const localEdits = useEditCompletion(form, dirty, onSave, !editCompletion);
  const edits = editCompletion ?? localEdits;
  const tx = (key: string, fallback: string) => t(key, { defaultValue: fallback });
  return (
    <div className="settings-stack" onChangeCapture={edits.onChangeCapture} onFocusCapture={edits.onFocusCapture} onBlurCapture={edits.onBlurCapture}>
      <section>
        <SettingsSectionTitle>
          {tx("settings.sections.webuiSafety", "Web safety")}
        </SettingsSectionTitle>
        <SettingsGroup>
          <SettingsRow
            title={tx("settings.rows.localServiceAccess", "Local Service Access")}
            description={tx(
              "settings.help.localServiceAccess",
              "Allow Full Access shell commands to reach localhost services.",
            )}
          >
            <ToggleButton
              checked={form.webuiAllowLocalServiceAccess}
              onChange={(webuiAllowLocalServiceAccess) =>
                onChangeForm((prev) => ({ ...prev, webuiAllowLocalServiceAccess }))
              }
              ariaLabel={tx("settings.rows.localServiceAccess", "Local Service Access")}
              label={form.webuiAllowLocalServiceAccess ? tx("settings.values.on", "On") : tx("settings.values.off", "Off")}
            />
          </SettingsRow>
          <SettingsRow
            title={tx("settings.rows.webuiDefaultAccess", "Default access")}
            description={tx(
              "settings.help.webuiDefaultAccess",
              "Initial access for new conversations. Use tool policy follows Workspace restriction: on limits access to the working directory; off allows Full Access.",
            )}
          >
            <SegmentedControl
              value={form.webuiDefaultAccessMode}
              options={[
                { value: "default", label: tx("settings.values.inheritToolPolicy", "Use tool policy") },
                { value: "review", label: tx("thread.composer.workspace.review", "AI review") },
                { value: "full", label: tx("settings.values.fullAccess", "Full Access") },
              ]}
              onChange={(webuiDefaultAccessMode) =>
                onChangeForm((prev) => ({
                  ...prev,
                  webuiDefaultAccessMode: webuiDefaultAccessMode as WebuiDefaultAccessMode,
                }))
              }
            />
          </SettingsRow>
          {form.webuiDefaultAccessMode === "review" && <p className="px-4 text-xs leading-relaxed text-destructive">{tx("thread.composer.workspace.reviewDescription", "")}</p>}
          <RestartSettingsFooter
            autoSave
            error={Boolean(error)}
            message={error}
            dirty={dirty}
            saving={saving}
            pendingRestart={requiresRestartPending}
            onSave={onSave}
            onRestart={onRestart}
            isRestarting={isRestarting}
          />
        </SettingsGroup>
      </section>

    </div>
  );
}
