import { Tooltip } from "@heroui/react";
import { TooltipTriggerStateContext } from "react-aria-components";
import { cn } from "@/lib/utils";
import { useContext, type ReactNode } from "react";

function HintTarget({ children, className }: { children: ReactNode; className?: string }) {
  const state = useContext(TooltipTriggerStateContext)!;
  return <span className={cn("inline-flex min-w-0 shrink-0", className)}
    // Pointer entry precedes React Aria's global modality update after typing.
    // Its shared state still owns the delay, dismissal and keyboard behavior.
    onPointerMove={event => { if (event.pointerType === "mouse") state.open(); }}
    onPointerLeave={event => { if (event.pointerType === "mouse") state.close(); }}
    onPointerDownCapture={() => state.close(true)}
    onKeyDownCapture={() => state.close(true)}>
    {children}
  </span>;
}

export function Hint({ children, content, delay = 500, contentClassName, triggerClassName, placement = "top" }: {
  children: ReactNode; content: ReactNode; delay?: number; contentClassName?: string; triggerClassName?: string;
  placement?: "top" | "right" | "bottom" | "left";
}) {
  return <Tooltip delay={delay}>
    <HintTarget className={triggerClassName}>{children}</HintTarget>
    <Tooltip.Content className={contentClassName} placement={placement}>{content}</Tooltip.Content>
  </Tooltip>;
}
