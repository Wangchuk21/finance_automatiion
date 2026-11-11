"use client";

import * as React from "react";
import {
  Send,
  Users,
  Phone,
  PhoneOff,
  AlertTriangle,
  History,
  CheckCircle2,
  XCircle,
  Search,
  RefreshCw,
  MessageSquare,
  Sparkles,
  X,
} from "lucide-react";
import {
  notificationsApi,
  type ReminderCandidate,
  type NotificationTemplate,
  type NotificationHistoryItem,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const AGING_BUCKETS = [
  { label: "All Overdue", value: "all" },
  { label: "0-30 Days", value: "0-30" },
  { label: "31-60 Days", value: "31-60" },
  { label: "61-90 Days", value: "61-90" },
  { label: "91-120 Days", value: "91-120" },
  { label: "120+ Days (Critical)", value: "120+" },
];

export function RemindersPage() {
  const [banner, setBanner] = React.useState<{ title: string; desc?: string; error?: boolean } | null>(null);

  const showBanner = (title: string, desc?: string, error: boolean = false) => {
    setBanner({ title, desc, error });
    setTimeout(() => setBanner(null), 6000);
  };
  const [activeTab, setActiveTab] = React.useState<"candidates" | "history">("candidates");

  // Candidates state
  const [candidates, setCandidates] = React.useState<ReminderCandidate[]>([]);
  const [templates, setTemplates] = React.useState<NotificationTemplate[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [selectedTemplateId, setSelectedTemplateId] = React.useState<number | undefined>(undefined);
  const [selectedContractIds, setSelectedContractIds] = React.useState<Set<number>>(new Set());

  // Filter states
  const [selectedBucket, setSelectedBucket] = React.useState("all");
  const [searchQuery, setSearchQuery] = React.useState("");
  const [regionFilter, setRegionFilter] = React.useState("");
  const [minBalance, setMinBalance] = React.useState<number>(100);

  // Stats
  const [totalEligible, setTotalEligible] = React.useState(0);
  const [withMobileCount, setWithMobileCount] = React.useState(0);
  const [missingMobileCount, setMissingMobileCount] = React.useState(0);
  const [totalBalanceDue, setTotalBalanceDue] = React.useState(0);

  // Dispatch state & confirmation modal
  const [previewCustomer, setPreviewCustomer] = React.useState<ReminderCandidate | null>(null);
  const [confirmModalOpen, setConfirmModalOpen] = React.useState(false);
  const [isSending, setIsSending] = React.useState(false);

  // History state
  const [historyItems, setHistoryItems] = React.useState<NotificationHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = React.useState(false);

  // Fetch candidates
  const loadCandidates = React.useCallback(async () => {
    try {
      setLoading(true);
      const data = await notificationsApi.getReminderCandidates({
        aging_bucket: selectedBucket,
        region: regionFilter || undefined,
        min_balance: minBalance,
        template_id: selectedTemplateId,
      });

      setCandidates(data.candidates);
      setTemplates(data.templates);
      setTotalEligible(data.total_eligible);
      setWithMobileCount(data.with_mobile_count);
      setMissingMobileCount(data.missing_mobile_count);
      setTotalBalanceDue(data.total_balance_due);

      if (!selectedTemplateId && data.templates.length > 0) {
        setSelectedTemplateId(data.templates[0].id);
      }
    } catch (err) {
      showBanner("Failed to load candidates", err instanceof Error ? err.message : "Network error", true);
    } finally {
      setLoading(false);
    }
  }, [selectedBucket, regionFilter, minBalance, selectedTemplateId]);

  // Fetch history
  const loadHistory = React.useCallback(async () => {
    try {
      setHistoryLoading(true);
      const data = await notificationsApi.getHistory({ channel: "sms", limit: 50 });
      setHistoryItems(data.items);
    } catch (err) {
      showBanner("Failed to load notification history", err instanceof Error ? err.message : "Network error", true);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (activeTab === "candidates") {
      loadCandidates();
    } else {
      loadHistory();
    }
  }, [activeTab, loadCandidates, loadHistory]);

  // Filter candidates by client search query
  const filteredCandidates = React.useMemo(() => {
    if (!searchQuery.trim()) return candidates;
    const q = searchQuery.toLowerCase().trim();
    return candidates.filter(
      (c) =>
        c.customer.toLowerCase().includes(q) ||
        c.reference.toLowerCase().includes(q) ||
        (c.mobile && c.mobile.includes(q)) ||
        (c.cid && c.cid.includes(q)) ||
        (c.item && c.item.toLowerCase().includes(q))
    );
  }, [candidates, searchQuery]);

  // Selection handlers
  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      // Select all currently visible candidates with a valid phone number
      const validIds = filteredCandidates
        .filter((c) => Boolean(c.mobile))
        .map((c) => c.contract_id);
      setSelectedContractIds(new Set(validIds));
    } else {
      setSelectedContractIds(new Set());
    }
  };

  const handleToggleRow = (contractId: number) => {
    setSelectedContractIds((prev) => {
      const next = new Set(prev);
      if (next.has(contractId)) {
        next.delete(contractId);
      } else {
        next.add(contractId);
      }
      return next;
    });
  };

  const selectedCount = selectedContractIds.size;
  const selectedTotalBalance = candidates
    .filter((c) => selectedContractIds.has(c.contract_id))
    .reduce((acc, c) => acc + c.balance_due, 0);

  // Dispatch reminder action
  const handleSendReminders = async () => {
    if (selectedCount === 0) return;
    try {
      setIsSending(true);
      const res = await notificationsApi.sendReminders({
        contract_ids: Array.from(selectedContractIds),
        template_id: selectedTemplateId,
      });

      showBanner("SMS Reminders Dispatched", res.message, false);

      setConfirmModalOpen(false);
      setSelectedContractIds(new Set());
      loadCandidates();
    } catch (err) {
      showBanner("Failed to send reminders", err instanceof Error ? err.message : "Error sending SMS", true);
    } finally {
      setIsSending(false);
    }
  };

  const activeTemplate = templates.find((t) => t.id === selectedTemplateId);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">
            Customer Payment Reminders (SMS)
          </h1>
          <p className="text-text-secondary mt-1 text-sm">
            Generate and dispatch automated SMS payment reminders to customers with overdue balances.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant={activeTab === "candidates" ? "default" : "outline"}
            size="sm"
            onClick={() => setActiveTab("candidates")}
            className="gap-2"
          >
            <MessageSquare className="h-4 w-4" />
            <span>Reminders</span>
          </Button>
          <Button
            variant={activeTab === "history" ? "default" : "outline"}
            size="sm"
            onClick={() => setActiveTab("history")}
            className="gap-2"
          >
            <History className="h-4 w-4" />
            <span>Sent Log</span>
          </Button>
        </div>
      </div>

      {banner && (
        <div
          className={cn(
            "p-3 rounded-lg border flex items-center justify-between text-xs transition-all shadow-sm",
            banner.error
              ? "bg-critical/10 text-critical border-critical/30"
              : "bg-success/10 text-success border-success/30"
          )}
        >
          <div className="flex items-center gap-2">
            {banner.error ? <AlertTriangle className="h-4 w-4 shrink-0" /> : <CheckCircle2 className="h-4 w-4 shrink-0" />}
            <div>
              <strong>{banner.title}</strong>
              {banner.desc && <span className="ml-1.5 opacity-90">{banner.desc}</span>}
            </div>
          </div>
          <button onClick={() => setBanner(null)} className="p-1 hover:opacity-70">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {activeTab === "candidates" && (
        <>
          {/* Top KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card>
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <p className="text-xs text-text-secondary font-medium">Overdue Accounts</p>
                  <p className="text-2xl font-bold text-text-primary mt-1 tabular-nums">
                    {totalEligible.toLocaleString()}
                  </p>
                </div>
                <div className="p-2.5 rounded-lg bg-primary/10 text-primary">
                  <Users className="h-5 w-5" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <p className="text-xs text-text-secondary font-medium">Total Balance Overdue</p>
                  <p className="text-2xl font-bold text-critical mt-1 tabular-nums">
                    Nu. {totalBalanceDue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </p>
                </div>
                <div className="p-2.5 rounded-lg bg-critical/10 text-critical">
                  <AlertTriangle className="h-5 w-5" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <p className="text-xs text-text-secondary font-medium">Ready for SMS (Valid Phone)</p>
                  <p className="text-2xl font-bold text-success mt-1 tabular-nums">
                    {withMobileCount.toLocaleString()}
                  </p>
                </div>
                <div className="p-2.5 rounded-lg bg-success/10 text-success">
                  <Phone className="h-5 w-5" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <p className="text-xs text-text-secondary font-medium">Missing Phone Number</p>
                  <p className="text-2xl font-bold text-warning-dark mt-1 tabular-nums">
                    {missingMobileCount.toLocaleString()}
                  </p>
                </div>
                <div className="p-2.5 rounded-lg bg-warning/10 text-warning">
                  <PhoneOff className="h-5 w-5" />
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Main Action Banner */}
          {selectedCount > 0 && (
            <div className="sticky top-20 z-20 bg-primary/10 border border-primary/30 rounded-lg p-3 flex flex-wrap items-center justify-between gap-3 shadow-md backdrop-blur-md">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-primary" />
                <span className="text-sm font-semibold text-text-primary">
                  {selectedCount} customer{selectedCount > 1 ? "s" : ""} selected
                </span>
                <span className="text-xs text-text-secondary">
                  (Total overdue: Nu. {selectedTotalBalance.toLocaleString(undefined, { minimumFractionDigits: 2 })})
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSelectedContractIds(new Set())}
                  className="h-8 text-xs"
                >
                  Clear Selection
                </Button>
                <Button
                  size="sm"
                  onClick={() => setConfirmModalOpen(true)}
                  className="h-8 text-xs gap-1.5 bg-primary text-white hover:bg-primary-dark"
                >
                  <Send className="h-3.5 w-3.5" />
                  <span>Send SMS Reminders ({selectedCount})</span>
                </Button>
              </div>
            </div>
          )}

          {/* Filter Bar */}
          <Card>
            <CardContent className="p-4 space-y-4">
              {/* Aging Buckets Selector */}
              <div>
                <Label className="text-xs text-text-secondary mb-1.5 block">Aging Bucket Filter</Label>
                <div className="flex items-center gap-1.5 flex-wrap">
                  {AGING_BUCKETS.map((b) => (
                    <button
                      key={b.value}
                      type="button"
                      onClick={() => setSelectedBucket(b.value)}
                      className={cn(
                        "px-3 py-1.5 rounded-md text-xs font-medium transition-colors border",
                        selectedBucket === b.value
                          ? "bg-primary text-white border-primary shadow-sm"
                          : "bg-surface border-border text-text-secondary hover:text-text-primary hover:bg-neutral-light/50"
                      )}
                    >
                      {b.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Sub-filters & Search */}
              <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end pt-2 border-t border-border/50">
                <div className="sm:col-span-5">
                  <Label htmlFor="search-input" className="text-xs text-text-secondary mb-1 block">
                    Search Customer / Phone / Reference
                  </Label>
                  <div className="relative">
                    <Search className="h-4 w-4 text-text-secondary absolute left-3 top-2.5" />
                    <Input
                      id="search-input"
                      placeholder="e.g. Karma, 17123456, BT25..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-9 h-9 text-xs"
                    />
                  </div>
                </div>

                <div className="sm:col-span-3">
                  <Label htmlFor="region-filter" className="text-xs text-text-secondary mb-1 block">
                    Region / Cost Center
                  </Label>
                  <Input
                    id="region-filter"
                    placeholder="e.g. Thimphu, Western"
                    value={regionFilter}
                    onChange={(e) => setRegionFilter(e.target.value)}
                    className="h-9 text-xs"
                  />
                </div>

                <div className="sm:col-span-2">
                  <Label htmlFor="min-bal" className="text-xs text-text-secondary mb-1 block">
                    Min Overdue (Nu.)
                  </Label>
                  <Input
                    id="min-bal"
                    type="number"
                    value={minBalance}
                    onChange={(e) => setMinBalance(Number(e.target.value))}
                    className="h-9 text-xs"
                    min="0"
                  />
                </div>

                <div className="sm:col-span-2 flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={loadCandidates}
                    disabled={loading}
                    className="h-9 w-full text-xs gap-1.5"
                  >
                    <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
                    <span>Refresh</span>
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Template & Message Customization Card */}
          <Card>
            <CardHeader className="py-3 px-4 border-b border-border">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <CardTitle className="text-sm font-semibold">SMS Template & Preview</CardTitle>
                  <CardDescription className="text-xs">
                    Select the SMS template used when dispatching reminders.
                  </CardDescription>
                </div>
                {templates.length > 0 && (
                  <div className="flex items-center gap-2">
                    <Label className="text-xs text-text-secondary shrink-0">Template:</Label>
                    <select
                      value={selectedTemplateId || ""}
                      onChange={(e) => setSelectedTemplateId(Number(e.target.value))}
                      className="text-xs bg-surface border border-border rounded-md px-2.5 py-1 text-text-primary focus:outline-none focus:ring-1 focus:ring-primary"
                    >
                      {templates.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
            </CardHeader>
            <CardContent className="p-4 bg-neutral-light/20">
              <div className="text-xs font-mono bg-card border border-border rounded-lg p-3 text-text-primary leading-relaxed">
                {activeTemplate?.body_template || "Select a template"}
              </div>
              <div className="flex items-center gap-4 mt-2 text-[11px] text-text-secondary">
                <span>
                  Estimated length: ~{activeTemplate?.body_template.length || 0} chars (1 SMS message)
                </span>
                <span>• Available tags: {"{customer}"}, {"{balance_due}"}, {"{item}"}, {"{reference}"}, {"{aging_bucket}"}</span>
              </div>
            </CardContent>
          </Card>

          {/* Candidates Table */}
          <Card>
            <CardHeader className="py-3 px-4 border-b border-border flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-sm font-semibold">
                  Eligible Overdue Customers ({filteredCandidates.length})
                </CardTitle>
                <CardDescription className="text-xs">
                  Select customers and click Send Reminders to trigger SMS dispatch.
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-neutral-light/50 border-b border-border text-text-secondary font-medium">
                    <tr>
                      <th className="p-3 w-10 text-center">
                        <input
                          type="checkbox"
                          checked={
                            filteredCandidates.length > 0 &&
                            filteredCandidates.filter((c) => Boolean(c.mobile)).length > 0 &&
                            filteredCandidates
                              .filter((c) => Boolean(c.mobile))
                              .every((c) => selectedContractIds.has(c.contract_id))
                          }
                          onChange={(e) => handleSelectAll(e.target.checked)}
                          className="rounded border-border text-primary focus:ring-primary"
                        />
                      </th>
                      <th className="p-3 text-left">Customer</th>
                      <th className="p-3 text-left">Mobile / Phone</th>
                      <th className="p-3 text-left">Reference / Item</th>
                      <th className="p-3 text-left">Location</th>
                      <th className="p-3 text-left">Aging / Alert</th>
                      <th className="p-3 text-right">Balance Due</th>
                      <th className="p-3 text-center w-20">Preview</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {loading ? (
                      <tr>
                        <td colSpan={8} className="p-8 text-center text-text-secondary">
                          Loading overdue accounts...
                        </td>
                      </tr>
                    ) : filteredCandidates.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="p-8 text-center text-text-secondary">
                          No overdue accounts match your active filters.
                        </td>
                      </tr>
                    ) : (
                      filteredCandidates.map((c) => {
                        const isSelected = selectedContractIds.has(c.contract_id);
                        const hasPhone = Boolean(c.mobile);
                        return (
                          <tr
                            key={c.contract_id}
                            className={cn(
                              "hover:bg-neutral-light/40 transition-colors",
                              isSelected && "bg-primary/5"
                            )}
                          >
                            <td className="p-3 text-center">
                              <input
                                type="checkbox"
                                checked={isSelected}
                                disabled={!hasPhone}
                                onChange={() => handleToggleRow(c.contract_id)}
                                className="rounded border-border text-primary focus:ring-primary disabled:opacity-30"
                              />
                            </td>
                            <td className="p-3 font-medium text-text-primary">
                              <div>{c.customer}</div>
                              {c.cid && (
                                <div className="text-[10px] text-text-secondary">CID: {c.cid}</div>
                              )}
                            </td>
                            <td className="p-3">
                              {hasPhone ? (
                                <Badge variant="success" className="font-mono text-[11px]">
                                  {c.mobile}
                                </Badge>
                              ) : (
                                <Badge variant="critical" className="text-[10px]">
                                  No phone
                                </Badge>
                              )}
                            </td>
                            <td className="p-3 text-text-secondary">
                              <div className="font-mono text-text-primary text-[11px]">{c.reference}</div>
                              <div className="truncate max-w-[140px] text-[10px]">{c.item}</div>
                            </td>
                            <td className="p-3 text-text-secondary">
                              <div>{c.cost_center || c.region || "—"}</div>
                            </td>
                            <td className="p-3">
                              <span
                                className={cn(
                                  "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold",
                                  c.alert === "Critical"
                                    ? "bg-critical/10 text-critical"
                                    : c.alert === "Follow-up"
                                    ? "bg-warning/15 text-warning-dark"
                                    : "bg-primary/10 text-primary"
                                )}
                              >
                                {c.aging_bucket} • {c.alert}
                              </span>
                            </td>
                            <td className="p-3 text-right tabular-nums font-semibold text-critical">
                              Nu. {c.balance_due.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                            </td>
                            <td className="p-3 text-center">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setPreviewCustomer(c)}
                                className="h-7 px-2 text-[11px] text-primary"
                              >
                                View SMS
                              </Button>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {/* History Tab */}
      {activeTab === "history" && (
        <Card>
          <CardHeader className="py-3 px-4 border-b border-border flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-sm font-semibold">Sent Reminder Logs</CardTitle>
              <CardDescription className="text-xs">
                History of SMS payment reminders dispatched to customers.
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={loadHistory}
              disabled={historyLoading}
              className="h-8 text-xs gap-1.5"
            >
              <RefreshCw className={cn("h-3 w-3", historyLoading && "animate-spin")} />
              <span>Refresh</span>
            </Button>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-neutral-light/50 border-b border-border text-text-secondary font-medium">
                  <tr>
                    <th className="p-3 text-left">Sent At</th>
                    <th className="p-3 text-left">Recipient</th>
                    <th className="p-3 text-left">Channel</th>
                    <th className="p-3 text-left">Status</th>
                    <th className="p-3 text-left">Message Body</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {historyLoading ? (
                    <tr>
                      <td colSpan={5} className="p-8 text-center text-text-secondary">
                        Loading reminder logs...
                      </td>
                    </tr>
                  ) : historyItems.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="p-8 text-center text-text-secondary">
                        No reminders have been dispatched yet.
                      </td>
                    </tr>
                  ) : (
                    historyItems.map((h) => (
                      <tr key={h.id} className="hover:bg-neutral-light/30">
                        <td className="p-3 text-text-secondary whitespace-nowrap">
                          {new Date(h.created_at).toLocaleString()}
                        </td>
                        <td className="p-3 font-mono font-medium text-text-primary">
                          {h.recipient_id}
                        </td>
                        <td className="p-3 uppercase text-[10px] font-bold text-text-secondary">
                          {h.channel}
                        </td>
                        <td className="p-3">
                          {h.status === "sent" ? (
                            <span className="inline-flex items-center gap-1 text-success font-medium text-[11px]">
                              <CheckCircle2 className="h-3.5 w-3.5" />
                              Sent
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-critical font-medium text-[11px]" title={h.error || "Failed"}>
                              <XCircle className="h-3.5 w-3.5" />
                              {h.status}
                            </span>
                          )}
                        </td>
                        <td className="p-3 text-text-secondary max-w-md truncate" title={h.body}>
                          {h.body}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Confirmation Modal */}
      <Dialog open={confirmModalOpen} onOpenChange={setConfirmModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Confirm SMS Reminders</DialogTitle>
            <DialogDescription>
              You are about to dispatch SMS payment reminders to{" "}
              <strong>{selectedCount}</strong> customer{selectedCount > 1 ? "s" : ""}.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-2 text-xs">
            <div className="bg-neutral-light/50 p-3 rounded-lg space-y-1.5 border border-border">
              <div className="flex justify-between">
                <span className="text-text-secondary">Total Customers:</span>
                <span className="font-semibold text-text-primary">{selectedCount}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Total Overdue Reminded:</span>
                <span className="font-semibold text-critical">
                  Nu. {selectedTotalBalance.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Channel:</span>
                <span className="font-semibold text-text-primary">SMS (Bhutan Telecom)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Template:</span>
                <span className="font-semibold text-text-primary">
                  {activeTemplate?.name || "Standard SMS Reminder"}
                </span>
              </div>
            </div>

            <p className="text-text-secondary text-[11px]">
              Each recipient will receive a customized SMS containing their name, contract reference, device, and exact overdue balance due.
            </p>
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setConfirmModalOpen(false)}
              disabled={isSending}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleSendReminders}
              disabled={isSending}
              className="gap-1.5 bg-primary text-white hover:bg-primary-dark"
            >
              <Send className="h-3.5 w-3.5" />
              <span>{isSending ? "Dispatching..." : "Confirm & Send"}</span>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Single Customer SMS Preview Modal */}
      <Dialog open={Boolean(previewCustomer)} onOpenChange={(open) => !open && setPreviewCustomer(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>SMS Message Preview</DialogTitle>
            <DialogDescription>
              Rendered text for {previewCustomer?.customer} ({previewCustomer?.reference})
            </DialogDescription>
          </DialogHeader>

          {previewCustomer && (
            <div className="space-y-3 py-2 text-xs">
              <div className="flex items-center justify-between text-text-secondary">
                <span>To: <strong className="text-text-primary font-mono">{previewCustomer.mobile || "No phone"}</strong></span>
                <span>Due: <strong className="text-critical">Nu. {previewCustomer.balance_due.toLocaleString()}</strong></span>
              </div>

              {/* Rendered SMS Phone Mockup */}
              <div className="bg-surface border-2 border-primary/20 rounded-xl p-4 shadow-inner space-y-2">
                <div className="flex items-center gap-1.5 text-[10px] text-text-secondary border-b border-border/50 pb-2">
                  <MessageSquare className="h-3 w-3 text-primary" />
                  <span>SMS from Bhutan Telecom</span>
                </div>
                <p className="text-xs font-mono text-text-primary leading-relaxed whitespace-pre-wrap">
                  {previewCustomer.rendered_message}
                </p>
              </div>

              <div className="text-[11px] text-text-secondary text-right">
                Character count: {previewCustomer.rendered_message.length} chars (~1 SMS)
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setPreviewCustomer(null)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
