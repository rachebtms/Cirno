import {
  Alert,
  Button,
  Form,
  Input,
  Label,
  Modal,
  TextArea,
  TextField,
} from "@heroui/react";
import { CircleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type {
  AutomationUpdatePayload,
  SessionAutomationJob,
} from "@/lib/contracts/automations";
import {
  automationDraftFromJob,
  parseAutomationDraft,
  type AutomationEditDraft,
} from "../model/draft";
import { isLocalTriggerAutomation } from "../model/status";
import { ScheduleFields } from "./ScheduleFields";
import "../automations.css";

interface EditProps {
  job: SessionAutomationJob | null;
  saving: boolean;
  error?: string | null;
  onOpenChange: (open: boolean) => void;
  onCancel?: (job: SessionAutomationJob) => void;
  onSave: (
    job: SessionAutomationJob,
    values: AutomationUpdatePayload,
  ) => void | Promise<void>;
}
export function AutomationEditDialog(props: EditProps) {
  const [busy, setBusy] = useState(false);
  const disabled = busy || props.saving;
  return props.job ? (
    <Modal.Backdrop
      isOpen
      onOpenChange={(open) => {
        if (!open) {
          props.onOpenChange(false);
          props.onCancel?.(props.job!);
        }
      }}
      isDismissable={!disabled}
      isKeyboardDismissDisabled={disabled}
    >
      <Modal.Container size="lg">
        <Modal.Dialog className="automation-edit-dialog">
          <AutomationEditContent
            key={props.job.id}
            {...props}
            job={props.job}
            onBusyChange={setBusy}
          />
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  ) : null;
}
export function AutomationEditContent({
  job,
  saving,
  error,
  onOpenChange,
  onCancel,
  onSave,
  onBusyChange,
}: EditProps & {
  job: SessionAutomationJob;
  onBusyChange?: (busy: boolean) => void;
}) {
  const { t } = useTranslation();
  const [original] = useState(job);
  const [draft, setDraft] = useState(() => automationDraftFromJob(job));
  const [busy, setBusy] = useState(false),
    [saveError, setSaveError] = useState("");
  const submitting = useRef(false);
  const disabled = busy || saving;
  useEffect(() => {
    onBusyChange?.(busy);
    return () => onBusyChange?.(false);
  }, [onBusyChange, busy]);
  const parsed = parseAutomationDraft(draft, original);
  const validation = !parsed.ok
    ? t(`settings.automations.validation.${parsed.error}`)
    : null;
  const message = validation || saveError || error;
  const canSave = parsed.ok && Object.keys(parsed.value).length > 0;
  const change = (patch: Partial<AutomationEditDraft>) => {
    setSaveError("");
    setDraft((old) => ({ ...old, ...patch }));
  };
  const cancel = () => {
    onOpenChange(false);
    onCancel?.(job);
  };
  const submit = async () => {
    const current = parseAutomationDraft(draft, original);
    if (!current.ok) {
      setSaveError(t(`settings.automations.validation.${current.error}`));
      return;
    }
    if (!Object.keys(current.value).length || submitting.current || saving)
      return;
    submitting.current = true;
    setBusy(true);
    setSaveError("");
    try {
      await onSave(job, current.value);
    } catch (reason) {
      setSaveError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  };
  return (
    <Form
      validationBehavior="aria"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <Modal.Header>
        <Modal.Heading>{t("settings.automations.editTitle")}</Modal.Heading>
        <Modal.CloseTrigger isDisabled={disabled} />
      </Modal.Header>
      <Modal.Body>
        <TextField
          isRequired
          isDisabled={disabled}
          value={draft.name}
          onChange={(name) => change({ name })}
        >
          <Label>{t("settings.automations.fields.name")}</Label>
          <Input autoFocus />
        </TextField>
        {!isLocalTriggerAutomation(job) && (
          <>
            <TextField
              isRequired
              isDisabled={disabled}
              value={draft.message}
              onChange={(message) => change({ message })}
            >
              <Label>{t("settings.automations.fields.message")}</Label>
              <TextArea rows={5} />
            </TextField>
            <ScheduleFields draft={draft} change={change} disabled={disabled} />
          </>
        )}
      </Modal.Body>
      <Modal.Footer className="automation-dialog-footer">
        {message && (
          <Alert status="danger" role="alert">
            <Alert.Indicator>
              <CircleAlert />
            </Alert.Indicator>
            <Alert.Content>
              <Alert.Description>{message}</Alert.Description>
            </Alert.Content>
          </Alert>
        )}
        <div className="automation-dialog-actions">
          <Button variant="ghost" isDisabled={disabled} onPress={cancel}>
            {t("settings.automations.cancel")}
          </Button>
          <Button type="submit" isPending={disabled} isDisabled={!canSave}>
            {t("settings.automations.save")}
          </Button>
        </div>
      </Modal.Footer>
    </Form>
  );
}
