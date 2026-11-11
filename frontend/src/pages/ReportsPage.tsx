"use client";

import * as React from "react";
import { BarChart2, CalendarClock, Download, FileText, MapPin, Search, Table as TableIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  contractsApi,
  reportsApi,
  type ContractFacets,
  type ReportByBrandItem,
  type ReportByRegionItem,
  type ReportDueItem,
  type ReportOverdueItem,
} from "@/lib/api";
import { cn, formatDate, formatMonthYear, formatNumber, getStatusBadgeVariant } from "@/lib/utils";

type TabKey = "overdue" | "by-region" | "by-brand" | "dues";

const TABS: Array<{ key: TabKey; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { key: "overdue", label: "Overdue", icon: CalendarClock },
  { key: "by-region", label: "By Region & Cost Center", icon: MapPin },
  { key: "by-brand", label: "By Brand", icon: TableIcon },
  { key: "dues", label: "Dues by Installment", icon: TableIcon },
];

const SELECT_CLASS =
  "flex h-9 w-full rounded-button border border-input bg-background px-3 py-1.5 text-sm text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";

function csvCell(value: unknown): string {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

export function ReportsPage() {
  const [tab, setTab] = React.useState<TabKey>("overdue");
  const [facets, setFacets] = React.useState<ContractFacets | null>(null);
  const [region, setRegion] = React.useState("");
  const [costCenter, setCostCenter] = React.useState("");
  const [channel, setChannel] = React.useState("");
  const [brand, setBrand] = React.useState("");
  const [state, setState] = React.useState("");
  const [fromMonth, setFromMonth] = React.useState("");
  const [toMonth, setToMonth] = React.useState("");
  const [overdueSearch, setOverdueSearch] = React.useState("");
  const [duesSearch, setDuesSearch] = React.useState("");

  const [loading, setLoading] = React.useState(true);
  const [overdueItems, setOverdueItems] = React.useState<ReportOverdueItem[]>([]);
  const [overdueSum, setOverdueSum] = React.useState(0);
  const [regionItems, setRegionItems] = React.useState<ReportByRegionItem[]>([]);
  const [brandItems, setBrandItems] = React.useState<ReportByBrandItem[]>([]);
  const [duesItems, setDuesItems] = React.useState<ReportDueItem[]>([]);
  const [duesDue, setDuesDue] = React.useState(0);
  const [duesBalance, setDuesBalance] = React.useState(0);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    contractsApi.facets().then(setFacets).catch(() => {});
  }, []);

  const filters = React.useMemo(
    () => ({
      region: region || undefined,
      cost_center: costCenter || undefined,
      channel: channel || undefined,
      brand: brand || undefined,
      state: state || undefined,
      from_month: tab === "dues" && fromMonth ? fromMonth : undefined,
      to_month: tab === "dues" && toMonth ? toMonth : undefined,
    }),
    [region, costCenter, channel, brand, state, fromMonth, toMonth, tab]
  );

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        if (tab === "overdue") {
          const res = await reportsApi.overdue({ ...filters, limit: 10000 });
          if (!cancelled) {
            setOverdueItems(res.items);
            setOverdueSum(res.total_overdue);
          }
        } else if (tab === "by-region") {
          const res = await reportsApi.byRegion(filters);
          if (!cancelled) setRegionItems(res.items);
        } else if (tab === "by-brand") {
          const res = await reportsApi.byBrand(filters);
          if (!cancelled) setBrandItems(res.items);
        } else if (tab === "dues") {
          const res = await reportsApi.dues({ ...filters, limit: 10000 });
          if (!cancelled) {
            setDuesItems(res.items);
            setDuesDue(res.total_due);
            setDuesBalance(res.total_balance);
          }
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load report");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [tab, filters]);

  const costCenterOptions = React.useMemo(() => {
    const all = facets?.cost_centers ?? [];
    if (!region) return all;
    return all.filter((entry) => entry.region === region);
  }, [facets, region]);

  const filteredOverdue = React.useMemo(() => {
    if (!overdueSearch.trim()) return overdueItems;
    const q = overdueSearch.toLowerCase();
    return overdueItems.filter((item) =>
      [item.reference, item.customer, item.cid, item.mobile, item.region, item.cost_center]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [overdueItems, overdueSearch]);

  const filteredDues = React.useMemo(() => {
    if (!duesSearch.trim()) return duesItems;
    const q = duesSearch.toLowerCase();
    return duesItems.filter((item) =>
      [item.reference, item.customer, item.region, item.cost_center]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [duesItems, duesSearch]);

  const exportOverdue = () => {
    const headers = ["Reference", "Customer", "CID", "Mobile", "Region", "Cost Center", "Brand", "Payment Type", "EMI/Month", "EMI Months", "EMI Left", "Outstanding", "Balance Due", "Overdue Amount", "Status", "Start", "End"];
    const rows = filteredOverdue.map((i) => [i.reference, i.customer, i.cid, i.mobile, i.region, i.cost_center, i.brand, i.payment_type, i.monthly_deduction, i.emi_months ?? "", i.months_left ?? "", i.outstanding, i.balance_due, i.overdue_amount, i.status, i.start_date ?? "", i.end_date ?? ""]);
    const csv = [headers, ...rows].map((r) => r.map(csvCell).join(",")).join("\n");
    downloadCsv(csv, `overdue-report-${new Date().toISOString().slice(0, 10)}.csv`);
  };

  const exportByRegion = () => {
    const headers = ["Region", "Cost Center", "Contracts", "Monthly EMI", "Outstanding", "Collected", "Balance Due"];
    const rows = regionItems.map((i) => [i.region, i.cost_center, i.contracts, i.monthly_deduction, i.outstanding, i.collected, i.balance_due]);
    const csv = [headers, ...rows].map((r) => r.map(csvCell).join(",")).join("\n");
    downloadCsv(csv, `by-region-report-${new Date().toISOString().slice(0, 10)}.csv`);
  };

  const exportByBrand = () => {
    const headers = ["Brand", "Contracts", "Monthly EMI", "Outstanding", "Collected", "Balance Due"];
    const rows = brandItems.map((i) => [i.brand, i.contracts, i.monthly_deduction, i.outstanding, i.collected, i.balance_due]);
    const csv = [headers, ...rows].map((r) => r.map(csvCell).join(",")).join("\n");
    downloadCsv(csv, `by-brand-report-${new Date().toISOString().slice(0, 10)}.csv`);
  };

  const exportDues = () => {
    const headers = ["Due Month", "Reference", "Customer", "Region", "Cost Center", "Brand", "Payment Type", "Due", "Received", "Balance", "Installment Status", "Contract Status"];
    const rows = filteredDues.map((i) => [i.due_month ?? "", i.reference, i.customer, i.region, i.cost_center, i.brand, i.payment_type, i.due_amount, i.received_amount, i.balance, i.status, i.contract_status]);
    const csv = [headers, ...rows].map((r) => r.map(csvCell).join(",")).join("\n");
    downloadCsv(csv, `dues-report-${new Date().toISOString().slice(0, 10)}.csv`);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Reports</h1>
          <p className="text-sm text-text-secondary mt-1">Review overdue contracts, balances by region/cost center, and installment dues.</p>
        </div>
        <div className="flex items-center gap-2">
          {tab === "overdue" && <Button variant="outline" size="sm" className="gap-2" onClick={exportOverdue} disabled={loading || filteredOverdue.length === 0}><Download className="h-4 w-4" />Export CSV</Button>}
          {tab === "by-region" && <Button variant="outline" size="sm" className="gap-2" onClick={exportByRegion} disabled={loading || regionItems.length === 0}><Download className="h-4 w-4" />Export CSV</Button>}
          {tab === "by-brand" && <Button variant="outline" size="sm" className="gap-2" onClick={exportByBrand} disabled={loading || brandItems.length === 0}><Download className="h-4 w-4" />Export CSV</Button>}
          {tab === "dues" && <Button variant="outline" size="sm" className="gap-2" onClick={exportDues} disabled={loading || filteredDues.length === 0}><Download className="h-4 w-4" />Export CSV</Button>}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.key;
          return (
            <button key={t.key} type="button" onClick={() => setTab(t.key)} className={cn("flex items-center gap-2 rounded-full px-3 py-1.5 text-sm transition-colors", active ? "bg-primary text-primary-foreground" : "bg-card border border-border text-text-secondary hover:text-text-primary")}>
              <Icon className="h-4 w-4" />
              {t.label}
            </button>
          );
        })}
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base"><BarChart2 className="h-4 w-4 text-text-secondary" />Filters</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <FilterSelect label="Region" value={region} onChange={(v) => { setRegion(v); setCostCenter(""); }} options={["", ...(facets?.regions ?? [])]} />
          <FilterSelect label="Cost center" value={costCenter} onChange={setCostCenter} options={["", ...costCenterOptions.map((e) => e.name)]} display={(v) => v || "All cost centers"} />
          <FilterSelect label="Channel" value={channel} onChange={setChannel} options={["", "external", "internal"]} display={(v) => v ? v.charAt(0).toUpperCase() + v.slice(1) : "All channels"} />
          <FilterSelect label="Brand" value={brand} onChange={setBrand} options={["", ...(facets?.brands ?? [])]} />
          <FilterSelect label="Status" value={state} onChange={setState} options={["", "active", "missing_review", "closed", "reopened"]} display={(v) => v ? v.replace("_", " ").replace(/\b\w/g, c => c.toUpperCase()) : "All statuses"} />
          {tab === "dues" && <>
            <input type="month" value={fromMonth} onChange={(e) => setFromMonth(e.target.value)} className={SELECT_CLASS} />
            <input type="month" value={toMonth} onChange={(e) => setToMonth(e.target.value)} className={SELECT_CLASS} />
          </>}
        </CardContent>
      </Card>

      {tab === "overdue" && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-3">
            <div>
              <CardTitle className="text-lg">Overdue contracts</CardTitle>
              <p className="mt-1 text-xs text-text-secondary">{loading ? "Loading..." : `${filteredOverdue.length} contracts · Overdue total Nu. ${formatNumber(overdueSum)}`}</p>
            </div>
            <div className="relative w-full max-w-xs">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-text-secondary" />
              <Input value={overdueSearch} onChange={(e) => setOverdueSearch(e.target.value)} placeholder="Search contracts" className="h-9 pl-8" />
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {loading ? <SkeletonRows /> : error ? <ErrorState error={error} /> : filteredOverdue.length === 0 ? <EmptyState /> : <OverdueTable items={filteredOverdue} />}
          </CardContent>
        </Card>
      )}

      {tab === "by-region" && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Summary by Region & Cost Center</CardTitle>
            <p className="mt-1 text-xs text-text-secondary">All-time outstanding, collected, and balance due grouped by region and cost center.</p>
          </CardHeader>
          <CardContent className="p-0">
            {loading ? <SkeletonRows /> : error ? <ErrorState error={error} /> : regionItems.length === 0 ? <EmptyState /> : <RegionTable items={regionItems} />}
          </CardContent>
        </Card>
      )}

      {tab === "by-brand" && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Summary by Brand</CardTitle>
            <p className="mt-1 text-xs text-text-secondary">Contracts, EMI, outstanding, collected, and balance due grouped by brand — shows which brand is performing on income.</p>
          </CardHeader>
          <CardContent className="p-0">
            {loading ? <SkeletonRows /> : error ? <ErrorState error={error} /> : brandItems.length === 0 ? <EmptyState /> : <BrandTable items={brandItems} />}
          </CardContent>
        </Card>
      )}

      {tab === "dues" && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-3">
            <div>
              <CardTitle className="text-lg">Installment dues</CardTitle>
              <p className="mt-1 text-xs text-text-secondary">{loading ? "Loading..." : `${filteredDues.length} rows · Due Nu. ${formatNumber(duesDue)} · Balance Nu. ${formatNumber(duesBalance)}`}</p>
            </div>
            <div className="relative w-full max-w-xs">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-text-secondary" />
              <Input value={duesSearch} onChange={(e) => setDuesSearch(e.target.value)} placeholder="Search reference/customer" className="h-9 pl-8" />
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {loading ? <SkeletonRows /> : error ? <ErrorState error={error} /> : filteredDues.length === 0 ? <EmptyState /> : <DuesTable items={filteredDues} />}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function FilterSelect({ label, value, onChange, options, display }: { label: string; value: string; onChange: (v: string) => void; options: string[]; display?: (v: string) => string }) {
  return (
    <label className="space-y-1">
      <span className="text-xs font-medium text-text-secondary">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className={SELECT_CLASS}>
        {options.map((opt) => (
          <option key={opt || "__all__"} value={opt}>{display ? display(opt) : opt || `All ${label.toLowerCase()}`}</option>
        ))}
      </select>
    </label>
  );
}

function SkeletonRows() {
  return <div className="space-y-2 p-6">{[1,2,3,4,5].map(i => <div key={i} className="h-10 rounded bg-neutral-light/70" />)}</div>;
}

function ErrorState({ error }: { error: string }) {
  return <div className="p-8 text-center text-sm text-critical">{error}</div>;
}

function EmptyState() {
  return <div className="p-10 text-center"><FileText className="mx-auto h-8 w-8 text-text-secondary" /><p className="mt-2 text-sm text-text-secondary">No data for the selected filters.</p></div>;
}

function downloadCsv(content: string, filename: string) {
  const blob = new Blob(["\uFEFF" + content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function OverdueTable({ items }: { items: ReportOverdueItem[] }) {
  return (
    <div className="overflow-x-auto">
      <Table className="text-sm [&_td]:px-3 [&_th]:px-3">
        <TableHeader>
          <TableRow>
            <TableHead>Contract</TableHead>
            <TableHead>Customer</TableHead>
            <TableHead>Region / CC</TableHead>
            <TableHead>Brand / Type</TableHead>
            <TableHead className="text-right">EMI / Month</TableHead>
            <TableHead className="text-right">EMI Left</TableHead>
            <TableHead className="text-right">Outstanding</TableHead>
            <TableHead className="text-right">Balance Due</TableHead>
            <TableHead className="text-right">Overdue</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.id}>
              <TableCell><div className="font-mono text-xs">{item.reference}</div><div className="text-xs text-text-secondary">{item.start_date ? formatDate(item.start_date) : ""}{item.end_date ? ` → ${formatDate(item.end_date)}` : ""}</div></TableCell>
              <TableCell><div className="truncate max-w-[220px]" title={item.customer}>{item.customer || "—"}</div><div className="text-xs text-text-secondary truncate max-w-[220px]" title={[item.cid, item.mobile].filter(Boolean).join(" · ")}>{[item.cid, item.mobile].filter(Boolean).join(" · ") || ""}</div></TableCell>
              <TableCell><div>{item.region || "—"}</div><div className="text-xs text-text-secondary">{item.cost_center || "—"}</div></TableCell>
              <TableCell><div className="truncate max-w-[150px]" title={item.brand}>{item.brand || "—"}</div><div className="text-xs text-text-secondary truncate max-w-[150px]" title={item.payment_type}>{item.payment_type || ""}</div></TableCell>
              <TableCell className="text-right tabular-nums">Nu. {formatNumber(item.monthly_deduction)}</TableCell>
              <TableCell className="text-right">{item.months_left === null ? "—" : <span className={cn("font-medium", item.months_left === 0 ? "text-success" : item.months_left <= 2 ? "text-warning-dark" : "text-text-primary")}>{item.months_left}{item.emi_months ? <span className="ml-1 text-xs font-normal text-text-secondary">of {item.emi_months}</span> : null}</span>}</TableCell>
              <TableCell className="text-right tabular-nums">Nu. {formatNumber(item.outstanding)}</TableCell>
              <TableCell className="text-right tabular-nums">Nu. {formatNumber(item.balance_due)}</TableCell>
              <TableCell className="text-right tabular-nums text-critical">Nu. {formatNumber(item.overdue_amount)}</TableCell>
              <TableCell><Badge variant={getStatusBadgeVariant(item.status)}>{item.status.replace("_", " ")}</Badge></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function RegionTable({ items }: { items: ReportByRegionItem[] }) {
  const byRegion = React.useMemo(() => {
    const map = new Map<string, ReportByRegionItem[]>();
    for (const item of items) {
      const key = item.region || "Unassigned";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(item);
    }
    return Array.from(map.entries());
  }, [items]);
  return (
    <div className="overflow-x-auto">
      <Table className="text-sm [&_td]:px-3 [&_th]:px-3">
        <TableHeader>
          <TableRow>
            <TableHead>Region / Cost Center</TableHead>
            <TableHead className="text-right">Contracts</TableHead>
            <TableHead className="text-right">Monthly EMI</TableHead>
            <TableHead className="text-right">Outstanding</TableHead>
            <TableHead className="text-right">Collected</TableHead>
            <TableHead className="text-right">Balance Due</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {byRegion.map(([regionName, rows]) => (
            <React.Fragment key={regionName}>
              <TableRow className="bg-neutral-light/40">
                <TableCell colSpan={6} className="font-medium">{regionName}</TableCell>
              </TableRow>
              {rows.map((row, idx) => (
                <TableRow key={`${row.region}-${row.cost_center}-${idx}`}>
                  <TableCell className="pl-6">{row.cost_center || "Unassigned"}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.contracts}</TableCell>
                  <TableCell className="text-right tabular-nums">Nu. {formatNumber(row.monthly_deduction)}</TableCell>
                  <TableCell className="text-right tabular-nums">Nu. {formatNumber(row.outstanding)}</TableCell>
                  <TableCell className="text-right tabular-nums text-success">Nu. {formatNumber(row.collected)}</TableCell>
                  <TableCell className="text-right tabular-nums text-critical">Nu. {formatNumber(row.balance_due)}</TableCell>
                </TableRow>
              ))}
            </React.Fragment>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function BrandTable({ items }: { items: ReportByBrandItem[] }) {
  return (
    <div className="overflow-x-auto">
      <Table className="text-sm [&_td]:px-3 [&_th]:px-3">
        <TableHeader>
          <TableRow>
            <TableHead>Brand</TableHead>
            <TableHead className="text-right">Contracts</TableHead>
            <TableHead className="text-right">Monthly EMI</TableHead>
            <TableHead className="text-right">Outstanding</TableHead>
            <TableHead className="text-right">Collected</TableHead>
            <TableHead className="text-right">Balance Due</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.brand}>
              <TableCell className="font-medium text-text-primary">{item.brand || "Unassigned"}</TableCell>
              <TableCell className="text-right tabular-nums">{item.contracts}</TableCell>
              <TableCell className="text-right tabular-nums">Nu. {formatNumber(item.monthly_deduction)}</TableCell>
              <TableCell className="text-right tabular-nums">Nu. {formatNumber(item.outstanding)}</TableCell>
              <TableCell className="text-right tabular-nums text-success">Nu. {formatNumber(item.collected)}</TableCell>
              <TableCell className="text-right tabular-nums text-critical">Nu. {formatNumber(item.balance_due)}</TableCell>
            </TableRow>
          ))}
          <TableRow className="bg-neutral-light/40 font-semibold">
            <TableCell>Total</TableCell>
            <TableCell className="text-right tabular-nums">
              {items.reduce((sum, i) => sum + i.contracts, 0)}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              Nu. {formatNumber(items.reduce((sum, i) => sum + i.monthly_deduction, 0))}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              Nu. {formatNumber(items.reduce((sum, i) => sum + i.outstanding, 0))}
            </TableCell>
            <TableCell className="text-right tabular-nums text-success">
              Nu. {formatNumber(items.reduce((sum, i) => sum + i.collected, 0))}
            </TableCell>
            <TableCell className="text-right tabular-nums text-critical">
              Nu. {formatNumber(items.reduce((sum, i) => sum + i.balance_due, 0))}
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  );
}

function DuesTable({ items }: { items: ReportDueItem[] }) {
  return (
    <div className="overflow-x-auto">
      <Table className="text-sm [&_td]:px-3 [&_th]:px-3">
        <TableHeader>
          <TableRow>
            <TableHead>Due Month</TableHead>
            <TableHead>Contract</TableHead>
            <TableHead>Customer</TableHead>
            <TableHead>Region / CC</TableHead>
            <TableHead>Brand / Type</TableHead>
            <TableHead className="text-right">Due</TableHead>
            <TableHead className="text-right">Received</TableHead>
            <TableHead className="text-right">Balance</TableHead>
            <TableHead>Installment</TableHead>
            <TableHead>Contract</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.installment_id}>
              <TableCell className="whitespace-nowrap">{item.due_month ? formatMonthYear(item.due_month) : "—"}</TableCell>
              <TableCell><div className="font-mono text-xs">{item.reference}</div></TableCell>
              <TableCell><div className="truncate max-w-[200px]" title={item.customer}>{item.customer || "—"}</div></TableCell>
              <TableCell><div>{item.region || "—"}</div><div className="text-xs text-text-secondary">{item.cost_center || "—"}</div></TableCell>
              <TableCell><div className="truncate max-w-[150px]" title={item.brand}>{item.brand || "—"}</div><div className="text-xs text-text-secondary truncate max-w-[150px]" title={item.payment_type}>{item.payment_type || ""}</div></TableCell>
              <TableCell className="text-right tabular-nums">Nu. {formatNumber(item.due_amount)}</TableCell>
              <TableCell className="text-right tabular-nums text-success">Nu. {formatNumber(item.received_amount)}</TableCell>
              <TableCell className={cn("text-right tabular-nums", item.balance > 0 ? "text-critical" : "text-text-secondary")}>Nu. {formatNumber(item.balance)}</TableCell>
              <TableCell><Badge variant={getStatusBadgeVariant(item.status)}>{item.status}</Badge></TableCell>
              <TableCell><Badge variant={getStatusBadgeVariant(item.contract_status)}>{item.contract_status.replace("_", " ")}</Badge></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
