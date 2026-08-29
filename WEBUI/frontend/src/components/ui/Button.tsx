import { forwardRef } from "react";
import type { ButtonHTMLAttributes } from "react";

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: "primary" | "secondary" | "danger" | "ghost";
  }
>(function Button({ variant = "primary", ...props }, ref) {
  return <button ref={ref} className={`button button-${variant}`} {...props} />;
});
