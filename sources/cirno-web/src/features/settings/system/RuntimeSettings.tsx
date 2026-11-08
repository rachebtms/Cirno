import { Loader2, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { AgentSettingsDraft } from "@/features/settings/models/modelDraft";
import {
  ReadOnlyRow,
  SettingsGroup,
  SettingsRow,
  SettingsSectionTitle,
} from "@/features/settings/shared/SettingsControls";
import { Button } from "@/components/ui/button";
import type { SettingsPayload } from "@/lib/contracts/settings";

export function RuntimeSettings({
  form,
  settings,
  onRestart,
  isRestarting,
  requiresRestartPending,
}: {
  form: AgentSettingsDraft;
  settings: SettingsPayload;
  onRestart?: () => void;
  isRestarting?: boolean;
  requiresRestartPending: boolean;
}) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => t(key, { defaultValue: fallback });
  const restartActionLabel = t("app.system.restart");
  const restartingActionLabel = t("app.system.restarting");
  return (
    <div className="settings-stack">
      <section>
        <SettingsSectionTitle>{t("settings.sections.system")}</SettingsSectionTitle>
        <SettingsGroup>
          <ReadOnlyRow
            title={tx("settings.rows.healthListener", "Health listener")}
            value={`${settings.runtime.health_host}:${settings.runtime.health_port}`}
          />
          <ReadOnlyRow title={t("settings.rows.configPath")} value={settings.runtime.config_path} />
          {!settings.runtime_config ? (
            <ReadOnlyRow title={tx("settings.rows.workspacePath", "Default workspace")} value={settings.runtime.workspace_path} />
          ) : null}
          {!settings.runtime_config ? (
            <ReadOnlyRow title={tx("settings.rows.timezone", "Timezone")} value={form.timezone} />
          ) : null}
          {onRestart ? (
            <SettingsRow
              title={t("settings.rows.restart")}
              description={
                requiresRestartPending
                  ? tx("settings.status.savedRestartApply", "Saved. Restart to apply changes.")
                  : undefined
              }
            >
              <Button
                size="sm"
                variant="outline"
                onClick={onRestart}
                disabled={isRestarting}
                className="rounded-full"
              >
                {isRestarting ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden />
                ) : (
                  <RotateCcw className="mr-1.5 h-3.5 w-3.5" aria-hidden />
                )}
                {isRestarting ? restartingActionLabel : restartActionLabel}
              </Button>
            </SettingsRow>
          ) : null}
        </SettingsGroup>
      </section>
    </div>
  );
}
