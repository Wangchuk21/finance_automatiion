"use client";

import { useState } from "react";
import { Loader2, AlertTriangle, CheckCircle2, CreditCard, Shield, Clock, Users, DollarSign, FileText } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { authApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface CreditContract {
  reference: string;
  item: string;
  brand: string;
  start_date: string;
  end_date: string;
  status: string;
  monthly_emi: number;
  outstanding: number;
  balance_due: number;
  months_left: number;
  is_overdue: boolean;
  overdue_amount: number;
}

interface CreditCheckResponse {
  cid: string;
  customer_name: string;
  mobile: string | null;
  total_contracts: number;
  active_contracts: number;
  closed_contracts: number;
  overdue_contracts: number;
  total_outstanding: number;
  total_balance_due: number;
  total_monthly_emi: number;
  total_collected: number;
  total_installments: number;
  paid_installments: number;
  overdue_installments: number;
  partial_installments: number;
  payment_rate: number;
  max_days_overdue: number;
  has_overdue: boolean;
  multiple_active_loans: boolean;
  high_balance_due_ratio: boolean;
  credit_score: number;
  risk_level: "low" | "medium" | "high" | "critical";
  recommendation: string;
  contracts: CreditContract[];
}

function RiskBadge({ level }: { level: string }) {
  const variants = {
    low: "bg-success/10 text-success border-success/20",
    medium: "bg-warning/10 text-warning border-warning/20",
    high: "bg-orange/10 text-orange border-orange/20",
    critical: "bg-critical/10 text-critical border-critical/20",
  };
  return (
    <Badge variant="default" className={variants[level as keyof typeof variants] || "bg-neutral-light text-text-secondary"}>
      {level.charAt(0).toUpperCase() + level.slice(1)} Risk
    </Badge>
  );
}

function ScoreCircle({ score }: { score: number }) {
  const getColor = (s: number) => {
    if (s >= 80) return "text-success";
    if (s >= 60) return "text-warning";
    if (s >= 40) return "text-orange";
    return "text-critical";
  };
  return (
    <div className="relative w-24 h-24">
      <svg className="w-24 h-24 transform -rotate-90">
        <circle
          className="text-neutral-light"
          strokeWidth="8"
          stroke="currentColor"
          fill="transparent"
          r="48"
          cx="60"
          cy="60"
        />
        <circle
          className={getColor(100)}
          strokeWidth="8"
          strokeDasharray={`${(100 * 301.44) / 100} 301.44`}
          strokeLinecap="round"
          stroke="currentColor"
          fill="transparent"
          r="48"
          cx="60"
          cy="60"
          style={{ strokeDasharray: `${(score * 301.44) / 100} 301.44` }}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className={`text-3xl font-bold ${["text-critical", "text-orange", "text-warning", "text-success"][Math.floor(score / 25)]}`}>
          {score}
        </span>
      </div>
    </div>
  );
}

export function CreditCheckPage() {
  const { isAuthenticated } = useAuth();
  const [cid, setCid] = useState("");
  const [data, setData] = useState<CreditCheckResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"overview" | "contracts" | "installments">("overview");

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-neutral-light/50">
        <div className="text-center">
          <Loader2 className="h-10 w-10 animate-spin text-primary mx-auto" />
          <p className="mt-4 text-text-secondary">Checking authentication...</p>
        </div>
      </div>
    );
  }

  const handleCheck = async () => {
    if (!cid.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await authApi.creditCheck(cid.trim());
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to check credit");
    } finally {
      setLoading(false);
    }
  };

  if (!data) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Credit Check</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Enter a Customer CID to check their creditworthiness before approving new EMI
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Credit Check Lookup
            </CardTitle>
            <CardDescription>
              Enter Customer CID to retrieve credit score, risk assessment, and contract history
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-3">
              <Label htmlFor="cid" className="sr-only">
                Customer CID
              </Label>
              <Input
                id="cid"
                type="text"
                value={cid}
                onChange={(e) => setCid(e.target.value)}
                placeholder="Enter Customer CID (e.g., 11803002498)"
                className="flex-1"
                onKeyDown={(e) => e.key === "Enter" && handleCheck()}
              />
              <Button onClick={handleCheck} disabled={loading || !cid.trim()}>
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    Checking...
                  </>
                ) : (
                  "Check Credit"
                )}
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm text-text-secondary">
              <div className="flex items-center gap-2">
                <CreditCard className="h-4 w-4" />
                <span>Enter 10+ digit CID</span>
              </div>
              <div className="flex items-center gap-2">
                <Users className="h-4 w-4" />
                <span>Validates against existing contracts</span>
              </div>
              <div className="flex items-center gap-2">
                <Shield className="h-4 w-4" />
                <span>Returns credit score & risk level</span>
              </div>
            </div>

            {error && (
              <Alert variant="destructive" className="text-sm">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  // Data loaded - show results
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Credit Check Results</h1>
          <p className="mt-1 text-sm text-text-secondary">
            CID: {data.cid} • {data.customer_name} • {data.mobile || "No mobile"}
          </p>
        </div>
        <Button variant="outline" onClick={() => setData(null)}>
          <FileText className="h-4 w-4 mr-2" />
          New Search
        </Button>
      </div>

      {/* Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-text-secondary">Credit Score</p>
                <div className="flex items-baseline gap-1 mt-1">
                  <span className="text-3xl font-bold">{data.credit_score}</span>
                  <span className="text-text-secondary">/ 100</span>
                </div>
              </div>
              <div className="w-16 h-16">
                <ScoreCircle score={data.credit_score} />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <p className="text-sm text-text-secondary">Risk Level</p>
            <div className="mt-2">
              <RiskBadge level={data.risk_level} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <p className="text-sm text-text-secondary">Total Balance Due</p>
            <p className="text-2xl font-bold text-critical mt-1">
              {data.total_balance_due > 0 ? data.total_balance_due.toLocaleString("en-US") : "0"}
            </p>
            <p className="text-xs text-text-secondary mt-1">Nu. balance due</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <p className="text-sm text-text-secondary">Payment Rate</p>
            <p className="text-2xl font-bold text-success mt-1">
              {(data.payment_rate * 100).toFixed(1)}%
            </p>
            <p className="text-xs text-text-secondary mt-1">
              {data.paid_installments}/{data.total_installments} paid
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Risk Assessment */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Risk Assessment
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3 p-4 rounded-lg bg-neutral-light/50">
            <div className="flex-1">
              <p className="font-medium">{data.recommendation}</p>
              <p className="text-sm text-text-secondary mt-1">
                Score: {data.credit_score}/100 • Risk: {data.risk_level}
              </p>
            </div>
            <RiskBadge level={data.risk_level} />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 rounded-lg border border-border">
              <div className="flex items-center gap-2 text-sm text-text-secondary">
                <AlertTriangle className="h-4 w-4" />
                <span>Overdue Contracts: {data.overdue_contracts}</span>
              </div>
              <p className="text-lg font-bold mt-1">{data.overdue_contracts}</p>
            </div>
            <div className="p-4 rounded-lg border border-border">
              <div className="flex items-center gap-2 text-sm text-text-secondary">
                <Clock className="h-4 w-4" />
                <span>Max Days Overdue</span>
              </div>
              <p className="text-lg font-bold mt-1">{data.max_days_overdue}</p>
            </div>
            <div className="p-4 rounded-lg border border-border">
              <div className="flex items-center gap-2 text-sm text-text-secondary">
                <DollarSign className="h-4 w-4" />
                <span>Total Balance Due</span>
              </div>
              <p className="text-lg font-bold mt-1 text-critical">
                {data.total_balance_due.toLocaleString("en-US")}
              </p>
            </div>
          </div>

          <Separator />

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="p-3 rounded-lg border border-border">
              <p className="text-sm text-text-secondary">Total Contracts</p>
              <p className="text-xl font-bold">{data.total_contracts}</p>
            </div>
            <div className="p-3 rounded-lg border border-border">
              <p className="text-sm text-text-secondary">Active</p>
              <p className="text-xl font-bold text-success">{data.active_contracts}</p>
            </div>
            <div className="p-3 rounded-lg border border-border">
              <p className="text-sm text-text-secondary">Closed</p>
              <p className="text-xl font-bold">{data.closed_contracts}</p>
            </div>
            <div className="p-3 rounded-lg border border-border">
              <p className="text-sm text-text-secondary">Overdue</p>
              <p className="text-xl font-bold text-critical">{data.overdue_contracts}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <div className="flex border-b border-border">
        <button
          onClick={() => setActiveTab("overview")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "overview"
              ? "border-primary text-primary"
              : "border-transparent text-text-secondary hover:text-text-primary"
          }`}
        >
          Overview
        </button>
        <button
          onClick={() => setActiveTab("contracts")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "contracts"
              ? "border-primary text-primary"
              : "border-transparent text-text-secondary hover:text-text-primary"
          }`}
        >
          Contracts ({data.contracts.length})
        </button>
      </div>

{/* Tab Content */}
      {activeTab === "overview" ? (
        <Card>
          <CardContent className="p-6 space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h4 className="font-medium mb-3">Financial Summary</h4>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Total Outstanding</span>
                    <span className="font-medium">{data.total_outstanding.toLocaleString("en-US")} Nu.</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Total Collected</span>
                    <span className="font-medium text-success">{data.total_collected.toLocaleString("en-US")} Nu.</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Total Balance Due</span>
                    <span className="font-medium text-critical">{data.total_balance_due.toLocaleString("en-US")} Nu.</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Monthly EMI</span>
                    <span className="font-medium">{data.total_monthly_emi.toLocaleString("en-US")} Nu.</span>
                  </div>
                </div>
              </div>
              <div>
                <h4 className="font-medium mb-3">Installment Performance</h4>
                <div className="space-y-3">
                  <div>
                    <div className="flex justify-between text-sm mb-1">
                      <span>Payment Rate</span>
                      <span className="font-medium">{(data.payment_rate * 100).toFixed(1)}%</span>
                    </div>
                    <Progress value={data.payment_rate * 100} className="h-2" />
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-sm">
                    <div className="p-2 rounded border">
                      <div className="text-text-secondary">Paid</div>
                      <div className="font-bold text-success">{data.paid_installments}</div>
                    </div>
                    <div className="p-2 rounded border">
                      <div className="text-text-secondary">Overdue</div>
                      <div className="font-bold text-critical">{data.overdue_installments}</div>
                    </div>
                    <div className="p-2 rounded border">
                      <div className="text-text-secondary">Partial</div>
                      <div className="font-bold text-warning">{data.partial_installments}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div>
              <h4 className="font-medium mb-3">Risk Indicators</h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className={`p-3 rounded-lg border ${data.has_overdue ? "border-critical/50 bg-critical/5" : "border-success/50 bg-success/5"}`}>
                  <div className="flex items-center gap-2">
                    {data.has_overdue ? (
                      <AlertTriangle className="h-4 w-4 text-critical" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4 text-success" />
                    )}
                    <span className="font-medium">Has Overdue</span>
                  </div>
                  <p className="text-sm text-text-secondary mt-1">
                    {data.has_overdue ? "Customer has overdue payments" : "No overdue payments"}
                  </p>
                </div>
                <div className={`p-3 rounded-lg border ${data.multiple_active_loans ? "border-warning/50 bg-warning/5" : "border-success/50 bg-success/5"}`}>
                  <div className="flex items-center gap-2">
                    {data.multiple_active_loans ? (
                      <AlertTriangle className="h-4 w-4 text-warning" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4 text-success" />
                    )}
                    <span className="font-medium">Multiple Active Loans</span>
                  </div>
                  <p className="text-sm text-text-secondary mt-1">
                    {data.multiple_active_loans ? `${data.active_contracts} active loans` : "Single active loan"}
                  </p>
                </div>
                <div className={`p-3 rounded-lg border ${data.high_balance_due_ratio ? "border-critical/50 bg-critical/5" : "border-success/50 bg-success/5"}`}>
                  <div className="flex items-center gap-2">
                    {data.high_balance_due_ratio ? (
                      <AlertTriangle className="h-4 w-4 text-critical" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4 text-success" />
                    )}
                    <span className="font-medium">High Balance/EMI Ratio</span>
                  </div>
                  <p className="text-sm text-text-secondary mt-1">
                    {data.high_balance_due_ratio ? "Balance due > 2x monthly EMI" : "Healthy balance/EMI ratio"}
                  </p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Reference</TableHead>
                    <TableHead>Item</TableHead>
                    <TableHead>Brand</TableHead>
                    <TableHead className="text-right">Monthly EMI</TableHead>
                    <TableHead className="text-right">Outstanding</TableHead>
                    <TableHead className="text-right">Balance Due</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Months Left</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.contracts.map((contract) => (
                    <TableRow key={contract.reference}>
                      <TableCell className="font-mono">{contract.reference}</TableCell>
                      <TableCell>{contract.item}</TableCell>
                      <TableCell>{contract.brand}</TableCell>
                      <TableCell className="text-right font-mono">
                        {contract.monthly_emi.toLocaleString("en-US")} Nu.
                      </TableCell>
                      <TableCell className="text-right">
                        {contract.outstanding.toLocaleString("en-US")} Nu.
                      </TableCell>
                      <TableCell className="text-right font-medium text-critical">
                        {contract.balance_due.toLocaleString("en-US")} Nu.
                      </TableCell>
                      <TableCell>
                        <Badge variant={contract.is_overdue ? "critical" : "default"}>
                          {contract.is_overdue ? "Overdue" : contract.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        {contract.months_left} months
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}