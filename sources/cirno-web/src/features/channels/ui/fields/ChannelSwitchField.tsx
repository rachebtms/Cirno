import { FieldError, Label, Switch } from "@heroui/react";
import type { ChannelFieldProps } from "./contracts";
import {
  channelFieldInputId,
  channelFieldValue,
} from "../../model/fieldValues";
export function ChannelSwitchField({
  field,
  values,
  onChange,
  onFieldBlur,
  errors = {},
  disabled,
}: ChannelFieldProps) {
  const error = errors[field.key];
  return (
    <Switch
      id={channelFieldInputId(field.key)}
      onBlur={() => onFieldBlur?.(field.key)}
      isSelected={channelFieldValue(field, values) === "true"}
      isDisabled={disabled}
      isInvalid={Boolean(error)}
      onChange={(checked) => onChange(field.key, String(checked))}
    >
      <Switch.Content className="channel-switch-content">
        <Label>{field.label}</Label>
        <Switch.Control>
          <Switch.Thumb />
        </Switch.Control>
      </Switch.Content>
      <FieldError>{error}</FieldError>
    </Switch>
  );
}
