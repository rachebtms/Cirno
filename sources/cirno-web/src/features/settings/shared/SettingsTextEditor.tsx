import { Alert, Button, Form, Modal, TextArea, TextField } from "@heroui/react";
import { SquarePen } from "lucide-react";
import { useId, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useTextEditor } from "./useTextEditor";
import "./text-editor.css";

export function SettingsTextEditor({ id, title, description, value, placeholder, disabled, trigger, onSave, saveLabel, buttonLabel, json = false, loadValue }: {
  id?: string;
  title: string;
  description?: string;
  value: string;
  placeholder?: string;
  disabled?: boolean;
  trigger?: ReactElement;
  onSave: (value: string) => void | Promise<void>;
  saveLabel?: string;
  buttonLabel?: string;
  json?: boolean;
  loadValue?: () => Promise<string>;
}) {
  const { t } = useTranslation();
  const state = useTextEditor({ value, json, loadValue, onSave });
  const descriptionId = useId();
  const help = description?.trim();
  const showHelp = Boolean(help && help !== title.trim());
  const locked = state.saving || state.loading || state.loadFailed;
  return <Modal isOpen={state.open} onOpenChange={state.changeOpen}>
    {trigger ?? <Button id={id} variant="ghost" isIconOnly isDisabled={disabled} aria-label={buttonLabel ?? title}><SquarePen size={17} /></Button>}
    <Modal.Backdrop isDismissable={!state.saving} isKeyboardDismissDisabled={state.saving}><Modal.Container size="lg"><Modal.Dialog aria-describedby={showHelp ? descriptionId : undefined}>
      <Form validationBehavior="aria" className="settings-text-form" onSubmit={event => { event.preventDefault(); void state.save(); }}>
        <Modal.Header><Modal.Heading>{title}</Modal.Heading>{showHelp && <p id={descriptionId} className="settings-text-help">{help}</p>}<Modal.CloseTrigger isDisabled={state.saving} /></Modal.Header>
        <Modal.Body>
          <TextField autoFocus aria-label={buttonLabel ?? title} value={state.draft} onChange={state.change} isDisabled={locked} isInvalid={Boolean(state.error)} validationBehavior="aria">
            <TextArea ref={state.editor} placeholder={placeholder} aria-busy={state.loading} spellCheck={false} className="settings-text-input" />
          </TextField>
          {state.loading && <p role="status" className="settings-text-help">{t("settings.loading")}</p>}
          {state.error && <Alert status="danger" role="alert"><Alert.Description>{state.error}</Alert.Description></Alert>}
        </Modal.Body>
        <Modal.Footer>
          {json && <Button variant="ghost" isDisabled={locked} onPress={state.formatDraft}>{t("settings.actions.formatJson")}</Button>}
          <Button variant="secondary" isDisabled={state.saving} onPress={() => state.changeOpen(false)}>{t("settings.actions.cancel")}</Button>
          <Button type="submit" isDisabled={locked} isPending={state.saving}>{state.saving ? t("settings.actions.saving") : saveLabel ?? t("settings.actions.save")}</Button>
        </Modal.Footer>
      </Form>
    </Modal.Dialog></Modal.Container></Modal.Backdrop>
  </Modal>;
}
