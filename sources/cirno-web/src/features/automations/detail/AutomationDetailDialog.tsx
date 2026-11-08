import { Modal } from "@heroui/react";
import { useCallback, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  AutomationChatBinding,
  type AutomationChatNames,
  type ChangeAutomationChat,
} from "../binding/AutomationChatBinding";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import { automationChannelLabel } from "../model/presentation";
import { InlineError } from "@/ui/feedback/InlineError";
import { DetailRow } from "./DetailRow";
import { TaskActions, type TaskActionsProps } from "./TaskActions";
import { TaskInformation } from "./TaskInformation";
import { TaskInstructions } from "./TaskInstructions";
import "../automations.css";

interface DetailProps extends Omit<TaskActionsProps, "job" | "busy"> {
  token?: string;
  chatNames?: AutomationChatNames;
  onChangeChat?: ChangeAutomationChat;
  job: SessionAutomationJob | null;
  open: boolean;
  locale: string;
  actionKey: string | null;
  error: string | null;
  onOpenChange: (open: boolean) => void;
}
export function AutomationDetailDialog({ job, ...props }: DetailProps) {
  return job ? <TaskDetail key={job.id} job={job} {...props} /> : null;
}
function TaskDetail({
  job,
  open,
  onOpenChange,
  ...props
}: DetailProps & { job: SessionAutomationJob }) {
  const [busy, setBusy] = useState(false);
  const locked = busy || !!props.actionKey;
  return (
    <Modal.Backdrop
      isOpen={open}
      onOpenChange={onOpenChange}
      isDismissable={!locked}
      isKeyboardDismissDisabled={locked}
    >
      <Modal.Container size="lg">
        <Modal.Dialog className="automation-detail-dialog">
          <AutomationDetailContent
            job={job}
            {...props}
            onBusyChange={setBusy}
          />
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
export function AutomationDetailContent({
  job,
  token = "",
  chatNames,
  onChangeChat,
  locale,
  actionKey,
  error,
  onBusyChange,
  ...actions
}: Omit<DetailProps, "open" | "onOpenChange"> & {
  job: SessionAutomationJob;
  onBusyChange?: (busy: boolean) => void;
}) {
  const { t } = useTranslation();
  const [bindingBusy, setBindingBusy] = useState(false);
  const updateBusy = useCallback(
    (value: boolean) => {
      setBindingBusy(value);
      onBusyChange?.(value);
    },
    [onBusyChange],
  );
  const busy = Boolean(actionKey) || bindingBusy;
  const content = (chatPicker?: ReactNode) => (
    <>
      <Modal.Header>
        <Modal.Heading>{job.name || job.id}</Modal.Heading>
        <TaskInformation job={job} locale={locale} />
        <Modal.CloseTrigger isDisabled={busy} />
      </Modal.Header>
      <Modal.Body>
        <TaskInstructions job={job} />
        <InlineError message={job.state.last_error} />
        {chatPicker ??
          (!job.protected &&
            job.origin?.channel &&
            job.origin.channel !== "websocket" && (
              <dl>
                <DetailRow label={t("settings.automations.labels.origin")}>
                  {automationChannelLabel(job.origin.channel, t)}
                </DetailRow>
              </dl>
            ))}
      </Modal.Body>
      <InlineError message={error} />
      {!job.protected && <TaskActions job={job} busy={busy} {...actions} />}
    </>
  );
  return job.chat_binding_revision && onChangeChat ? (
    <AutomationChatBinding
      job={job}
      token={token}
      chatNames={chatNames}
      onSave={onChangeChat}
      onBusyChange={updateBusy}
    >
      {content}
    </AutomationChatBinding>
  ) : (
    content()
  );
}
