import * as React from "react";
import { Input as HeroInput } from "@heroui/react";
import { cn } from "@/lib/utils";
type InputProps = React.InputHTMLAttributes<HTMLInputElement>;
export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, ...props }, ref) =>
    <HeroInput ref={ref} className={cn("touch-text-input h-10 w-full min-w-0 text-ui-body", className)} {...props} />,
);
Input.displayName = "Input";
export const SearchInput = React.forwardRef<HTMLInputElement, InputProps>(
  (props, ref) => <Input {...props} ref={ref} type="search" />,
);
SearchInput.displayName = "SearchInput";
