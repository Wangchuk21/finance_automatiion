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
import { dashboardApi, type DashboardData, type AttentionItem, type UploadRowData } from "@/lib/api";

export function Dashboard() {
  const [data, setData] = React.useState<DashboardData | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    async function fetchDashboard() {
      try {
        setLoading(true);
        const result = await dashboardApi.getDashboard();
        setData(result);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load dashboard");
      } finally {
        setLoading(false);
      }
    }
    fetchDashboard();
  }, []);

  if (loading) {
    return <DashboardSkeleton />;
  }

  if (error) {
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

  if (!data) return <DashboardSkeleton />;

  const kpis = data.kpis;
  const regions = data.regions;
  const aging = data.aging;
  const trend = data.trend;
  const attention = data.attention;
  const recentUploads = data.recentUploads;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Dashboard</h1>
          <p className="text-text-secondary mt-1">
            {data.asOfDate ? `As of ${formatDate(data.asOfDate)}` : "No data"} •{" "}
            {data.lastUploadAt ? `Last upload: ${formatDateTime(data.lastUploadAt)}` : "No uploads"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="primary">Internal</Badge>
          <Badge variant="warning">External</Badge>
        </div>
      </div>

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