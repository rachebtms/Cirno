import {
  Button,
  Description,
  FieldError,
  InputGroup,
  Label,
  TextArea,
  TextField,
} from "@heroui/react";
import { Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ChannelFieldProps } from "./contracts";
import { channelFieldInputId } from "../../model/fieldValues";
export function ChannelTextField({
  field,
  values,
  configuredFields,
  visibleSecrets,
  onChange,
  onFieldBlur,
  onToggleSecret,
  errors = {},
  clearedSecrets,
  onClearSecret,
  showSecretActions,
  secretActionsDisabled,
  disabled,
}: ChannelFieldProps) {
  const { t } = useTranslation(),
    value = values[field.key] ?? "",
    error = errors[field.key],
    clear = clearedSecrets?.has(field.key) ?? false;
  const saved = Boolean(
      field.secret &&
        configuredFields?.has(field.key) &&
        !value.trim() &&
        !clear,
    ),
    visible = Boolean(visibleSecrets[field.key]);
  const common = {
    id: channelFieldInputId(field.key),
    placeholder: saved
      ? t("settings.channels.savedSecretPlaceholder")
      : field.placeholder,
    onBlur: () => onFieldBlur?.(field.key),
    spellCheck: false,
  };
  return (
    <div className="channel-text-field">
      <TextField
        value={value}
        onChange={(value) => onChange(field.key, value)}
        isDisabled={disabled}
        isInvalid={Boolean(error)}
      >
        <Label>{field.label}</Label>
        {field.kind === "json" ? (
          <TextArea {...common} rows={4} className="channel-json-field" />
        ) : (
          <InputGroup>
            <InputGroup.Input
              {...common}
              type={
                field.secret && !visible
                  ? "password"
                  : (field.inputType ?? "text")
              }
              autoComplete={field.secret ? "off" : undefined}
              step={
                field.inputType === "number"
                  ? field.kind === "int"
                    ? 1
                    : "any"
                  : undefined
              }
              inputMode={
                field.inputType === "number"
                  ? field.kind === "int"
                    ? "numeric"
                    : "decimal"
                  : undefined
              }
            />
            {field.secret && value.trim() && (
              <InputGroup.Suffix>
                <Button
                  type="button"
                  isIconOnly
                  size="sm"
                  variant="ghost"
                  isDisabled={disabled}
                  aria-label={t(
                    visible
                      ? "settings.channels.hideSecret"
                      : "settings.channels.showSecret",
                  )}
                  onPress={() => onToggleSecret(field.key)}
                >
                  {visible ? <EyeOff size={16} /> : <Eye size={16} />}
                </Button>
              </InputGroup.Suffix>
            )}
          </InputGroup>
        )}
        {clear ? (
          <Description>
            {t("settings.channels.secretWillBeRemoved")}
          </Description>
        ) : (
          field.optional && (
            <Description>{t("settings.channels.optional")}</Description>
          )
        )}
        <FieldError>{error}</FieldError>
      </TextField>
      {showSecretActions &&
        field.secret &&
        configuredFields?.has(field.key) &&
        !value.trim() &&
        onClearSecret && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            isDisabled={disabled || secretActionsDisabled}
            onPress={() => onClearSecret(field.key, !clear)}
          >
            {t(
              clear
                ? "settings.channels.keepSavedSecret"
                : "settings.channels.removeSavedSecret",
            )}
          </Button>
        )}
    </div>
  );
}
