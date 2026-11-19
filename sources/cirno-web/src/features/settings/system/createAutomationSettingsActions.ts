import type { SystemSettingsState } from "./useSystemSettingsState";
import type { CirnoClient } from "@/lib/cirno-client";
import { createSettingsActionGate } from "./createSettingsActionGate";
import type { TFunction } from "i18next";
import type { AutomationAction } from "@/features/automations";
import type { AutomationUpdatePayload, AutomationChatUpdate, SessionAutomationJob } from "@/lib/contracts/automations";
import { changeAutomationChat, runAutomationAction, updateAutomation } from "@/lib/api";

interface Options {
  state: SystemSettingsState;
  client: CirnoClient;
  t: TFunction;
  refreshAutomations: (showLoading?: boolean, automatic?: boolean) => Promise<void>;
}

export function createAutomationSettingsActions({ state, client, t, refreshAutomations }: Options) {
  const { isSystemSettingsCurrent, automationActionRef, automationsRevisionRef,
    setAutomationAction, setAutomationsLoading, setAutomationsError, setAutomations,
    setAutomationPendingDelete, setAutomationPendingEdit, automationRefreshTimersRef } = state;
  const { begin: beginAutomationAction, end: endAutomationAction } = createSettingsActionGate({
    isCurrent: isSystemSettingsCurrent, actionRef: automationActionRef, revisionRef: automationsRevisionRef,
    setAction: setAutomationAction, setLoading: setAutomationsLoading,
  });

  const scheduleAutomationRefresh = (delay: number) => {
    const timer = window.setTimeout(() => {
      automationRefreshTimersRef.current.delete(timer);
      if (isSystemSettingsCurrent()) void refreshAutomations(false, true);
    }, delay);
    automationRefreshTimersRef.current.add(timer);
  };
  const handleAutomationAction = async (
    action: AutomationAction,
    job: SessionAutomationJob,
  ) => {
    const key = `${action}:${job.id}`;
    if (!beginAutomationAction(key)) return;
    setAutomationsError(null);
    try {
      const payload = await runAutomationAction(client, action, job.id);
      if (!isSystemSettingsCurrent()) return;
      setAutomations(payload);
      if (action === "delete") setAutomationPendingDelete(null);
      if (action === "run") {
        scheduleAutomationRefresh(1200);
        scheduleAutomationRefresh(4000);
      }
    } catch (err) {
      if (isSystemSettingsCurrent()) setAutomationsError(err instanceof Error ? err.message : String(err));
    } finally {
      endAutomationAction(key);
    }
  };

  const handleAutomationEdit = async (
    job: SessionAutomationJob,
    values: AutomationUpdatePayload,
  ) => {
    const key = `update:${job.id}`;
    if (!beginAutomationAction(key)) return;
    setAutomationsError(null);
    try {
      const payload = await updateAutomation(client, job.id, values);
      if (!isSystemSettingsCurrent()) return;
      setAutomations(payload);
      setAutomationPendingEdit(null);
    } catch (err) {
      if (isSystemSettingsCurrent()) setAutomationsError(err instanceof Error ? err.message : String(err));
    } finally {
      endAutomationAction(key);
    }
  };

  const handleAutomationChat = async (job: SessionAutomationJob, values: AutomationChatUpdate) => {
    // The dialog owns the draft and error. Publish only the server acknowledgement.
    const key = `change-chat:${job.id}`;
    if (!beginAutomationAction(key)) {
      throw new Error(t("settings.automations.chat.schedulerBusy"));
    }
    try {
      const payload = await changeAutomationChat(client, job.id, values);
      if (isSystemSettingsCurrent()) setAutomations(payload);
    } finally {
      endAutomationAction(key);
    }
  };

  return { handleAutomationAction, handleAutomationEdit, handleAutomationChat };
}
