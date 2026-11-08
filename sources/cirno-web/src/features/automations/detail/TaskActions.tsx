import { Button, Dropdown, Modal } from "@heroui/react";
import { MoreHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import type { AutomationAction } from "../model/status";
import { isLocalTriggerAutomation } from "../model/status";

export interface TaskActionsProps {
  job: SessionAutomationJob;
  busy: boolean;
  onAction: (
    action: AutomationAction,
    job: SessionAutomationJob,
  ) => void | Promise<void>;
  onRequestEdit: (job: SessionAutomationJob) => void;
  onRequestDelete: (job: SessionAutomationJob) => void;
}
export function TaskActions({
  job,
  busy,
  onAction,
  onRequestEdit,
  onRequestDelete,
}: TaskActionsProps) {
  const { t } = useTranslation();
  const local = isLocalTriggerAutomation(job);
  const originHref =
    job.origin?.channel === "websocket" && job.origin.session_key
      ? `#/chat/${encodeURIComponent(job.origin.session_key)}`
      : null;
  return (
    <Modal.Footer className="automation-task-actions">
      <Dropdown>
        <Button
          isIconOnly
          variant="ghost"
          isDisabled={busy}
          aria-label={t("settings.automations.moreActions")}
        >
          <MoreHorizontal size={18} />
        </Button>
        <Dropdown.Popover placement="top start">
          <Dropdown.Menu aria-label={t("settings.automations.moreActions")}>
            <Dropdown.Item
              id="toggle"
              isDisabled={busy || (!job.enabled && !job.origin)}
              onAction={() => {
                void onAction(job.enabled ? "disable" : "enable", job);
              }}
            >
              {t(
                job.enabled
                  ? "settings.automations.pause"
                  : "settings.automations.resume",
              )}
            </Dropdown.Item>
            {originHref && (
              <Dropdown.Item id="chat" href={originHref}>
                {t("settings.automations.emptyAction")}
              </Dropdown.Item>
            )}
            <Dropdown.Item
              id="delete"
              variant="danger"
              isDisabled={busy}
              onAction={() => onRequestDelete(job)}
            >
              {t("settings.automations.delete")}
            </Dropdown.Item>
          </Dropdown.Menu>
        </Dropdown.Popover>
      </Dropdown>
      <div className="automation-dialog-actions">
        <Button
          variant="ghost"
          isDisabled={busy}
          onPress={() => onRequestEdit(job)}
        >
          {t("settings.automations.edit")}
        </Button>
        {!local && (
          <Button
            variant="secondary"
            isDisabled={
              busy || !job.origin || !job.enabled || job.state.pending
            }
            onPress={() => {
              void onAction("run", job);
            }}
          >
            {t("settings.automations.runNow")}
          </Button>
        )}
      </div>
    </Modal.Footer>
  );
}
