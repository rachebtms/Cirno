import type { SystemSettingsState } from "./useSystemSettingsState";
import type { CirnoClient } from "@/lib/cirno-client";
import { createSettingsActionGate } from "./createSettingsActionGate";
import { runCliAppAction } from "@/lib/api";
import { notifyCliAppsChanged } from "@/lib/cli-app-events";

export function createCliSettingsActions({ state, client }: { state: SystemSettingsState; client: CirnoClient }) {
  const { isSystemSettingsCurrent, cliAppsActionRef, cliAppsRevisionRef,
    setCliAppsAction, setCliAppsLoading, setCliAppsMessage, setCliAppsError,
    setCliAppsReadError, setCliApps, setCliAppsFocusName } = state;
  const { begin: beginCliAction, end: endCliAction } = createSettingsActionGate({
    isCurrent: isSystemSettingsCurrent, actionRef: cliAppsActionRef, revisionRef: cliAppsRevisionRef,
    setAction: setCliAppsAction, setLoading: setCliAppsLoading,
  });

  const handleCliAppAction = async (
    action: "install" | "update" | "uninstall" | "test",
    name: string,
  ) => {
    const key = `${action}:${name}`;
    if (!beginCliAction(key)) return;
    setCliAppsMessage(null);
    setCliAppsError(null);
    setCliAppsReadError(null);
    try {
      const payload = await runCliAppAction(client, action, name);
      if (!isSystemSettingsCurrent()) return;
      setCliApps(payload);
      if (action !== "test") {
        notifyCliAppsChanged(payload);
      }
      if (payload.last_action?.ok === false) {
        setCliAppsError(payload.last_action.message);
        setCliAppsFocusName(null);
      } else {
        setCliAppsMessage(payload.last_action?.message ?? null);
        setCliAppsFocusName(action === "uninstall" ? null : name);
      }
    } catch (err) {
      if (isSystemSettingsCurrent()) setCliAppsError((err as Error).message);
    } finally {
      endCliAction(key);
    }
  };

  return { handleCliAppAction };
}
