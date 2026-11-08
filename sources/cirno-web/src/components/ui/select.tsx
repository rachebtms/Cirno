import * as React from "react";
import { ListBox, Select as HeroSelect, Separator } from "@heroui/react";
import { useFloatingPortal } from "./floating-portal";
import { cn } from "@/lib/utils";

interface SelectProps {
  children: React.ReactNode; value?: string; defaultValue?: string; disabled?: boolean;
  open?: boolean; onOpenChange?: (open: boolean) => void; onValueChange?: (value: string) => void;
  required?: boolean; name?: string;
}
export function Select<T extends string = string>({ children, value, defaultValue, disabled, open, onOpenChange, onValueChange, required, name }: Omit<SelectProps, "onValueChange"> & { onValueChange?: (value: T) => void }) {
  const trigger = React.Children.toArray(children).find(child => React.isValidElement<{ "aria-label"?: string }>(child) && child.props["aria-label"]);
  const label = React.isValidElement<{ "aria-label"?: string }>(trigger) ? trigger.props["aria-label"] : undefined;
  return <HeroSelect aria-label={label} value={value || null} defaultValue={defaultValue} isDisabled={disabled}
    isOpen={open} onOpenChange={onOpenChange} onChange={key => { if (key !== null) onValueChange?.(String(key) as T); }}
    isRequired={required} name={name} className="min-w-0">
    {children}
  </HeroSelect>;
}
export const SelectTrigger = React.forwardRef<HTMLButtonElement, Omit<React.ComponentProps<typeof HeroSelect.Trigger>, "className" | "children"> & {className?: string; children?: React.ReactNode; disabled?: boolean}>(
  ({ className, children, disabled, onFocus, onBlur, ...props }, ref) => <HeroSelect.Trigger ref={ref} isDisabled={disabled}
    render={domProps => <button {...domProps} role="combobox" aria-labelledby={undefined} aria-label={props["aria-label"]} />}
    onFocus={onFocus ? event => onFocus(event as React.FocusEvent<HTMLButtonElement>) : undefined}
    onBlur={onBlur ? event => onBlur(event as React.FocusEvent<HTMLButtonElement>) : undefined}
    className={cn("h-10 w-full min-w-0 text-ui-body", className)} {...props}>
    {children}<HeroSelect.Indicator />
  </HeroSelect.Trigger>,
);
SelectTrigger.displayName = "SelectTrigger";
export function SelectValue({ placeholder, children }: { placeholder?: string; children?: React.ReactNode }) {
  return <HeroSelect.Value className="min-w-0 truncate">{children ?? (({ selectedText }) => selectedText || placeholder)}</HeroSelect.Value>;
}
export function SelectContent({ children }: { children?: React.ReactNode }) {
  const container = useFloatingPortal();
  return <HeroSelect.Popover UNSTABLE_portalContainer={container ?? undefined} className="z-50 max-h-[min(24rem,calc(100dvh-2rem))] min-w-[var(--trigger-width)]">
    <ListBox>{children}</ListBox>
  </HeroSelect.Popover>;
}
export function SelectItem({ value, children, className, disabled, textValue }: {
  value: string; children?: React.ReactNode; className?: string; disabled?: boolean; textValue?: string;
}) {
  return <ListBox.Item id={value} textValue={textValue ?? (typeof children === "string" ? children : value)}
    isDisabled={disabled} className={cn("min-h-9 text-ui-body", className)}>
    {children}<ListBox.ItemIndicator />
  </ListBox.Item>;
}
export const SelectSeparator = Separator;
