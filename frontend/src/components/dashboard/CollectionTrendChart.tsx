"use client";

import * as React from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { cn } from "@/lib/utils";

interface CollectionTrendChartProps {
  data: Array<{ month: string; internal: number; external: number; total: number }>;
  className?: string;
}

export function CollectionTrendChart({ data, className }: CollectionTrendChartProps) {
  return (
    <div className={cn("card p-6 h-[350px]", className)}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="card-title">Collection Trend</h3>
        <div className="flex items-center gap-4 text-sm text-text-secondary">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-primary" />
            Internal
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-warning" />
            External
          </span>
        </div>
      </div>
      <div className="h-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
            <XAxis dataKey="month" tick={{ fill: "#6B7280", fontSize: 11 }} axisLine={{ stroke: "#E5E7EB" }} />
            <YAxis tick={{ fill: "#6B7280", fontSize: 11 }} tickFormatter={(v) => `₹${(v/1e5).toFixed(1)}L`} axisLine={false} tickLine={false} />
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
                name === "internal" ? "Internal" : name === "external" ? "External" : "Total",
              ]}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="internal"
              name="Internal"
              stroke="#1F4FD8"
              strokeWidth={2}
              dot={{ r: 4, fill: "#1F4FD8" }}
              activeDot={{ r: 6 }}
            />
            <Line
              type="monotone"
              dataKey="external"
              name="External"
              stroke="#D97706"
              strokeWidth={2}
              dot={{ r: 4, fill: "#D97706" }}
              activeDot={{ r: 6 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}