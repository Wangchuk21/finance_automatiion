"use client";

import * as React from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, Legend } from "recharts";
import { cn } from "@/lib/utils";

interface AgingBucketChartProps {
  data: Array<{ bucket: string; amount: number; count: number }>;
  className?: string;
}

export function AgingBucketChart({ data, className }: AgingBucketChartProps) {
  return (
    <div className={cn("card p-6 h-[350px]", className)}>
      <h3 className="card-title mb-4">Aging Buckets</h3>
      <div className="h-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 10, right: 10, left: 10, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false} />
            <XAxis type="number" tick={{ fill: "#6B7280", fontSize: 11 }} tickFormatter={(v) => `₹${(v/1e5).toFixed(1)}L`} />
            <YAxis
              dataKey="bucket"
              type="category"
              width={100}
              tick={{ fill: "#111827", fontSize: 12 }}
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
              formatter={(value: number) => [`₹${value.toLocaleString("en-IN")}`, "Amount"]}
            />
            <Legend />
            <Bar dataKey="amount" name="Amount" fill="#1F4FD8" radius={[0, 4, 4, 0]} maxBarSize={32}>
              {data.map((_, index) => (
                <Cell key={`cell-${index}`} fill={getBucketColor(data[index].bucket)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function getBucketColor(bucket: string): string {
  const colors: Record<string, string> = {
    "0-30": "#16A34A",
    "31-60": "#D97706",
    "61-90": "#F59E0B",
    "91-120": "#EF4444",
    "120+": "#DC2626",
  };
  return colors[bucket] || "#1F4FD8";
}