import { FieldError, Label, Radio, RadioGroup } from "@heroui/react";
import type { ChannelFieldProps } from "./contracts";
import {
  channelFieldInputId,
  channelFieldValue,
} from "../../model/fieldValues";
export function ChannelChoiceField({
  field,
  values,
  onChange,
  onFieldBlur,
  errors = {},
  disabled,
}: ChannelFieldProps) {
  const error = errors[field.key],
    id = channelFieldInputId(field.key);
  return (
    <RadioGroup
      id={`${id}-group`}
      value={channelFieldValue(field, values)}
      onChange={(value) => onChange(field.key, value)}
      isDisabled={disabled}
      isInvalid={Boolean(error)}
      orientation="horizontal"
      className="channel-choice-field"
    >
      <Label>{field.label}</Label>
      <div className="channel-choice-options">
        {field.options?.map((option, index) => (
          <Radio
            key={option.value}
            value={option.value}
            id={index === 0 ? id : `${id}-${index}`}
            onBlur={() => onFieldBlur?.(field.key)}
          >
            <Radio.Content>
              <Radio.Control>
                <Radio.Indicator />
              </Radio.Control>
              <Label>{option.label}</Label>
            </Radio.Content>
          </Radio>
        ))}
      </div>
      <FieldError>{error}</FieldError>
    </RadioGroup>
  );
}
