import { Description, Label, Switch } from "@heroui/react";
import type { ReactNode } from "react";
import "./toggle-field.css";
export function ToggleField({ label, description, selected, onChange, disabled, id, className = "", labelHidden = false }: {
  label: string; description?: ReactNode; selected: boolean; onChange: (selected: boolean) => void;
  disabled?: boolean; id?: string; className?: string; labelHidden?: boolean;
}) {
  return <Switch id={id} aria-label={label} isSelected={selected} onChange={onChange} isDisabled={disabled} className={`interface-toggle ${labelHidden ? "interface-toggle-compact" : ""} ${className}`}>
    <Switch.Content><Label className={labelHidden ? "sr-only" : undefined}>{label}</Label><Switch.Control><Switch.Thumb /></Switch.Control></Switch.Content>
    {description && <Description>{description}</Description>}
  </Switch>;
}
