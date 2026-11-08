import * as React from "react";
import { Button as HeroButton, buttonVariants as heroButtonVariants } from "@heroui/react";
import { Slot } from "@radix-ui/react-slot";
import { cn } from "@/lib/utils";

type Variant = "default" | "accent" | "destructive" | "outline" | "secondary" | "ghost" | "icon" | "link";
type Size = "default" | "sm" | "control" | "lg" | "icon";
const variants = {
  default: "primary", accent: "primary", destructive: "danger", outline: "outline",
  secondary: "secondary", ghost: "ghost", icon: "ghost", link: "ghost",
} as const;
export function buttonVariants({ variant = "default", size = "default", className }: {
  variant?: Variant | null; size?: Size | null; className?: string;
} = {}) {
  return cn(heroButtonVariants({
    variant: variants[variant ?? "default"],
    size: size === "lg" ? "lg" : size === "sm" ? "sm" : "md",
    isIconOnly: size === "icon",
  }), "text-control-label", size === "control" && "control-layout", variant === "link" && "underline-offset-4 hover:underline", className);
}
interface ButtonProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "value"> {
  variant?: Variant | null; size?: Size | null; asChild?: boolean; value?: string;
}
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", asChild, disabled, onFocus, onBlur, onClick, onKeyDown, onKeyUp, title, "aria-busy": busy, ...props }, ref) => {
    const classes = buttonVariants({ variant, size, className });
    if (asChild) return <Slot ref={ref} className={classes} title={title} aria-busy={busy} onFocus={onFocus} onBlur={onBlur} onClick={onClick} onKeyDown={onKeyDown} onKeyUp={onKeyUp} {...props} />;
    return <HeroButton ref={ref} render={domProps => <button {...domProps} title={title} aria-busy={busy} />} className={classes} variant={variants[variant ?? "default"]}
      size={size === "lg" ? "lg" : size === "sm" ? "sm" : "md"}
      isIconOnly={size === "icon"} isDisabled={disabled}
      onClick={onClick ? event => onClick(event as React.MouseEvent<HTMLButtonElement>) : undefined}
      onKeyDown={onKeyDown ? event => onKeyDown(event as React.KeyboardEvent<HTMLButtonElement>) : undefined}
      onKeyUp={onKeyUp ? event => onKeyUp(event as React.KeyboardEvent<HTMLButtonElement>) : undefined}
      onFocus={onFocus ? event => onFocus(event as React.FocusEvent<HTMLButtonElement>) : undefined}
      onBlur={onBlur ? event => onBlur(event as React.FocusEvent<HTMLButtonElement>) : undefined} {...props} />;
  },
);
Button.displayName = "Button";
