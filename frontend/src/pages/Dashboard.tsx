"use client";

import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ExternalLink,
  ArrowRight,
  RotateCcw,
  Download,
  X,
  Calendar,
  Filter,
} from "lucide-react";
import { KPICard } from "@/components/dashboard/KPICard";
import { RegionComparisonChart } from "@/components/dashboard/RegionComparisonChart";
import { AgingBucketChart } from "@/components/dashboard/AgingBucketChart";
import { CollectionTrendChart } from "@/components/dashboard/CollectionTrendChart";
import { NeedsAttentionCard } from "@/components/dashboard/NeedsAttentionCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  dashboardApi,
  type DashboardData,
  type UploadRowData,
} from "@/lib/api";

const PRESET_OPTIONS = [
  { value: "all", label: "All time" },
  { value: "this_month", label: "This month" },
  { value: "last_month", label: "Last month" },
  { value: "last_3_months", label: "Last 3 months" },
  { value: "this_fy", label: "This FY (Jul - Jun)" },
  { value: "last_fy", label: "Last FY (Jul - Jun)" },
  { value: "custom", label: "Custom range" },
];

export function Dashboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = React.useState<DashboardData | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const preset = searchParams.get("preset") || "all";
  const fromMonth = searchParams.get("from") || "";
  const toMonth = searchParams.get("to") || "";
  const region = searchParams.get("region") || "";
  const channel = searchParams.get("channel") || "";

  React.useEffect(() => {
    async function fetchDashboard() {
      try {
        setLoading(true);
        const result = await dashboardApi.getDashboard({
          preset,
          from: fromMonth || undefined,
          to: toMonth || undefined,
          region: region || undefined,
          channel: channel || undefined,
        });
        setData(result);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load dashboard");
      } finally {
        setLoading(false);
      }
    }
    fetchDashboard();
  }, [preset, fromMonth, toMonth, region, channel]);

  const updateParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (value && value !== "all") {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    setSearchParams(next);
  };

  const handlePresetChange = (newPreset: string) => {
    const next = new URLSearchParams(searchParams);
    if (newPreset === "all") {
      next.delete("preset");
      next.delete("from");
      next.delete("to");
    } else {
      next.set("preset", newPreset);
      if (newPreset !== "custom") {
        next.delete("from");
        next.delete("to");
      }
    }
    setSearchParams(next);
  };

  const handleReset = () => {
    setSearchParams(new URLSearchParams());
  };

  const getExportUrl = () => {
    const query = new URLSearchParams();
    if (preset && preset !== "all") query.set("preset", preset);
    if (fromMonth) query.set("from", fromMonth);
    if (toMonth) query.set("to", toMonth);
    if (region) query.set("region", region);
    if (channel && channel !== "all") query.set("channel", channel);
    const qs = query.toString();
    return `/api/v1/dashboard/export${qs ? `?${qs}` : ""}`;
  };

  const hasActiveFilters =
    preset !== "all" || Boolean(fromMonth) || Boolean(toMonth) || Boolean(region) || Boolean(channel);

  if (loading && !data) {
    return <DashboardSkeleton />;
  }

  if (error && !data) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-text-primary">Dashboard</h1>
            <p className="text-text-secondary mt-1">Failed to load data</p>
          </div>
        </div>
        <Card className="border-critical/50 bg-critical-light/10 p-6">
          <p className="text-critical">{error}</p>
          <Button className="mt-4" onClick={() => window.location.reload()}>Retry</Button>
        </Card>
      </div>
    );
  }

  const kpis = data?.kpis || [];
  const regions = data?.regions || [];
  const aging = data?.aging || [];
  const trend = data?.trend || [];
  const attention = data?.attention || [];
  const recentUploads = data?.recentUploads || [];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Dashboard</h1>
          <p className="text-text-secondary mt-1">
            {data?.asOfDate ? `As of ${formatDate(data.asOfDate)}` : "No data"} •{" "}
            {data?.lastUploadAt ? `Last upload: ${formatDateTime(data.lastUploadAt)}` : "No uploads"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <a
            href={getExportUrl()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-border bg-surface hover:bg-neutral-light transition-colors text-text-primary"
            download
          >
            <Download className="h-3.5 w-3.5" />
            <span>Export CSV</span>
          </a>
          <div className="flex items-center gap-2">
            <Badge variant="primary">Internal</Badge>
            <Badge variant="warning">External</Badge>
          </div>
        </div>
      </div>

      {/* Date & Filter Controls Card */}
      <Card className="p-4 bg-surface/50 border border-border">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-text-secondary font-medium">
            <Filter className="h-4 w-4" />
            <span>Filters:</span>
          </div>

          {/* Preset Dropdown */}
          <div className="flex items-center gap-2">
            <label htmlFor="preset-select" className="text-xs text-text-secondary">
              Period
            </label>
            <select
              id="preset-select"
              value={preset}
              onChange={(e) => handlePresetChange(e.target.value)}
              className="text-xs font-medium bg-surface border border-border rounded-md px-2.5 py-1.5 text-text-primary focus:outline-none focus:ring-1 focus:ring-primary"
            >
              {PRESET_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* From / To Month Pickers for Custom */}
          {preset === "custom" && (
            <div className="flex items-center gap-2 flex-wrap">
              <div className="flex items-center gap-1.5">
                <Calendar className="h-3.5 w-3.5 text-text-secondary" />
                <span className="text-xs text-text-secondary">From:</span>
                <input
                  type="month"
                  value={fromMonth}
                  onChange={(e) => updateParam("from", e.target.value)}
                  className="text-xs bg-surface border border-border rounded-md px-2 py-1 text-text-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-text-secondary">To:</span>
                <input
                  type="month"
                  value={toMonth}
                  onChange={(e) => updateParam("to", e.target.value)}
                  className="text-xs bg-surface border border-border rounded-md px-2 py-1 text-text-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
            </div>
          )}

          {/* Channel Filter */}
          <div className="flex items-center gap-2">
            <label htmlFor="channel-select" className="text-xs text-text-secondary">
              Channel
            </label>
            <select
              id="channel-select"
              value={channel || "all"}
              onChange={(e) => updateParam("channel", e.target.value)}
              className="text-xs font-medium bg-surface border border-border rounded-md px-2.5 py-1.5 text-text-primary focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="all">All Channels</option>
              <option value="internal">Internal (Salary)</option>
              <option value="external">External</option>
            </select>
          </div>

          {/* Region Filter */}
          <div className="flex items-center gap-2">
            <label htmlFor="region-input" className="text-xs text-text-secondary">
              Region
            </label>
            <input
              id="region-input"
              type="text"
              placeholder="e.g. Thimphu"
              value={region}
              onChange={(e) => updateParam("region", e.target.value)}
              className="text-xs bg-surface border border-border rounded-md px-2.5 py-1.5 w-28 text-text-primary focus:outline-none focus:ring-1 focus:ring-primary placeholder:text-text-secondary/50"
            />
          </div>

          {/* Reset Button */}
          {hasActiveFilters && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleReset}
              className="h-8 gap-1.5 text-xs text-text-secondary hover:text-text-primary ml-auto"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              <span>Reset</span>
            </Button>
          )}
        </div>

        {/* Active-filter chips */}
        {hasActiveFilters && (
          <div className="flex items-center gap-2 flex-wrap mt-3 pt-3 border-t border-border/50 text-xs">
            <span className="text-text-secondary">Active filters:</span>
            {preset !== "all" && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-primary/10 text-primary font-medium">
                Period: {PRESET_OPTIONS.find((o) => o.value === preset)?.label || preset}
                {preset === "custom" && (fromMonth || toMonth) && ` (${fromMonth || "start"} to ${toMonth || "end"})`}
                <button
                  type="button"
                  onClick={() => handlePresetChange("all")}
                  className="hover:text-primary-dark ml-0.5"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}
            {channel && channel !== "all" && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-warning/10 text-warning-dark font-medium">
                Channel: {channel}
                <button
                  type="button"
                  onClick={() => updateParam("channel", null)}
                  className="hover:text-critical ml-0.5"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}
            {region && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-neutral-light text-text-primary font-medium">
                Region: {region}
                <button
                  type="button"
                  onClick={() => updateParam("region", null)}
                  className="hover:text-critical ml-0.5"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}
          </div>
        )}
      </Card>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((kpi, index) => (
          <KPICard key={index} {...kpi} />
        ))}
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column - Charts */}
        <div className="lg:col-span-7 space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <RegionComparisonChart data={regions} />
            <AgingBucketChart data={aging} />
          </div>
          <CollectionTrendChart data={trend} />
        </div>

        {/* Right Column - Needs Attention + Quick Actions */}
        <div className="lg:col-span-5 space-y-6">
          <NeedsAttentionCard items={attention} />

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
                {recentUploads.length === 0 ? (
                  <p className="text-text-secondary text-center py-4">No uploads yet</p>
                ) : (
                  recentUploads.map((upload) => (
                    <UploadRow key={upload.id} upload={upload} />
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-64 mt-1" />
        </div>
        <div className="flex items-center gap-2">
          <Skeleton className="h-6 w-20" />
          <Skeleton className="h-6 w-20" />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => <KPICardSkeleton key={i} />)}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-7 space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ChartSkeleton />
            <ChartSkeleton />
          </div>
          <ChartSkeleton />
        </div>
        <div className="lg:col-span-5 space-y-6">
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
      </div>
    </div>
  );
}

function KPICardSkeleton() {
  return (
    <div className="kpi-card">
      <Skeleton className="h-4 w-32 mb-2" />
      <Skeleton className="h-8 w-24 mb-2" />
      <Skeleton className="h-4 w-24" />
    </div>
  );
}

function ChartSkeleton() {
  return (
    <div className="card p-6 h-[350px]">
      <Skeleton className="h-6 w-40 mb-4" />
      <Skeleton className="h-full w-full" />
    </div>
  );
}

function CardSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-6 w-32" />
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
        </div>
      </CardContent>
    </Card>
  );
}

function UploadRow({ upload }: { upload: UploadRowData }) {
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
          <p className="font-medium text-text-primary">{upload.file_name}</p>
          <p className="text-sm text-text-secondary">{upload.date} • {upload.contracts} contracts</p>
        </div>
      </div>
      <Badge variant={statusVariants[upload.status] || "neutral"}>
        {upload.status}
      </Badge>
    </div>
  );
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

function formatDateTime(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}