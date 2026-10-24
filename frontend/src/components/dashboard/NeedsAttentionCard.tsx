"use client";

import * as React from "react";
import { AlertTriangle, AlertCircle, FileText, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

interface AttentionItem {
  id: string;
  type: "missing_contract" | "validation_warning" | "pending_review";
  title: string;
  description: string;
  count?: number;
  actionLabel?: string;
  onAction?: () => void;
}

interface NeedsAttentionCardProps {
  items: AttentionItem[];
  className?: string;
}

export function NeedsAttentionCard({ items, className }: NeedsAttentionCardProps) {
  if (items.length === 0) {
    return (
      <div className={cn("card p-6", className)}>
        <div className="flex items-center gap-3 text-success">
          <div className="p-2 rounded-full bg-success-light">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <p className="font-medium text-text-primary">All clear</p>
            <p className="text-sm text-text-secondary">No items need attention at this time</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("card p-6", className)}>
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 rounded-full bg-critical-light">
          <AlertTriangle className="h-5 w-5 text-critical" />
        </div>
        <div>
          <h3 className="font-semibold text-text-primary">Needs Attention</h3>
          <p className="text-sm text-text-secondary">{items.length} item{items.length > 1 ? "s" : ""} require review</p>
        </div>
      </div>

      <div className="space-y-3">
        {items.map((item) => (
          <div key={item.id} className="flex items-center gap-3 p-3 rounded-lg bg-neutral-light/50 border border-border">
            <div className={cn("p-2 rounded-full", getItemBgColor(item.type))}>
              {getItemIcon(item.type)}
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-medium text-text-primary">{item.title}</p>
              <p className="text-sm text-text-secondary">{item.description}</p>
              {item.count && (
                <Badge variant={getBadgeVariant(item.type)} className="mt-1">
                  {item.count} contract{item.count > 1 ? "s" : ""}
                </Badge>
              )}
            </div>
            {item.actionLabel && item.onAction && (
              <button
                onClick={item.onAction}
                className="text-sm text-primary hover:underline font-medium"
              >
                {item.actionLabel}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function getItemBgColor(type: AttentionItem["type"]) {
  switch (type) {
    case "missing_contract":
      return "bg-critical-light";
    case "validation_warning":
      return "bg-warning-light";
    case "pending_review":
      return "bg-primary/10";
    default:
      return "bg-neutral-light";
  }
}

function getItemIcon(type: AttentionItem["type"]) {
  switch (type) {
    case "missing_contract":
      return <AlertCircle className="h-5 w-5 text-critical" />;
    case "validation_warning":
      return <AlertTriangle className="h-5 w-5 text-warning" />;
    case "pending_review":
      return <Clock className="h-5 w-5 text-primary" />;
    default:
      return <AlertTriangle className="h-5 w-5 text-neutral" />;
  }
}

function getBadgeVariant(type: AttentionItem["type"]) {
  switch (type) {
    case "missing_contract":
      return "critical";
    case "validation_warning":
      return "warning";
    case "pending_review":
      return "primary";
    default:
      return "neutral";
  }
}