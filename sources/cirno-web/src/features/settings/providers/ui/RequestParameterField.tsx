import { Button, Description, FieldError, Label, TextArea, TextField } from "@heroui/react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "@/lib/api";
import { useMutation } from "@/ui/resources/useMutation";
import { parseProviderObject } from "../providerForm";

export function RequestParameterField({
  value,
  title,
  placeholder,
  stringsOnly,
  field,
  disabled,
  inherited,
  draft,
  onChange,
  onSave,
}: {
  value: string;
  title: string;
  placeholder: string;
  stringsOnly: boolean;
  field: string;
  disabled: boolean;
  inherited: boolean;
  draft: boolean;
  onChange: (value: string) => void;
  onSave?: (value: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState(value);
  const mutation = useMutation(undefined);
  const saving = mutation.busy;
  const error = mutation.error ?? "";
  useEffect(() => setText(value), [value]);
  const parsed = parseProviderObject(text);
  const invalid = !parsed
    ? t("settings.providers.invalidObject")
    : stringsOnly && Object.values(parsed).some((item) => typeof item !== "string")
      ? t("settings.providers.stringValuesRequired")
      : "";
  async function save() {
    if (!onSave || disabled || invalid || text === value) return;
    await mutation.run(async () => {
      try {
        await onSave(text);
      } catch (reason) {
        const missingMask =
          reason instanceof ApiError &&
          reason.status === 400 &&
          (
            reason.message === "No saved secret matches this mask. Enter the actual value or remove the entry."
            || (stringsOnly && parsed && Object.entries(parsed).some(
              ([key, item]) =>
                item === "••••••••" &&
                reason.message === `${field}.${key}: Input should be a valid string`,
            ))
          );
        if (missingMask) throw new Error(t("settings.providers.maskedSecretMissing"), { cause: reason });
        throw reason;
      }
    }, () => {});
  }
  return (
    <div role="group" aria-label={title} className="provider-parameter-field">
      <TextField
        isDisabled={disabled || saving}
        isInvalid={Boolean(invalid || error)}
        validationBehavior="aria"
        value={text}
        onChange={(next) => {
          setText(next);
          mutation.clear();
          if (!onSave) onChange(next);
        }}
      >
        <Label>{title}</Label>
        {(draft || (inherited && !text.trim())) && (
          <Description>
            {t(draft ? "settings.providers.draftHint" : "settings.providers.useProviderSettings")}
          </Description>
        )}
        <TextArea
          placeholder={placeholder}
          rows={4}
          spellCheck={false}
          className="provider-json-input"
        />
        <FieldError>{invalid || error}</FieldError>
      </TextField>
      {error && (
        <p role="alert" className="text-danger text-sm">
          {error}
        </p>
      )}
      {onSave && (
        <Button
          variant="secondary"
          isPending={saving}
          isDisabled={disabled || saving || Boolean(invalid) || text === value}
          onPress={() => void save()}
        >
          {t(draft ? "settings.providers.applyToDraft" : "settings.actions.save")}
        </Button>
      )}
    </div>
  );
}
