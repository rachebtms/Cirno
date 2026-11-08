import * as React from "react";
import { TextArea } from "@heroui/react";
import { cn } from "@/lib/utils";
export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => <TextArea ref={ref}
    className={cn("touch-text-input min-h-24 w-full text-ui-body", className)} {...props} />,
);
Textarea.displayName = "Textarea";
