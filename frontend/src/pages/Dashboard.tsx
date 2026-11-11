"use client";

import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ExternalLink,
  ArrowRight,
  ArrowLeft,
  ChevronRight,
  RotateCcw,
  Download,
  X,
  Calendar,
  Filter,
} from "lucide-react";
import { KPICard } from "@/components/dashboard/KPICard";
import {
  RegionComparisonChart,
  type RegionMetric,
} from "@/components/dashboard/RegionComparisonChart";
import { AgingBucketChart } from "@/components/dashboard/AgingBucketChart";
import { CollectionTrendChart } from "@/components/dashboard/CollectionTrendChart";
import { NeedsAttentionCard } from "@/components/dashboard/NeedsAttentionCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn, formatNumber } from "@/lib/utils";
import {
  dashboardApi,
  type CostCenterContractData,
  type CostCenterData,
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
  const [costCenterRegion, setCostCenterRegion] = React.useState<string | null>(null);
  const [costCenters, setCostCenters] = React.useState<CostCenterData[] | null>(null);
  const [costCentersLoading, setCostCentersLoading] = React.useState(false);
  const [costCentersError, setCostCentersError] = React.useState<string | null>(null);
  const [selectedCostCenter, setSelectedCostCenter] = React.useState<string | null>(null);
  const [costCenterContracts, setCostCenterContracts] = React.useState<CostCenterContractData[] | null>(null);
  const [contractsLoading, setContractsLoading] = React.useState(false);
  const [contractsError, setContractsError] = React.useState<string | null>(null);
  const [costMetric, setCostMetric] = React.useState<RegionMetric>("receivable");
  const drilldownRef = React.useRef<HTMLDivElement | null>(null);

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

  const openCostCenters = async (
    selectedRegion: string,
    metric?: RegionMetric
  ) => {
    setCostMetric(metric ?? costMetric);
    setCostCenterRegion(selectedRegion);
    setCostCenters(null);
    setCostCentersError(null);
    setCostCentersLoading(true);
    setSelectedCostCenter(null);
    setCostCenterContracts(null);
    setContractsError(null);
    try {
      const result = await dashboardApi.getCostCenters({
        preset,
        from: fromMonth || undefined,
        to: toMonth || undefined,
        region: selectedRegion,
        channel: channel || undefined,
      });
      setCostCenters(result);
    } catch (err) {
      setCostCentersError(
        err instanceof Error ? err.message : "Failed to load cost centers"
      );
    } finally {
      setCostCentersLoading(false);
    }
  };

  const openCostCenterContracts = async (selected: string) => {
    if (!costCenterRegion) return;
    setSelectedCostCenter(selected);
    setCostCenterContracts(null);
    setContractsError(null);
    setContractsLoading(true);
    try {
      const result = await dashboardApi.getCostCenterContracts({
        preset,
        from: fromMonth || undefined,
        to: toMonth || undefined,
        region: costCenterRegion,
        channel: channel || undefined,
        cost_center: selected,
      });
      setCostCenterContracts(result);
    } catch (err) {
      setContractsError(
        err instanceof Error ? err.message : "Failed to load customers"
      );
    } finally {
      setContractsLoading(false);
    }
  };

  const backToCostCenters = () => {
    setSelectedCostCenter(null);
    setCostCenterContracts(null);
    setContractsError(null);
  };

  const closeCostCenters = () => {
    setCostCenterRegion(null);
    setCostCenters(null);
    setCostCentersError(null);
    setSelectedCostCenter(null);
    setCostCenterContracts(null);
    setContractsError(null);
  };

  React.useEffect(() => {
    if (costCenterRegion) {
      drilldownRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [costCenterRegion]);

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

      {/* Region chart - full width */}
      <RegionComparisonChart data={regions} onRegionClick={openCostCenters} />

      {/* Region → Cost Center → Customer drill-down */}
      {costCenterRegion && (
        <div ref={drilldownRef} className="scroll-mt-24">
          <CostCenterDrilldown
            region={costCenterRegion}
            rows={costCenters}
            loading={costCentersLoading}
            error={costCentersError}
            selectedCostCenter={selectedCostCenter}
            contracts={costCenterContracts}
            contractsLoading={contractsLoading}
            contractsError={contractsError}
            metric={costMetric}
            onMetricChange={setCostMetric}
            onSelectCostCenter={openCostCenterContracts}
            onBack={backToCostCenters}
            onClose={closeCostCenters}
          />
        </div>
      )}

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column - Charts */}
        <div className="lg:col-span-7 space-y-6">
          <AgingBucketChart data={aging} />
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

const DRILL_METRICS: Record<
  RegionMetric,
  {
    label: string;
    activeButton: string;
    header: string;
    cell: string;
    tint: string;
    bar: string;
  }
> = {
  receivable: {
    label: "Receivable",
    activeButton: "bg-primary text-white shadow-sm",
    header: "text-primary",
    cell: "text-primary font-semibold",
    tint: "bg-primary/5",
    bar: "bg-primary",
  },
  collected: {
    label: "Collected",
    activeButton: "bg-success text-white shadow-sm",
    header: "text-success",
    cell: "text-success font-semibold",
    tint: "bg-success/5",
    bar: "bg-success",
  },
  balance_due: {
    label: "Balance Due",
    activeButton: "bg-critical text-white shadow-sm",
    header: "text-critical",
    cell: "text-critical font-semibold",
    tint: "bg-critical/5",
    bar: "bg-critical",
  },
};

function MetricSwitch({
  metric,
  onChange,
}: {
  metric: RegionMetric;
  onChange: (metric: RegionMetric) => void;
}) {
  return (
    <div className="inline-flex items-center gap-1 rounded-lg border border-border bg-card p-1">
      {(Object.keys(DRILL_METRICS) as RegionMetric[]).map((key) => (
        <button
          key={key}
          type="button"
          onClick={() => onChange(key)}
          aria-pressed={metric === key}
          className={cn(
            "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
            metric === key
              ? DRILL_METRICS[key].activeButton
              : "text-text-secondary hover:bg-neutral-light hover:text-text-primary"
          )}
        >
          {DRILL_METRICS[key].label}
        </button>
      ))}
    </div>
  );
}

function MetricBar({
  value,
  max,
  className,
}: {
  value: number;
  max: number;
  className?: string;
}) {
  return (
    <span className="block h-1 w-16 overflow-hidden rounded-full bg-black/5">
      <span
        className={cn("block h-full rounded-full", className)}
        style={{ width: `${Math.max(3, (value / max) * 100)}%` }}
      />
    </span>
  );
}

function CostCenterDrilldown({
  region,
  rows,
  loading,
  error,
  selectedCostCenter,
  contracts,
  contractsLoading,
  contractsError,
  metric,
  onMetricChange,
  onSelectCostCenter,
  onBack,
  onClose,
}: {
  region: string;
  rows: CostCenterData[] | null;
  loading: boolean;
  error: string | null;
  selectedCostCenter: string | null;
  contracts: CostCenterContractData[] | null;
  contractsLoading: boolean;
  contractsError: string | null;
  metric: RegionMetric;
  onMetricChange: (metric: RegionMetric) => void;
  onSelectCostCenter: (costCenter: string) => void;
  onBack: () => void;
  onClose: () => void;
}) {
  const active = DRILL_METRICS[metric];

  const sortedRows = React.useMemo(
    () => (rows ? [...rows].sort((a, b) => b[metric] - a[metric]) : null),
    [rows, metric]
  );

  const sortedContracts = React.useMemo(
    () =>
      contracts
        ? [...contracts].sort((a, b) => {
            const aValue = metric === "collected" ? a.collected : metric === "balance_due" ? a.balance_due : a.outstanding;
            const bValue = metric === "collected" ? b.collected : metric === "balance_due" ? b.balance_due : b.outstanding;
            return bValue - aValue;
          })
        : null,
    [contracts, metric]
  );

  const maxMetric = Math.max(
    ...(sortedRows || []).map((row) => row[metric]),
    1
  );
  const totals = (rows || []).reduce(
    (acc, row) => ({
      contracts: acc.contracts + row.contracts,
      receivable: acc.receivable + row.receivable,
      collected: acc.collected + row.collected,
      balance_due: acc.balance_due + row.balance_due,
    }),
    { contracts: 0, receivable: 0, collected: 0, balance_due: 0 }
  );

  const contractTotals = (contracts || []).reduce(
    (acc, contract) => ({
      monthly_deduction: acc.monthly_deduction + contract.monthly_deduction,
      outstanding: acc.outstanding + contract.outstanding,
      collected: acc.collected + contract.collected,
      balance_due: acc.balance_due + contract.balance_due,
    }),
    { monthly_deduction: 0, outstanding: 0, collected: 0, balance_due: 0 }
  );

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="text-lg">
            {selectedCostCenter ? `${selectedCostCenter} — Customers` : `Cost Centers — ${region}`}
          </CardTitle>
          <p className="text-sm text-text-secondary mt-0.5">
            {selectedCostCenter
              ? `Ranked by ${active.label.toLowerCase()}. Outstanding is all-time; collected and balance due follow the filters.`
              : `Ranked by ${active.label.toLowerCase()}. Click a cost center to see the customers behind it.`}
          </p>
          <div className="mt-3 flex items-center gap-2">
            <span className="text-xs font-medium text-text-secondary">Show by</span>
            <MetricSwitch metric={metric} onChange={onMetricChange} />
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1.5 rounded-md text-text-secondary hover:bg-neutral-light hover:text-text-primary"
          aria-label="Close cost center breakdown"
          title="Close"
        >
          <X className="h-4 w-4" />
        </button>
      </CardHeader>

      <CardContent>
        {selectedCostCenter ? (
          <>
            <div className="flex items-center justify-between gap-3 mb-4">
              <button
                type="button"
                onClick={onBack}
                className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:text-primary-dark"
              >
                <ArrowLeft className="h-4 w-4" />
                All cost centers in {region}
              </button>
              {sortedContracts && sortedContracts.length > 0 && (
                <span className="text-xs text-text-secondary">
                  {sortedContracts.length} contract{sortedContracts.length === 1 ? "" : "s"}
                </span>
              )}
            </div>

            {contractsLoading ? (
              <div className="space-y-3">
                {[1, 2, 3, 4, 5].map((i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : contractsError ? (
              <p className="text-critical text-sm">{contractsError}</p>
            ) : !sortedContracts || sortedContracts.length === 0 ? (
              <p className="text-text-secondary text-sm">
                No contracts recorded under this cost center for the selected filters.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Customer</TableHead>
                      <TableHead>Contract</TableHead>
                      <TableHead>Item</TableHead>
                      <TableHead className="text-right">EMI / Month</TableHead>
                      <TableHead
                        className="text-right"
                        title="Remaining EMI months based on outstanding ÷ monthly EMI"
                      >
                        EMI Left
                      </TableHead>
                      <TableHead
                        className={cn("text-right", metric === "receivable" && [active.header, active.tint])}
                        title="All-time outstanding: Sales + GST − received"
                      >
                        Receivable
                      </TableHead>
                      <TableHead className={cn("text-right", metric === "collected" && [active.header, active.tint])}>
                        Collected
                      </TableHead>
                      <TableHead className={cn("text-right", metric === "balance_due" && [active.header, active.tint])}>
                        Balance Due
                      </TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sortedContracts.map((contract) => {
                      const contact = [
                        contract.cid ? `CID: ${contract.cid}` : "",
                        contract.mobile ? `Mobile: ${contract.mobile}` : "",
                      ]
                        .filter(Boolean)
                        .join(" · ");
                      const meta = [
                        contract.payment_type,
                        contract.emi_months ? `${contract.emi_months} months` : "",
                        contract.ministry_agency,
                      ]
                        .filter(Boolean)
                        .join(" · ");

                      return (
                        <TableRow key={contract.id}>
                          <TableCell>
                            <div className="font-medium text-text-primary">
                              {contract.customer || "—"}
                            </div>
                            {contact && (
                              <div className="text-xs text-text-secondary">{contact}</div>
                            )}
                          </TableCell>
                          <TableCell>
                            <div className="font-mono text-xs text-text-primary">
                              {contract.reference}
                            </div>
                            <div className="text-xs text-text-secondary">
                              {contract.start_date ? formatDate(contract.start_date) : "—"}
                              {" → "}
                              {contract.end_date ? formatDate(contract.end_date) : "—"}
                            </div>
                          </TableCell>
                          <TableCell className="max-w-[240px]">
                            <div className="truncate text-text-primary" title={contract.item || contract.brand}>
                              {contract.item || contract.brand || "—"}
                            </div>
                            {meta && (
                              <div className="truncate text-xs text-text-secondary" title={meta}>
                                {meta}
                              </div>
                            )}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            Nu. {formatNumber(contract.monthly_deduction)}
                          </TableCell>
                          <TableCell className="text-right">
                            {contract.months_left === null ? (
                              <span className="text-text-secondary">—</span>
                            ) : (
                              <span
                                className={cn(
                                  "font-medium tabular-nums",
                                  contract.months_left === 0
                                    ? "text-success"
                                    : contract.months_left <= 2
                                      ? "text-warning-dark"
                                      : "text-text-primary"
                                )}
                              >
                                {contract.months_left}{" "}
                                {contract.emi_months ? (
                                  <span className="ml-1 text-xs font-normal text-text-secondary">
                                    of {contract.emi_months}
                                  </span>
                                ) : null}
                              </span>
                            )}
                          </TableCell>
                          <TableCell
                            className={cn(
                              "text-right tabular-nums",
                              metric === "receivable" && [active.cell, active.tint]
                            )}
                          >
                            Nu. {formatNumber(contract.outstanding)}
                          </TableCell>
                          <TableCell
                            className={cn(
                              "text-right tabular-nums text-success",
                              metric === "collected" && ["font-semibold", active.tint]
                            )}
                          >
                            Nu. {formatNumber(contract.collected)}
                          </TableCell>
                          <TableCell
                            className={cn(
                              "text-right tabular-nums text-critical",
                              metric === "balance_due" && ["font-semibold", active.tint]
                            )}
                          >
                            Nu. {formatNumber(contract.balance_due)}
                          </TableCell>
                          <TableCell>
                            <ContractStatusBadge status={contract.status} />
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                  <TableFooter>
                    <TableRow>
                      <TableCell colSpan={3}>
                        Total — {sortedContracts.length} contract{sortedContracts.length === 1 ? "" : "s"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        Nu. {formatNumber(contractTotals.monthly_deduction)}
                      </TableCell>
                      <TableCell className="text-right text-text-secondary">—</TableCell>
                      <TableCell className="text-right tabular-nums">
                        Nu. {formatNumber(contractTotals.outstanding)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        Nu. {formatNumber(contractTotals.collected)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        Nu. {formatNumber(contractTotals.balance_due)}
                      </TableCell>
                      <TableCell />
                    </TableRow>
                  </TableFooter>
                </Table>
              </div>
            )}
          </>
        ) : loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : error ? (
          <p className="text-critical text-sm">{error}</p>
        ) : !sortedRows || sortedRows.length === 0 ? (
          <p className="text-text-secondary text-sm">No cost centers recorded for this region.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Cost Center</TableHead>
                <TableHead className="text-right">Contracts</TableHead>
                <TableHead className={cn("text-right", metric === "receivable" && [active.header, active.tint])}>
                  Receivable
                </TableHead>
                <TableHead className={cn("text-right", metric === "collected" && [active.header, active.tint])}>
                  Collected
                </TableHead>
                <TableHead className={cn("text-right", metric === "balance_due" && [active.header, active.tint])}>
                  Balance Due
                </TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedRows.map((row) => (
                <TableRow
                  key={row.cost_center}
                  className="cursor-pointer hover:bg-neutral-light/60"
                  onClick={() => onSelectCostCenter(row.cost_center)}
                >
                  <TableCell className="font-medium text-text-primary">
                    {row.cost_center}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{row.contracts}</TableCell>
                  <TableCell className={cn("text-right tabular-nums", metric === "receivable" && [active.cell, active.tint])}>
                    <div className="flex flex-col items-end gap-1">
                      <span>Nu. {formatNumber(row.receivable)}</span>
                      {metric === "receivable" && (
                        <MetricBar value={row.receivable} max={maxMetric} className={active.bar} />
                      )}
                    </div>
                  </TableCell>
                  <TableCell className={cn("text-right tabular-nums text-success", metric === "collected" && ["font-semibold", active.tint])}>
                    <div className="flex flex-col items-end gap-1">
                      <span>Nu. {formatNumber(row.collected)}</span>
                      {metric === "collected" && (
                        <MetricBar value={row.collected} max={maxMetric} className={active.bar} />
                      )}
                    </div>
                  </TableCell>
                  <TableCell className={cn("text-right tabular-nums text-critical", metric === "balance_due" && ["font-semibold", active.tint])}>
                    <div className="flex flex-col items-end gap-1">
                      <span>Nu. {formatNumber(row.balance_due)}</span>
                      {metric === "balance_due" && (
                        <MetricBar value={row.balance_due} max={maxMetric} className={active.bar} />
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <ChevronRight className="ml-auto h-4 w-4 text-text-secondary" />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell>Total</TableCell>
                <TableCell className="text-right tabular-nums">{totals.contracts}</TableCell>
                <TableCell className={cn("text-right tabular-nums", metric === "receivable" && [active.cell, active.tint])}>
                  Nu. {formatNumber(totals.receivable)}
                </TableCell>
                <TableCell className={cn("text-right tabular-nums", metric === "collected" && [active.cell, active.tint])}>
                  Nu. {formatNumber(totals.collected)}
                </TableCell>
                <TableCell className={cn("text-right tabular-nums", metric === "balance_due" && [active.cell, active.tint])}>
                  Nu. {formatNumber(totals.balance_due)}
                </TableCell>
                <TableCell />
              </TableRow>
            </TableFooter>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

function ContractStatusBadge({ status }: { status: string }) {
  const normalized = (status || "").toLowerCase();
  const variant =
    normalized === "active" || normalized === "reopened"
      ? "success"
      : normalized === "missing_review"
        ? "warning"
        : normalized === "closed"
          ? "neutral"
          : "neutral";

  return (
    <Badge variant={variant}>
      {normalized ? normalized.replace(/_/g, " ") : "unknown"}
    </Badge>
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

      <ChartSkeleton className="h-[420px]" />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-7 space-y-6">
          <ChartSkeleton />
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

function ChartSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("card p-6 h-[350px]", className)}>
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