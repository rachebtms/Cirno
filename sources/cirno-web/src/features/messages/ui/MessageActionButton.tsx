import { Button } from "@heroui/react";
import type { ComponentProps } from "react";
import { Hint } from "@/ui/feedback/Hint";

export function MessageActionButton({
  label,
  children,
  className = "",
  ...props
}: ComponentProps<typeof Button> & { label: string }) {
  return (
    <Hint content={label}>
      <Button
        type="button"
        isIconOnly
        size="sm"
        variant="ghost"
        aria-label={label}
        className={`message-action ${className}`}
        {...props}
      >
        {children}
      </Button>
    </Hint>
  );
}
