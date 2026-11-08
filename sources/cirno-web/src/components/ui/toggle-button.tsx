import type { ComponentProps } from "react";
import { Switch } from "@heroui/react";
export function ToggleButton({ checked, disabled, onChange, ariaLabel, label, "aria-invalid": invalid, ...accessibility }: {
  checked: boolean; disabled?: boolean; onChange: (checked: boolean) => void;
  ariaLabel?: string; label: string;
} & Pick<ComponentProps<"button">, "id" | "aria-describedby" | "aria-invalid">) {
  return <Switch data-settings-inline-action {...accessibility} aria-label={ariaLabel ?? label} isSelected={checked} isDisabled={disabled} onChange={onChange} size="sm"
    validationBehavior="aria" isInvalid={Boolean(invalid && invalid !== "false")}>
    <Switch.Content>
      <Switch.Control><Switch.Thumb /></Switch.Control>
      <span className="sr-only">{label}</span>
    </Switch.Content>
  </Switch>;
}
