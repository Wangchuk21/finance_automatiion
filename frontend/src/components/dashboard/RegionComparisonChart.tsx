"use client";

import * as React from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { cn } from "@/lib/utils";

interface RegionComparisonChartProps {
  data: Array<{ region: string; receivable: number; collected: number; overdue: number }>;
  className?: string;
}

export function RegionComparisonChart({ data, className }: RegionComparisonChartProps) {
  const COLORS = ["#1F4FD8", "#16A34A", "#DC2626"];

  return (
    <div className={cn("card p-6 h-[350px]", className)}>
      <h3 className="card-title mb-4">Receivable by Region</h3>
      <div className="h-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false} />
            <XAxis type="number" tick={{ fill: "#6B7280", fontSize: 11 }} tickFormatter={(v) => `₹${(v/1e5).toFixed(1)}L`} />
            <YAxis
              dataKey="region"
              type="category"
              width={80}
              tick={{ fill: "#111827", fontSize: 12, fontWeight: 500 }}
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
              formatter={(value: number, name: string) => [
                `₹${value.toLocaleString("en-IN")}`,
                name === "receivable" ? "Receivable" : name === "collected" ? "Collected" : "Overdue",
              ]}
            />
            <Bar dataKey="receivable" name="Receivable" fill="#1F4FD8" radius={[0, 4, 4, 0]} maxBarSize={32}>
              <Cell fill="#1F4FD8" />
            </Bar>
            <Bar dataKey="collected" name="Collected" fill="#16A34A" radius={[0, 4, 4, 0]} maxBarSize={32}>
              <Cell fill="#16A34A" />
            </Bar>
            <Bar dataKey="overdue" name="Overdue" fill="#DC2626" radius={[0, 4, 4, 0]} maxBarSize={32}>
              <Cell fill="#DC2626" />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}