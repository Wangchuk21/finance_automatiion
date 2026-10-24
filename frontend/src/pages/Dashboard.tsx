"use client";

import * as React from "react";
import { Link } from "react-router-dom";
import { TrendingUp, TrendingDown, Minus, ExternalLink, ArrowRight } from "lucide-react";
import { KPICard } from "@/components/dashboard/KPICard";
import { RegionComparisonChart } from "@/components/dashboard/RegionComparisonChart";
import { AgingBucketChart } from "@/components/dashboard/AgingBucketChart";
import { CollectionTrendChart } from "@/components/dashboard/CollectionTrendChart";
import { NeedsAttentionCard } from "@/components/dashboard/NeedsAttentionCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

// Mock data - replace with API calls
const mockKPIs = [
  {
    title: "Total Receivable",
    value: "₹1,22,64,000",
    change: 3.2,
    changeLabel: "last upload",
    trend: "up" as const,
  },
  {
    title: "Collected",
    value: "₹87,45,000",
    change: 5.1,
    changeLabel: "last upload",
    trend: "up" as const,
  },
  {
    title: "Overdue",
    value: "₹35,19,000",
    change: -2.1,
    changeLabel: "last upload",
    trend: "down" as const,
  },
  {
    title: "Critical Accounts",
    value: "142",
    change: 12,
    changeLabel: "last upload",
    trend: "up" as const,
  },
];

const mockRegionData = [
  { region: "North", receivable: 4500000, collected: 3200000, overdue: 1300000 },
  { region: "South", receivable: 3800000, collected: 2900000, overdue: 900000 },
  { region: "East", receivable: 2500000, collected: 1800000, overdue: 700000 },
  { region: "West", receivable: 1500000, collected: 850000, overdue: 650000 },
];

const mockAgingData = [
  { bucket: "0-30", amount: 4200000, count: 89 },
  { bucket: "31-60", amount: 2800000, count: 56 },
  { bucket: "61-90", amount: 1500000, count: 34 },
  { bucket: "91-120", amount: 900000, count: 21 },
  { bucket: "120+", amount: 600000, count: 18 },
];

const mockTrendData = [
  { month: "May", internal: 1200000, external: 800000, total: 2000000 },
  { month: "Jun", internal: 1350000, external: 900000, total: 2250000 },
  { month: "Jul", internal: 1400000, external: 950000, total: 2350000 },
  { month: "Aug", internal: 1500000, external: 1000000, total: 2500000 },
  { month: "Sep", internal: 1650000, external: 1100000, total: 2750000 },
  { month: "Oct", internal: 1800000, external: 1200000, total: 3000000 },
];

const mockAttentionItems = [
  {
    id: "1",
    type: "missing_contract" as const,
    title: "Missing contracts from last upload",
    description: "14 contracts from Sep 24 upload not found in Oct 24 file",
    count: 14,
    actionLabel: "Review missing",
    onAction: () => console.log("Review missing"),
  },
  {
    id: "2",
    type: "validation_warning" as const,
    title: "Validation warnings in latest upload",
    description: "3 contracts have mismatched payment type vs month columns",
    count: 3,
    actionLabel: "View warnings",
    onAction: () => console.log("View warnings"),
  },
];

export function Dashboard() {
  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Dashboard</h1>
          <p className="text-text-secondary mt-1">As of Oct 2024 • Last upload: 28 Oct 2024</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="primary">Internal</Badge>
          <Badge variant="warning">External</Badge>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {mockKPIs.map((kpi, index) => (
          <KPICard key={index} {...kpi} />
        ))}
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column - Charts */}
        <div className="lg:col-span-7 space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <RegionComparisonChart data={mockRegionData} />
            <AgingBucketChart data={mockAgingData} />
          </div>
          <CollectionTrendChart data={mockTrendData} />
        </div>

        {/* Right Column - Needs Attention + Quick Actions */}
        <div className="lg:col-span-5 space-y-6">
          <NeedsAttentionCard items={mockAttentionItems} />

          {/* Quick Actions */}
          <Card>
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Button className="w-full justify-start gap-3" asChild>
                <Link to="/uploads">
                  <span>Upload New File</span>
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button variant="outline" className="w-full justify-start gap-3" asChild>
                <Link to="/reports">
                  <span>View Reports</span>
                  <ExternalLink className="h-4 w-4" />
                </Link>
              </Button>
              <Button variant="outline" className="w-full justify-start gap-3" asChild>
                <Link to="/contracts">
                  <span>Browse Contracts</span>
                  <ExternalLink className="h-4 w-4" />
                </Link>
              </Button>
            </CardContent>
          </Card>

          {/* Recent Uploads */}
          <Card>
            <CardHeader>
              <CardTitle>Recent Uploads</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <UploadRow
                  name="EMI_Oct_2024.xlsx"
                  date="28 Oct 2024"
                  status="confirmed"
                  contracts={156}
                />
                <UploadRow
                  name="EMI_Sep_2024.xlsx"
                  date="25 Sep 2024"
                  status="confirmed"
                  contracts={148}
                />
                <UploadRow
                  name="EMI_Aug_2024.xlsx"
                  date="28 Aug 2024"
                  status="confirmed"
                  contracts={142}
                />
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function UploadRow({ name, date, status, contracts }: { name: string; date: string; status: string; contracts: number }) {
  const statusVariants: Record<string, "success" | "warning" | "neutral"> = {
    confirmed: "success",
    pending: "warning",
    rolled_back: "neutral",
  };

  return (
    <div className="flex items-center justify-between p-3 rounded-lg bg-neutral-light/50 border border-border">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-full bg-primary/10">
          <span className="text-primary">📄</span>
        </div>
        <div>
          <p className="font-medium text-text-primary">{name}</p>
          <p className="text-sm text-text-secondary">{date} • {contracts} contracts</p>
        </div>
      </div>
      <Badge variant={statusVariants[status] || "neutral"}>{status}</Badge>
    </div>
  );
}