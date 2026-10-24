import * as React from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "success" | "warning" | "critical" | "neutral" | "primary";
}

const badgeVariants = {
  default: "bg-primary/10 text-primary",
  success: "bg-success-light text-success dark:bg-success-light/20",
  warning: "bg-warning-light text-warning dark:bg-warning-light/20",
  critical: "bg-critical-light text-critical dark:bg-critical-light/20",
  neutral: "bg-neutral-light text-neutral dark:bg-neutral-light/20",
  primary: "bg-primary/10 text-primary",
};

function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium",
        badgeVariants[variant],
        className
      )}
      {...props}
    />
  );
}

export { Badge };