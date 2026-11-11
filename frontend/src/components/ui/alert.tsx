import * as React from "react";
import { cn } from "@/lib/utils";

interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "destructive" | "warning" | "success";
}

export function Alert({ className, variant = "default", children, ...props }: AlertProps) {
  const variants = {
    default: "bg-neutral-light/80 text-text-primary border border-border",
    destructive: "bg-critical-light/80 text-critical border border-critical/50",
    warning: "bg-warning-light/80 text-warning-dark border border-warning/50",
    success: "bg-success-light/80 text-success border border-success/50",
  };

  return (
    <div
      className={cn("relative w-full rounded-lg border p-4", variants[variant], className)}
      role="alert"
      {...props}
    >
      {children}
    </div>
  );
}

export function AlertTitle({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <h5 className={cn("mb-1 font-medium leading-none tracking-tight", className)} {...props}>
      {children}
    </h5>
  );
}

export function AlertDescription({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("text-sm [&_p]:leading-relaxed", className)} {...props}>
      {children}
    </div>
  );
}