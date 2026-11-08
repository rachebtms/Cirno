import type { ReactNode } from "react";
import { Radio, RadioGroup, Tabs, ToggleButton } from "@heroui/react";
import { toggleButtonVariants } from "@heroui/styles";
import { HoverHint } from "./hover-hint";
import { cn } from "@/lib/utils";
interface Option<T extends string> { value: T; label: ReactNode; ariaLabel?: string; tooltip?: string }
interface Props<T extends string> {
  value: T; options: Option<T>[]; onChange: (value: T) => void; ariaLabel?: string;
  mode?: "buttons" | "tabs" | "radio"; className?: string; itemClassName?: string;
  indicatorClassName?: string; animateIndicator?: boolean;
}
/** Selection geometry and keyboard navigation belong to the component library. */
export function SegmentedControl<T extends string>({ value, options, onChange, ariaLabel, mode = "buttons", className, itemClassName, indicatorClassName, animateIndicator = true }: Props<T>) {
  if (mode === "tabs") return <Tabs selectedKey={value} onSelectionChange={key => onChange(String(key) as T)}
    className={cn("segmented-control inline-flex w-fit max-w-full", className)}>
    <Tabs.ListContainer><Tabs.List aria-label={ariaLabel ?? "Views"}>
      {options.map(option => <Tabs.Tab key={option.value} id={option.value} aria-label={option.ariaLabel}
        className={cn("min-h-8 whitespace-nowrap text-ui-label", itemClassName)}>
        {option.label}<Tabs.Indicator className={cn(!animateIndicator && "transition-none", indicatorClassName)} />
      </Tabs.Tab>)}
    </Tabs.List></Tabs.ListContainer>
  </Tabs>;
  if (mode === "radio") return <RadioGroup aria-label={ariaLabel ?? "Options"}
    orientation="horizontal" value={value} onChange={next => onChange(next as T)}
    className={cn("segmented-control inline-flex max-w-full items-center gap-1 rounded-xl bg-default p-1", className)}>
    {options.map(option => {
      const content = <Radio.Content className={cn(toggleButtonVariants({ size: "sm" }), "whitespace-nowrap text-ui-label", itemClassName)}>
        {option.label}
      </Radio.Content>;
      return <Radio key={option.value} value={option.value} aria-label={option.ariaLabel}>
        {option.tooltip ? <HoverHint content={option.tooltip}><span className="inline-flex">{content}</span></HoverHint> : content}
      </Radio>;
    })}
  </RadioGroup>;
  const items = options.map(option => {
    const item = <ToggleButton key={option.value} id={option.value} aria-label={option.ariaLabel}
      isSelected={value === option.value}
      onChange={() => onChange(option.value)}
      size="sm" className={cn("whitespace-nowrap text-ui-label", itemClassName)}>{option.label}</ToggleButton>;
    return option.tooltip ? <HoverHint key={option.value} content={option.tooltip}>{item}</HoverHint> : item;
  });
  return <div role="group" aria-label={ariaLabel}
    className={cn("segmented-control inline-flex max-w-full items-center gap-1 rounded-xl bg-default p-1", className)}>{items}</div>;
}
