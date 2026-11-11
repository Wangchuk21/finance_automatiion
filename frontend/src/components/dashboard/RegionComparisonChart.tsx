"use client";

import * as React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { Maximize2, Minimize2 } from "lucide-react";
import { cn } from "@/lib/utils";

export type RegionMetric = "receivable" | "collected" | "balance_due";

interface RegionComparisonChartProps {
  data: Array<{
    region: string;
    receivable: number;
    collected: number;
    balance_due?: number;
    overdue?: number;
  }>;
  onRegionClick?: (region: string, metric?: RegionMetric) => void;
  className?: string;
}

type RegionTickProps = {
  x?: number;
  y?: number;
  payload?: { value?: string };
  onRegionClick?: (region: string, metric?: RegionMetric) => void;
};

function RegionTick({ x, y, payload, onRegionClick }: RegionTickProps) {
  return (
    <text
      x={x}
      y={y}
      dy={4}
      textAnchor="end"
      fill="#111827"
      fontSize={12}
      fontWeight={500}
      style={{ cursor: onRegionClick ? "pointer" : undefined }}
      onClick={() => {
        if (payload?.value) onRegionClick?.(payload.value);
      }}
    >
      {payload?.value}
    </text>
  );
}

export function RegionComparisonChart({ data, onRegionClick, className }: RegionComparisonChartProps) {
  const [expanded, setExpanded] = React.useState(false);

  // Normalize data so balance_due is populated regardless of field name
  const chartData = (data || []).map((d) => ({
    ...d,
    balance_due: d.balance_due ?? d.overdue ?? 0,
  }));

  React.useEffect(() => {
    if (!expanded) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setExpanded(false);
    };
    window.addEventListener("keydown", handleKeyDown);

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [expanded]);

  const handleRegionClick = (region: string, metric?: RegionMetric) => {
    setExpanded(false);
    onRegionClick?.(region, metric);
  };

  const handleBarClick = (entry: unknown, metric: RegionMetric) => {
    if (!onRegionClick) return;
    const item = entry as { region?: string; payload?: { region?: string } };
    const clicked = item?.region ?? item?.payload?.region;
    if (clicked) handleRegionClick(clicked, metric);
  };

  const renderChart = () => (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={chartData}
        layout="vertical"
        margin={{ top: 10, right: 40, left: 8, bottom: 10 }}
        barCategoryGap="22%"
      >
        <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false} />
        <XAxis
          type="number"
          tick={{ fill: "#6B7280", fontSize: 11 }}
          tickFormatter={(v) => (v === 0 ? "Nu. 0" : v >= 1e6 ? `Nu. ${(v / 1e6).toFixed(1)}M` : `Nu. ${(v / 1e3).toFixed(0)}K`)}
        />
        <YAxis
          dataKey="region"
          type="category"
          width={150}
          tick={<RegionTick onRegionClick={handleRegionClick} />}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "#FFFFFF",
            border: "1px solid #E5E7EB",
            borderRadius: "8px",
            boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)",
          }}
          labelStyle={{ color: "#111827", fontWeight: 600 }}
          formatter={(value, name) => [
            `Nu. ${Number(value).toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`,
            name === "receivable" ? "Receivable" : name === "collected" ? "Collected" : name === "balance_due" ? "Balance Due" : "",
          ]}
        />
        <Legend verticalAlign="bottom" wrapperStyle={{ fontSize: "12px", paddingTop: "8px" }} />
        <Bar dataKey="receivable" name="Receivable" fill="#1F4FD8" radius={[0, 4, 4, 0]} maxBarSize={32} onClick={(entry) => handleBarClick(entry, "receivable")} />
        <Bar dataKey="collected" name="Collected" fill="#16A34A" radius={[0, 4, 4, 0]} maxBarSize={32} onClick={(entry) => handleBarClick(entry, "collected")} />
        <Bar dataKey="balance_due" name="Balance Due" fill="#DC2626" radius={[0, 4, 4, 0]} maxBarSize={32} onClick={(entry) => handleBarClick(entry, "balance_due")} />
      </BarChart>
    </ResponsiveContainer>
  );

  const hint = onRegionClick ? (
    <p className="text-xs text-text-secondary mt-0.5">Click a colored bar to drill into that metric; click the region name for the same breakdown</p>
  ) : null;

  return (
    <>
      <div className={cn("card p-6 h-[420px]", className)}>
        <div className="flex items-start justify-between gap-3 mb-3">
          <div>
            <h3 className="card-title">Receivable by Region</h3>
            {hint}
          </div>
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="p-1.5 rounded-md text-text-secondary hover:bg-neutral-light hover:text-text-primary"
            aria-label="Expand region chart"
            title="Expand region chart"
          >
            <Maximize2 className="h-4 w-4" />
          </button>
        </div>
        <div className="h-[calc(100%-3.5rem)] [&_.recharts-bar-rectangle]:cursor-pointer">
          {renderChart()}
        </div>
      </div>

      {expanded && (
        <div
          className="fixed inset-0 z-50 bg-black/50 p-3 md:p-6"
          role="dialog"
          aria-modal="true"
          aria-label="Receivable by Region - expanded"
          onClick={() => setExpanded(false)}
        >
          <div
            className="bg-card border border-border rounded-xl shadow-2xl w-full h-full flex flex-col p-5 md:p-6"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3 mb-4">
              <div>
                <h3 className="card-title">Receivable by Region</h3>
                {hint}
              </div>
              <button
                type="button"
                onClick={() => setExpanded(false)}
                className="p-1.5 rounded-md text-text-secondary hover:bg-neutral-light hover:text-text-primary"
                aria-label="Close expanded chart"
                title="Close expanded chart"
              >
                <Minimize2 className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 min-h-0 [&_.recharts-bar-rectangle]:cursor-pointer">
              {renderChart()}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
