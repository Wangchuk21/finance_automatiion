import * as React from "react";
import { cn } from "@/lib/utils";
import { Check } from "lucide-react";

export type StepperStepStatus = "pending" | "active" | "completed" | "error";

export interface StepperStep {
  id: string;
  label: string;
  status: StepperStepStatus;
  icon?: React.ReactNode;
}

interface StepperProps {
  steps: StepperStep[];
  className?: string;
}

function Stepper({ steps, className }: StepperProps) {
  return (
    <div className={cn("flex items-center justify-between w-full", className)}>
      {steps.map((step, index) => (
        <StepperStepComponent key={step.id} step={step} isLast={index === steps.length - 1} />
      ))}
    </div>
  );
}

function StepperStepComponent({ step, isLast }: { step: StepperStep; isLast: boolean }) {
  const statusStyles = {
    pending: "bg-background border-border text-text-secondary",
    active: "bg-primary border-primary text-primary-foreground",
    completed: "bg-success border-success text-white",
    error: "bg-critical border-critical text-white",
  };

  return (
    <div className="flex flex-col items-center relative z-10 flex-1">
      {!isLast && (
        <div
          className={cn(
            "absolute top-3 left-1/2 w-full h-1 -translate-x-1/2 z-[-1]",
            step.status === "completed" ? "bg-success" : "bg-border"
          )}
        />
      )}
      <div
        className={cn(
          "relative z-10 flex h-6 w-6 items-center justify-center rounded-full border-2 text-table-meta font-medium transition-all",
          statusStyles[step.status]
        )}
      >
        {step.status === "completed" ? (
          <Check className="h-3.5 w-3.5" />
        ) : (
          step.icon
        )}
      </div>
      <span
        className={cn(
          "mt-2 text-table-meta text-center text-text-secondary transition-colors",
          step.status === "active" && "text-text-primary font-medium"
        )}
      >
        {step.label}
      </span>
    </div>
  );
}

export { Stepper };