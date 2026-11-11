"use client";

import * as React from "react";
import {
  AlertTriangle,
  Archive,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  BadgeCheck,
  CalendarClock,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Download,
  FileText,
  Filter,
  Loader2,
  RotateCcw,
  Search,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
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
  type ContractFacets,
  type ContractInstallment,
  type ContractListItem,
  type ContractListResponse,
} from "@/lib/api";
import { cn, formatDate, formatMonthYear, formatNumber, getStatusBadgeVariant } from "@/lib/utils";

const PAGE_SIZE = 25;

type QuickView = "all" | "active" | "review" | "overdue" | "ending" | "paid" | "closed";

const QUICK_VIEWS: Array<{
  key: QuickView;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  { key: "all", label: "All contracts", icon: FileText },
  { key: "active", label: "Active", icon: CheckCircle2 },
  { key: "review", label: "Needs review", icon: AlertTriangle },
  { key: "overdue", label: "Has balance due", icon: CalendarClock },
  { key: "ending", label: "Ending soon", icon: Clock },
  { key: "paid", label: "Fully paid", icon: BadgeCheck },
  { key: "closed", label: "Closed", icon: Archive },
];

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "active", label: "Active" },
  { value: "missing_review", label: "Needs review" },
  { value: "closed", label: "Closed" },
  { value: "reopened", label: "Reopened" },
];

const EMI_LEFT_OPTIONS = [
  { value: "", label: "Any EMI left" },
  { value: "zero", label: "0 — fully paid" },
  { value: "1-2", label: "1–2 months" },
  { value: "3-6", label: "3–6 months" },
  { value: "7+", label: "7+ months" },
];

const ENDING_OPTIONS = [
  { value: "", label: "Any end date" },
  { value: "this_month", label: "Ending this month" },
  { value: "next_3_months", label: "Ending in 3 months" },
  { value: "this_fy", label: "Ending this FY" },
];

const SELECT_CLASS =
  "flex h-10 w-full rounded-button border border-input bg-background px-3 py-2 text-sm text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50";

function currentQuickView({
  state,
  overdue,
  ending,
  emiLeft,
}: {
  state: string;
  overdue: boolean;
  ending: string;
  emiLeft: string;
}): QuickView {
  if (overdue) return "overdue";
  if (emiLeft === "zero") return "paid";
  if (ending === "next_3_months") return "ending";
  if (state === "active") return "active";
  if (state === "missing_review") return "review";
  if (state === "closed") return "closed";
  return "all";
}

export function ContractsPage() {
  const [searchInput, setSearchInput] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [state, setState] = React.useState("");
  const [channel, setChannel] = React.useState("");
  const [region, setRegion] = React.useState("");
  const [costCenter, setCostCenter] = React.useState("");
  const [brand, setBrand] = React.useState("");
  const [emiLeft, setEmiLeft] = React.useState("");
  const [ending, setEnding] = React.useState("");
  const [overdue, setOverdue] = React.useState(false);
  const [cycleEndedDue, setCycleEndedDue] = React.useState(false);
  const [cycleEndedPaid, setCycleEndedPaid] = React.useState(false);
  const [sort, setSort] = React.useState("outstanding");
  const [order, setOrder] = React.useState<"asc" | "desc">("desc");
  const [page, setPage] = React.useState(0);
  const [refreshKey, setRefreshKey] = React.useState(0);

  const [data, setData] = React.useState<ContractListResponse | null>(null);
  const [facets, setFacets] = React.useState<ContractFacets | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [exporting, setExporting] = React.useState(false);
  const [exportError, setExportError] = React.useState<string | null>(null);

  const [selectedId, setSelectedId] = React.useState<number | null>(null);
  const [detail, setDetail] = React.useState<ContractListItem | null>(null);
  const [installments, setInstallments] = React.useState<ContractInstallment[] | null>(null);
  const [detailLoading, setDetailLoading] = React.useState(false);
  const [detailError, setDetailError] = React.useState<string | null>(null);
  const detailRequestRef = React.useRef(0);

  React.useEffect(() => {
    contractsApi
      .facets()
      .then(setFacets)
      .catch(() => {
        // Filters still work without facet options.
      });
  }, []);

  React.useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const filters = React.useMemo(
    () => ({
      search: search || undefined,
      state: state || undefined,
      channel: channel || undefined,
      region: region || undefined,
      cost_center: costCenter || undefined,
      brand: brand || undefined,
      emi_left: emiLeft || undefined,
      ending: ending || undefined,
      overdue: overdue || undefined,
      cycle_ended_due: cycleEndedDue || undefined,
      cycle_ended_paid: cycleEndedPaid || undefined,
      sort,
      order,
    }),
    [search, state, channel, region, costCenter, brand, emiLeft, ending, overdue, cycleEndedDue, cycleEndedPaid, sort, order]
  );

  React.useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await contractsApi.list({
          ...filters,
          skip: page * PAGE_SIZE,
          limit: PAGE_SIZE,
        });
        if (!cancelled) {
          setData(result);
          const maxPage = Math.max(0, Math.ceil(result.total / PAGE_SIZE) - 1);
          if (page > maxPage) setPage(maxPage);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load contracts");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [filters, page, refreshKey]);

  const items = data?.items ?? [];
  const summary = data?.summary;
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const startRow = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const endRow = Math.min(total, (page + 1) * PAGE_SIZE);

  const costCenterOptions = React.useMemo(() => {
    const all = facets?.cost_centers ?? [];
    if (!region) return all;
    return all.filter((entry) => entry.region === region);
  }, [facets, region]);

  const applyQuickView = (view: QuickView) => {
    setPage(0);
    setState(
      view === "active"
        ? "active"
        : view === "review"
          ? "missing_review"
          : view === "closed"
            ? "closed"
            : ""
    );
    setOverdue(view === "overdue");
    setEnding(view === "ending" ? "next_3_months" : "");
    setEmiLeft(view === "paid" ? "zero" : "");
  };

  const resetFilters = () => {
    setSearchInput("");
    setSearch("");
    setState("");
    setChannel("");
    setRegion("");
    setCostCenter("");
    setBrand("");
    setEmiLeft("");
    setEnding("");
    setOverdue(false);
    setCycleEndedDue(false);
    setCycleEndedPaid(false);
    setSort("outstanding");
    setOrder("desc");
    setPage(0);
    setExportError(null);
  };

  const handleRegionChange = (value: string) => {
    setRegion(value);
    setCostCenter("");
    setPage(0);
  };

  const toggleSort = (key: string) => {
    if (sort === key) {
      setOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSort(key);
      setOrder("desc");
    }
    setPage(0);
  };

  const openContract = async (id: number) => {
    const requestId = ++detailRequestRef.current;
    setSelectedId(id);
    setDetail(null);
    setInstallments(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const [contract, schedule] = await Promise.all([
        contractsApi.get(id),
        contractsApi.getInstallments(id),
      ]);
      if (detailRequestRef.current !== requestId) return;
      setDetail(contract);
      setInstallments(schedule);
    } catch (err) {
      if (detailRequestRef.current !== requestId) return;
      setDetailError(err instanceof Error ? err.message : "Failed to load contract");
    } finally {
      if (detailRequestRef.current === requestId) setDetailLoading(false);
    }
  };

  const closeDetail = () => {
    detailRequestRef.current += 1;
    setSelectedId(null);
    setDetail(null);
    setInstallments(null);
    setDetailError(null);
    setDetailLoading(false);
  };

  React.useEffect(() => {
    if (selectedId === null) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeDetail();
    };
    window.addEventListener("keydown", handleKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const exportCsv = async () => {
    setExporting(true);
    setExportError(null);
    try {
      const result = await contractsApi.list({
        ...filters,
        skip: 0,
        limit: 10000,
      });
      const headers = [
        "Reference",
        "Customer",
        "CID",
        "Mobile",
        "Item",
        "Brand",
        "Region",
        "Cost Center",
        "Payment Type",
        "EMI Months",
        "EMI Left",
        "Monthly EMI",
        "Sales Amount",
        "GST",
        "Collected",
        "Receivable",
        "Balance Due",
        "Start Date",
        "End Date",
        "Status",
      ];
      const rows = result.items.map((contract) => [
        contract.reference,
        contract.customer,
        contract.cid,
        contract.mobile,
        contract.item,
        contract.brand,
        contract.region,
        contract.cost_center,
        contract.payment_type,
        contract.emi_months ?? "",
        contract.months_left ?? "",
        contract.monthly_deduction,
        contract.sales_amount,
        contract.gst,
        contract.collected,
        contract.outstanding,
        contract.balance_due,
        contract.start_date ?? "",
        contract.end_date ?? "",
        contract.status,
      ]);
      const csv = [headers, ...rows]
        .map((row) => row.map(csvCell).join(","))
        .join("\n");
      const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `contracts-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExporting(false);
    }
  };

  const activeView = currentQuickView({ state, overdue, ending, emiLeft });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-text-primary">Contracts</h1>
        <p className="text-sm text-text-secondary mt-1">
          Review contracts, balances, and installment schedules.
        </p>
      </div>

      <div className="flex flex-col gap-6 lg:flex-row">
        {/* Filter sidebar */}
        <aside className="w-full lg:w-[280px] lg:flex-shrink-0">
          <Card className="lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto">
            <CardHeader className="pb-4">
              <CardTitle className="flex items-center gap-2 text-base">
                <Filter className="h-4 w-4 text-text-secondary" />
                Filters
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-secondary" />
                <Input
                  value={searchInput}
                  onChange={(event) => setSearchInput(event.target.value)}
                  placeholder="Search reference, customer, CID, mobile"
                  className="pl-9 pr-9"
                  aria-label="Search contracts"
                />
                {searchInput && (
                  <button
                    type="button"
                    onClick={() => setSearchInput("")}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-text-secondary hover:bg-neutral-light hover:text-text-primary"
                    aria-label="Clear search"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>

              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-secondary">
                  Quick views
                </p>
                <div className="space-y-1">
                  {QUICK_VIEWS.map((view) => {
                    const Icon = view.icon;
                    const active = activeView === view.key;
                    return (
                      <button
                        key={view.key}
                        type="button"
                        onClick={() => applyQuickView(view.key)}
                        className={cn(
                          "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors",
                          active
                            ? "bg-primary/10 font-medium text-primary"
                            : "text-text-secondary hover:bg-neutral-light hover:text-text-primary"
                        )}
                      >
                        <Icon className="h-4 w-4 flex-shrink-0" />
                        {view.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="space-y-3 border-t border-border pt-4">
                <FilterField label="Status">
                  <select
                    value={state}
                    onChange={(event) => {
                      setState(event.target.value);
                      setPage(0);
                    }}
                    className={SELECT_CLASS}
                  >
                    {STATUS_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </FilterField>

                <FilterField label="Channel">
                  <select
                    value={channel}
                    onChange={(event) => {
                      setChannel(event.target.value);
                      setPage(0);
                    }}
                    className={SELECT_CLASS}
                  >
                    <option value="">All channels</option>
                    <option value="external">External</option>
                    <option value="internal">Internal</option>
                  </select>
                </FilterField>

                <FilterField label="Region">
                  <select
                    value={region}
                    onChange={(event) => handleRegionChange(event.target.value)}
                    className={SELECT_CLASS}
                  >
                    <option value="">All regions</option>
                    {(facets?.regions ?? []).map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                </FilterField>

                <FilterField label="Cost center">
                  <select
                    value={costCenter}
                    onChange={(event) => {
                      setCostCenter(event.target.value);
                      setPage(0);
                    }}
                    className={SELECT_CLASS}
                  >
                    <option value="">All cost centers</option>
                    {costCenterOptions.map((entry) => (
                      <option key={`${entry.region}-${entry.name}`} value={entry.name}>
                        {region ? entry.name : `${entry.name} · ${entry.region}`}
                      </option>
                    ))}
                  </select>
                </FilterField>

                <FilterField label="Brand">
                  <select
                    value={brand}
                    onChange={(event) => {
                      setBrand(event.target.value);
                      setPage(0);
                    }}
                    className={SELECT_CLASS}
                  >
                    <option value="">All brands</option>
                    {(facets?.brands ?? []).map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                </FilterField>

                <FilterField label="EMI left">
                  <select
                    value={emiLeft}
                    onChange={(event) => {
                      setEmiLeft(event.target.value);
                      setPage(0);
                    }}
                    className={SELECT_CLASS}
                  >
                    {EMI_LEFT_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </FilterField>

                <FilterField label="Ending">
                  <select
                    value={ending}
                    onChange={(event) => {
                      setEnding(event.target.value);
                      setPage(0);
                    }}
                    className={SELECT_CLASS}
                  >
                    {ENDING_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
</FilterField>

              <FilterField label="Cycle ended and paid">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={cycleEndedPaid}
                    onChange={(event) => {
                      setCycleEndedPaid(event.target.checked);
                      setPage(0);
                    }}
                    className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                  />
                  <span className="text-sm text-text-secondary">Payment cycle ended and fully paid</span>
                </label>
              </FilterField>

            </div>
              <FilterField label="Cycle ended but due">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={cycleEndedDue}
                    onChange={(event) => {
                      setCycleEndedDue(event.target.checked);
                      setPage(0);
                    }}
                    className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                  />
                  <span className="text-sm text-text-secondary">Payment cycle ended but still due</span>
                </label>
              </FilterField>

              <div className="space-y-2 rounded-lg border border-border bg-neutral-light/40 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
                  Filtered summary
                </p>
                <SummaryRow label="Contracts" value={formatNumber(summary?.contracts ?? 0)} />
                <SummaryRow
                  label="Monthly EMI"
                  value={`Nu. ${formatNumber(summary?.monthly_deduction ?? 0)}`}
                />
                <SummaryRow
                  label="Receivable"
                  value={`Nu. ${formatNumber(summary?.outstanding ?? 0)}`}
                />
                <SummaryRow
                  label="Collected"
                  value={`Nu. ${formatNumber(summary?.collected ?? 0)}`}
                />
                <SummaryRow
                  label="Balance Due"
                  value={`Nu. ${formatNumber(summary?.balance_due ?? 0)}`}
                />
              </div>

              <div className="space-y-2">
                <Button
                  variant="outline"
                  className="w-full justify-start gap-2"
                  onClick={exportCsv}
                  disabled={exporting || total === 0}
                >
                  {exporting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                  Export CSV
                </Button>
                <Button
                  variant="ghost"
                  className="w-full justify-start gap-2"
                  onClick={resetFilters}
                >
                  <RotateCcw className="h-4 w-4" />
                  Clear filters
                </Button>
                {exportError && <p className="text-xs text-critical">{exportError}</p>}
              </div>
            </CardContent>
          </Card>
        </aside>

        {/* Contract list */}
        <div className="min-w-0 flex-1">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-4">
              <div>
                <CardTitle className="text-lg">Contract list</CardTitle>
                <p className="mt-1 text-xs text-text-secondary">
                  {loading ? "Loading contracts…" : `${formatNumber(total)} contract${total === 1 ? "" : "s"}`}
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={exportCsv}
                disabled={exporting || total === 0}
              >
                {exporting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Download className="h-4 w-4" />
                )}
                Export
              </Button>
            </CardHeader>

            <CardContent className="p-0">
              {loading ? (
                <div className="space-y-3 p-6">
                  {[1, 2, 3, 4, 5, 6].map((row) => (
                    <Skeleton key={row} className="h-12 w-full" />
                  ))}
                </div>
              ) : error ? (
                <div className="p-10 text-center">
                  <p className="text-sm text-critical">{error}</p>
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-3"
                    onClick={() => setRefreshKey((key) => key + 1)}
                  >
                    Try again
                  </Button>
                </div>
              ) : items.length === 0 ? (
                <div className="p-12 text-center">
                  <FileText className="mx-auto h-8 w-8 text-text-secondary" />
                  <p className="mt-3 text-sm font-medium text-text-primary">
                    No contracts match these filters
                  </p>
                  <p className="mt-1 text-xs text-text-secondary">
                    Try a different search or clear the filters.
                  </p>
                  <Button variant="outline" size="sm" className="mt-4" onClick={resetFilters}>
                    Clear filters
                  </Button>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <Table className="text-sm [&_td]:px-3 [&_th]:px-3">
                    <TableHeader>
                      <TableRow>
                        <SortableHead
                          label="Customer"
                          sortKey="customer"
                          sort={sort}
                          order={order}
                          onSort={toggleSort}
                        />
                        <SortableHead
                          label="Contract"
                          sortKey="reference"
                          sort={sort}
                          order={order}
                          onSort={toggleSort}
                        />
                        <SortableHead
                          label="EMI / Left"
                          sortKey="emi_left"
                          sort={sort}
                          order={order}
                          onSort={toggleSort}
                          align="right"
                          title="Monthly EMI and remaining months (receivable ÷ monthly EMI, capped at total tenor)"
                        />
                        <SortableHead
                          label="Receivable"
                          sortKey="outstanding"
                          sort={sort}
                          order={order}
                          onSort={toggleSort}
                          align="right"
                          title="All-time outstanding: Sales + GST − collected"
                        />
                        <SortableHead
                          label="Collected"
                          sortKey="collected"
                          sort={sort}
                          order={order}
                          onSort={toggleSort}
                          align="right"
                          title="Total amount received to date"
                        />
                        <SortableHead
                          label="Balance Due"
                          sortKey="balance_due"
                          sort={sort}
                          order={order}
                          onSort={toggleSort}
                          align="right"
                          title="Unpaid amount on scheduled installments to date"
                        />
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {items.map((contract) => {
                        const location = [contract.region, contract.cost_center]
                          .filter(Boolean)
                          .join(" · ");
                        return (
                          <TableRow
                            key={contract.id}
                            className="cursor-pointer hover:bg-neutral-light/60"
                            onClick={() => openContract(contract.id)}
                          >
                            <TableCell className="max-w-[200px]">
                              <div
                                className="truncate font-medium text-text-primary"
                                title={contract.customer || "—"}
                              >
                                {contract.customer || "—"}
                              </div>
                              {location && (
                                <div className="truncate text-xs text-text-secondary" title={location}>
                                  {location}
                                </div>
                              )}
                            </TableCell>
                            <TableCell className="max-w-[180px]">
                              <div className="font-mono text-xs text-text-primary">
                                {contract.reference}
                              </div>
                              <div
                                className="truncate text-xs text-text-secondary"
                                title={[
                                  contract.item || contract.brand,
                                  contract.start_date ? formatDate(contract.start_date) : "",
                                  contract.end_date ? formatDate(contract.end_date) : "",
                                ]
                                  .filter(Boolean)
                                  .join(" · ")}
                              >
                                {contract.item || contract.brand || "—"}
                              </div>
                            </TableCell>
                            <TableCell className="whitespace-nowrap text-right">
                              <div className="tabular-nums">
                                Nu. {formatNumber(contract.monthly_deduction)}
                              </div>
                              <div className="mt-0.5 text-xs">
                                <MonthsLeftBadge
                                  monthsLeft={contract.months_left}
                                  total={contract.emi_months}
                                />
                              </div>
                            </TableCell>
                            <TableCell className="whitespace-nowrap text-right tabular-nums">
                              Nu. {formatNumber(contract.outstanding)}
                            </TableCell>
                            <TableCell className="whitespace-nowrap text-right tabular-nums text-success">
                              Nu. {formatNumber(contract.collected)}
                            </TableCell>
                            <TableCell className="whitespace-nowrap text-right tabular-nums text-critical">
                              Nu. {formatNumber(contract.balance_due)}
                            </TableCell>
                            <TableCell>
                              <div className="flex items-center justify-between gap-2">
                                <StatusBadge status={contract.status} />
                                <ChevronRight className="h-4 w-4 flex-shrink-0 text-text-secondary" />
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>

            {!loading && !error && items.length > 0 && (
              <div className="flex flex-col gap-2 border-t border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs text-text-secondary">
                  Showing {formatNumber(startRow)}–{formatNumber(endRow)} of{" "}
                  {formatNumber(total)}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((value) => Math.max(0, value - 1))}
                    disabled={page === 0}
                    className="gap-1"
                  >
                    <ChevronLeft className="h-4 w-4" />
                    Prev
                  </Button>
                  <span className="text-xs text-text-secondary">
                    Page {page + 1} of {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((value) => value + 1)}
                    disabled={page + 1 >= totalPages}
                    className="gap-1"
                  >
                    Next
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </Card>
        </div>
      </div>

      {selectedId !== null && (
        <ContractDetailDrawer
          contract={detail}
          installments={installments}
          loading={detailLoading}
          error={detailError}
          onClose={closeDetail}
        />
      )}
    </div>
  );
}

function FilterField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium text-text-secondary">{label}</span>
      {children}
    </label>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <span className="text-text-secondary">{label}</span>
      <span className="font-medium tabular-nums text-text-primary">{value}</span>
    </div>
  );
}

function SortableHead({
  label,
  sortKey,
  sort,
  order,
  onSort,
  align = "left",
  title,
}: {
  label: string;
  sortKey: string;
  sort: string;
  order: "asc" | "desc";
  onSort: (key: string) => void;
  align?: "left" | "right";
  title?: string;
}) {
  const active = sort === sortKey;
  return (
    <TableHead className={align === "right" ? "text-right" : undefined}>
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        title={title}
        className={cn(
          "inline-flex items-center gap-1 transition-colors hover:text-text-primary",
          active ? "text-text-primary" : "text-text-secondary"
        )}
      >
        {label}
        {active ? (
          order === "asc" ? (
            <ArrowUp className="h-3 w-3" />
          ) : (
            <ArrowDown className="h-3 w-3" />
          )
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-30" />
        )}
      </button>
    </TableHead>
  );
}

function MonthsLeftBadge({
  monthsLeft,
  total,
}: {
  monthsLeft: number | null;
  total: number | null;
}) {
  if (monthsLeft === null) {
    return <span className="text-text-secondary">—</span>;
  }
  return (
    <span
      className={cn(
        "font-medium tabular-nums",
        monthsLeft === 0
          ? "text-success"
          : monthsLeft <= 2
            ? "text-warning-dark"
            : "text-text-primary"
      )}
      title="Remaining EMI months based on receivable ÷ monthly EMI"
    >
      {monthsLeft}
      {total ? (
        <span className="ml-1 text-xs font-normal text-text-secondary">of {total}</span>
      ) : null}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const normalized = (status || "").toLowerCase();
  return (
    <Badge variant={getStatusBadgeVariant(normalized)}>
      {normalized ? normalized.replace(/_/g, " ") : "unknown"}
    </Badge>
  );
}

function ContractDetailDrawer({
  contract,
  installments,
  loading,
  error,
  onClose,
}: {
  contract: ContractListItem | null;
  installments: ContractInstallment[] | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50">
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Contract details"
        className="absolute right-0 top-0 flex h-full w-full max-w-2xl flex-col border-l border-border bg-card shadow-2xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-4">
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
              Contract details
            </p>
            <h2 className="mt-1 truncate text-lg font-semibold text-text-primary">
              {contract?.customer || "Loading…"}
            </h2>
            {contract && (
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-text-secondary">
                  {contract.reference}
                </span>
                <StatusBadge status={contract.status} />
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-text-secondary hover:bg-neutral-light hover:text-text-primary"
            aria-label="Close contract details"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {loading ? (
            <div className="space-y-4">
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-28 w-full" />
              <Skeleton className="h-64 w-full" />
            </div>
          ) : error ? (
            <p className="text-sm text-critical">{error}</p>
          ) : contract ? (
            <div className="space-y-6">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <DetailMetric label="Receivable" value={`Nu. ${formatNumber(contract.outstanding)}`} />
                <DetailMetric label="Collected" value={`Nu. ${formatNumber(contract.collected)}`} tone="success" />
                <DetailMetric label="Balance Due" value={`Nu. ${formatNumber(contract.balance_due)}`} tone="critical" />
                <DetailMetric label="EMI / Month" value={`Nu. ${formatNumber(contract.monthly_deduction)}`} />
                <DetailMetric
                  label="EMI Left"
                  value={
                    contract.months_left === null
                      ? "—"
                      : `${contract.months_left}${contract.emi_months ? ` of ${contract.emi_months}` : ""}`
                  }
                />
                <DetailMetric label="Scheduled Due" value={`Nu. ${formatNumber(contract.total_due)}`} />
              </div>

              <div className="rounded-lg border border-border">
                <div className="border-b border-border px-4 py-3">
                  <h3 className="text-sm font-semibold text-text-primary">Contract information</h3>
                </div>
                <dl className="grid grid-cols-1 gap-x-6 gap-y-3 p-4 text-sm sm:grid-cols-2">
                  <DetailRow label="Item" value={contract.item || "—"} />
                  <DetailRow label="Brand" value={contract.brand || "—"} />
                  <DetailRow label="Region" value={contract.region || "—"} />
                  <DetailRow label="Cost center" value={contract.cost_center || "—"} />
                  <DetailRow label="Payment type" value={contract.payment_type || "—"} />
                  <DetailRow label="Ministry / Agency" value={contract.ministry_agency || "—"} />
                  <DetailRow label="CID" value={contract.cid || "—"} />
                  <DetailRow label="Mobile" value={contract.mobile || "—"} />
                  <DetailRow
                    label="Start date"
                    value={contract.start_date ? formatDate(contract.start_date) : "—"}
                  />
                  <DetailRow
                    label="End date"
                    value={contract.end_date ? formatDate(contract.end_date) : "—"}
                  />
                  <DetailRow label="Sales amount" value={`Nu. ${formatNumber(contract.sales_amount)}`} />
                  <DetailRow label="GST" value={`Nu. ${formatNumber(contract.gst)}`} />
                </dl>
              </div>

              <div className="rounded-lg border border-border">
                <div className="flex items-center justify-between border-b border-border px-4 py-3">
                  <h3 className="text-sm font-semibold text-text-primary">
                    Installment schedule
                  </h3>
                  <span className="text-xs text-text-secondary">
                    {installments?.length ?? 0} month{(installments?.length ?? 0) === 1 ? "" : "s"}
                  </span>
                </div>
                {!installments || installments.length === 0 ? (
                  <p className="p-4 text-sm text-text-secondary">
                    No installment rows recorded for this contract.
                  </p>
                ) : (
                  <div className="max-h-[320px] overflow-y-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Month</TableHead>
                          <TableHead className="text-right">Due</TableHead>
                          <TableHead className="text-right">Received</TableHead>
                          <TableHead className="text-right">Balance</TableHead>
                          <TableHead>Status</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {installments.map((installment) => (
                          <TableRow key={installment.id}>
                            <TableCell className="whitespace-nowrap text-text-primary">
                              {formatMonthYear(installment.due_month)}
                            </TableCell>
                            <TableCell className="text-right tabular-nums">
                              {formatNumber(installment.due_amount)}
                            </TableCell>
                            <TableCell className="text-right tabular-nums text-success">
                              {formatNumber(installment.received_amount)}
                            </TableCell>
                            <TableCell
                              className={cn(
                                "text-right tabular-nums",
                                installment.balance > 0 ? "text-critical" : "text-text-secondary"
                              )}
                            >
                              {formatNumber(installment.balance)}
                            </TableCell>
                            <TableCell>
                              <StatusBadge status={installment.status} />
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function DetailMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "success" | "critical";
}) {
  return (
    <div className="rounded-lg border border-border bg-neutral-light/30 p-3">
      <p className="text-xs text-text-secondary">{label}</p>
      <p
        className={cn(
          "mt-1 text-sm font-semibold tabular-nums",
          tone === "success"
            ? "text-success"
            : tone === "critical"
              ? "text-critical"
              : "text-text-primary"
        )}
      >
        {value}
      </p>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-text-secondary">{label}</dt>
      <dd className="mt-0.5 truncate text-text-primary" title={value}>
        {value}
      </dd>
    </div>
  );
}

function csvCell(value: unknown): string {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}
