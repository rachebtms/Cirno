import type { ChannelFieldsProps } from "./contracts";
import { ChannelChoiceField } from "./ChannelChoiceField";
import { ChannelTextField } from "./ChannelTextField";
import { ChannelSwitchField } from "./ChannelSwitchField";
export function ChannelFields({ fields, ...props }: ChannelFieldsProps) {
  return (
    <div className="channel-fields">
      {fields.map((field) => {
        const Control =
          field.control === "switch" && field.kind === "bool"
            ? ChannelSwitchField
            : field.options?.length
              ? ChannelChoiceField
              : ChannelTextField;
        return <Control key={field.key} field={field} {...props} />;
      })}
    </div>
  );
}

export type { ChannelFieldsProps } from "./contracts";
