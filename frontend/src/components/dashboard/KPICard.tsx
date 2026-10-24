"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface KPICardProps {
  title: string;
  value: string | number;
  change?: number;
  changeLabel?: string;
  icon?: React.ReactNode;
  trend?: "up" | "down" | "neutral";
  className?: string;
}

export function KPICard({ title, value, change, changeLabel, icon, trend = "neutral", className }: KPICardProps) {
  const TrendIcon = trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : Minus;
  const trendColor = trend === "up" ? "text-success" : trend === "down" ? "text-critical" : "text-neutral";

  return (
    <div className={cn("kpi-card", className)}>
      <div className="flex items-start justify-between">
        <div>
          <p className="kpi-label">{title}</p>
          <p className="kpi-value tabular-nums">{value}</p>
          {change !== undefined && (
            <div className={cn("kpi-change flex items-center gap-1", trendColor)}>
              <TrendIcon className="h-3.5 w-3.5" />
              <span>{change >= 0 ? "+" : ""}{change.toFixed(1)}%</span>
              {changeLabel && <span className="text-text-secondary">vs {changeLabel}</span>}
            </div>
          )}
        </div>
        {icon && <div className="text-neutral">{icon}</div>}
      </div>
    </div>
  );
}