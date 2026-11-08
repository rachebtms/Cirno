import {
  Button,
  Description,
  FieldError,
  Form,
  Label,
  TextArea,
  TextField,
} from "@heroui/react";
import { useId, useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { autosizeTextarea } from "@/ui/fields/textarea";
import "./messages.css";

export interface InlineMessageEditorProps {
  value: string;
  busy: boolean;
  error: string;
  hasToolEffects: boolean;
  onChange: (value: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
}

/** Editing replaces only the human text; attachment and transcript owners stay mounted. */
export function InlineMessageEditor(props: InlineMessageEditorProps) {
  const { t } = useTranslation(),
    input = useRef<HTMLTextAreaElement>(null);
  const descriptionId = useId(),
    warningId = useId();
  useLayoutEffect(() => {
    const element = input.current!;
    element.focus({ preventScroll: true });
    element.setSelectionRange(element.value.length, element.value.length);
  }, []);
  useLayoutEffect(() => {
    autosizeTextarea(input.current!, Infinity);
  }, [props.value]);
  const submit = () => {
    if (!props.busy && props.value.trim()) props.onSubmit();
  };
  return (
    <Form
      aria-label={t("message.edit")}
      data-inline-message-editor
      className="message-editor"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <TextField
        value={props.value}
        onChange={props.onChange}
        isDisabled={props.busy}
        isInvalid={Boolean(props.error)}
      >
        <Label className="sr-only">{t("thread.historyEdit.text")}</Label>
        <Description id={descriptionId} className="sr-only">
          {t("thread.historyEdit.description")}
        </Description>
        <TextArea
          ref={input}
          aria-describedby={`${descriptionId}${props.hasToolEffects ? ` ${warningId}` : ""}`}
          className="message-editor-input"
          onKeyDown={(event) => {
            if (event.nativeEvent.isComposing || event.keyCode === 229) return;
            if (event.key === "Escape" && !props.busy) {
              event.preventDefault();
              event.stopPropagation();
              props.onCancel();
            }
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
              event.preventDefault();
              submit();
            }
          }}
        />
        {props.hasToolEffects && (
          <p id={warningId} role="note" className="message-editor-warning">
            {t("thread.historyEffects.description")}
          </p>
        )}
        {props.error && (
          <FieldError>
            <span role="alert">{props.error}</span>
          </FieldError>
        )}
      </TextField>
      <div className="message-editor-actions">
        <Button
          type="button"
          variant="secondary"
          isDisabled={props.busy}
          onPress={props.onCancel}
        >
          {t("files.cancel")}
        </Button>
        <Button
          type="submit"
          isDisabled={props.busy || !props.value.trim()}
          isPending={props.busy}
        >
          {t("thread.historyEdit.submit")}
        </Button>
      </div>
    </Form>
  );
}
