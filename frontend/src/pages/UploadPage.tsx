"use client";

import * as React from "react";
import { useDropzone } from "react-dropzone";
import { Upload, X, CheckCircle, AlertCircle, Loader2, FileSpreadsheet, UserPlus, CreditCard, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Stepper, type StepperStep } from "@/components/ui/stepper";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatError } from "@/lib/api";

interface ValidationIssue {
  severity: "error" | "warning" | "info";
  code: string;
  message: string;
  row?: number;
  column?: string;
  value?: string;
}

interface ValidationReport {
  has_errors: boolean;
  has_warnings: boolean;
  error_count: number;
  warning_count: number;
  issues: ValidationIssue[];
  stats: Record<string, any>;
}

interface MonthlyBreakdown {
  [key: string]: { due: number; received: number; contracts: number };
}

interface UploadPreview {
  id?: number;
  contracts_count: number;
  validation_report: ValidationReport;
  monthly_breakdown: MonthlyBreakdown;
}

const uploadSteps: StepperStep[] = [
  { id: "upload", label: "Choose File", status: "active" },
  { id: "validate", label: "Validate", status: "pending" },
  { id: "preview", label: "Preview", status: "pending" },
  { id: "confirm", label: "Confirm", status: "pending" },
];

type UploadTypeKey = "full" | "customer" | "payment";

const MAX_UPLOAD_MB = 50;

/** Read a response body without assuming it is JSON (nginx/proxy errors are HTML). */
async function readApiResponse(
  response: Response
): Promise<{ data: any; isJson: boolean }> {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return { data: await response.json().catch(() => null), isJson: true };
  }
  return { data: null, isJson: false };
}

function httpErrorMessage(response: Response, action = "Upload"): string {
  switch (response.status) {
    case 413:
      return `File is too large. Maximum ${action.toLowerCase()} size is ${MAX_UPLOAD_MB} MB.`;
    case 401:
      return "Your session has expired. Please sign in again.";
    case 504:
      return "The server took too long to process the file. Please try again.";
    default:
      return `${action} failed (HTTP ${response.status}). Please try again.`;
  }
}

const UPLOAD_TYPES: Record<
  UploadTypeKey,
  {
    label: string;
    description: string;
    icon: React.ReactNode;
    endpoint: string;
    color: string;
  }
> = {
  full: {
    label: "Full Upload",
    description: "Contracts + Installments (original format)",
    icon: <FileSpreadsheet className="h-5 w-5" />,
    endpoint: "/api/v1/uploads",
    color: "text-primary",
  },
  customer: {
    label: "Customer Upload",
    description: "New customers / contract master data only",
    icon: <UserPlus className="h-5 w-5" />,
    endpoint: "/api/v1/uploads/customers",
    color: "text-success",
  },
  payment: {
    label: "Payment Upload",
    description: "Monthly installment / payment data only",
    icon: <CreditCard className="h-5 w-5" />,
    endpoint: "/api/v1/uploads/payments",
    color: "text-warning",
  },
};

export function UploadPage() {
  const [currentStep, setCurrentStep] = React.useState(0);
  const [file, setFile] = React.useState<File | null>(null);
  const [uploadId, setUploadId] = React.useState<number | null>(null);
  const [preview, setPreview] = React.useState<UploadPreview | null>(null);
  const [isUploading, setIsUploading] = React.useState(false);
  const [isConfirming, setIsConfirming] = React.useState(false);
  const [totpCode, setTotpCode] = React.useState("");
  const [asOfDate, setAsOfDate] = React.useState(() => {
    const today = new Date();
    return today.toISOString().slice(0, 10); // YYYY-MM-DD
  });
  const [uploadType, setUploadType] = React.useState<UploadTypeKey>("customer");

  const onDrop = React.useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      const f = acceptedFiles[0];
      if (f.name.endsWith(".xlsx") || f.name.endsWith(".xls")) {
        setFile(f);
      } else {
        alert("Please select an Excel file (.xlsx or .xls)");
      }
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel": [".xls"],
    },
    maxSize: MAX_UPLOAD_MB * 1024 * 1024,
    onDropRejected: (rejections) => {
      const tooLarge = rejections.some((r) =>
        r.errors.some((e) => e.code === "file-too-large")
      );
      alert(
        tooLarge
          ? `File is too large. Maximum upload size is ${MAX_UPLOAD_MB} MB.`
          : "Please select an Excel file (.xlsx or .xls)"
      );
    },
  });

  const handleUpload = async () => {
    if (!file) return;
    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("as_of_date", asOfDate);

      const response = await fetch(UPLOAD_TYPES[uploadType].endpoint, {
        method: "POST",
        body: formData,
      });

      const { data, isJson } = await readApiResponse(response);
      if (response.ok && isJson) {
        const id = data.id ?? data.preview?.id;
        setUploadId(id);
        setPreview({
          id,
          ...data.preview,
        });
        setCurrentStep(1); // Go to validate step
      } else if (response.ok) {
        alert("Upload succeeded but the server returned an unexpected response. Please refresh and check the upload list.");
      } else {
        alert(
          isJson && data?.detail
            ? formatError(data.detail)
            : httpErrorMessage(response, "Upload")
        );
      }
    } catch (error) {
      alert(error instanceof Error ? error.message : "Upload failed. Please try again.");
    } finally {
      setIsUploading(false);
    }
  };

  const handleConfirm = async () => {
    const targetId = uploadId ?? preview?.id;
    if (!targetId) {
      alert("No upload record found to confirm.");
      return;
    }
    setIsConfirming(true);
    try {
      const response = await fetch(`${UPLOAD_TYPES[uploadType].endpoint}/${targetId}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ totp_code: totpCode, code: totpCode }),
      });

      const { data, isJson } = await readApiResponse(response);
      if (response.ok) {
        alert("Upload confirmed successfully!");
        setCurrentStep(0);
        setFile(null);
        setPreview(null);
        setUploadId(null);
        setTotpCode("");
      } else {
        alert(
          isJson && data?.detail
            ? formatError(data.detail)
            : httpErrorMessage(response, "Confirmation")
        );
      }
    } catch (error) {
      alert(error instanceof Error ? error.message : "Confirmation failed. Please try again.");
    } finally {
      setIsConfirming(false);
    }
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 0:
        return <UploadStep onDrop={onDrop} getRootProps={getRootProps} getInputProps={getInputProps} isDragActive={isDragActive} file={file} setFile={setFile} asOfDate={asOfDate} setAsOfDate={setAsOfDate} onUpload={handleUpload} isUploading={isUploading} uploadType={uploadType} setUploadType={setUploadType} />;
      case 1:
        return <ValidateStep preview={preview} onNext={() => setCurrentStep(2)} onBack={() => setCurrentStep(0)} />;
      case 2:
        return <PreviewStep preview={preview} onNext={() => setCurrentStep(3)} onBack={() => setCurrentStep(1)} />;
      case 3:
        return <ConfirmStep preview={preview} totpCode={totpCode} setTotpCode={setTotpCode} onConfirm={handleConfirm} isConfirming={isConfirming} onBack={() => setCurrentStep(2)} />;
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Upload EMI Data</h1>
          <p className="text-text-secondary mt-1">4-step process: Choose → Validate → Preview → Confirm</p>
        </div>
      </div>

      <Stepper steps={uploadSteps} />

      <Card className="mt-4">
        <CardContent className="pt-0">{renderStepContent()}</CardContent>
      </Card>
    </div>
  );
}

function UploadStep({
  getRootProps,
  getInputProps,
  isDragActive,
  file,
  setFile,
  asOfDate,
  setAsOfDate,
  onUpload,
  isUploading,
  uploadType,
  setUploadType,
}: any) {
  return (
    <div className="p-6 space-y-6">
      <Card className="border-primary/50 bg-primary/5">
        <CardContent className="p-4">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
              <span className="text-sm font-bold text-primary">!</span>
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="font-medium text-text-primary mb-2">Recommended Upload Order</h4>
              <ol className="space-y-1 text-sm text-text-secondary list-decimal list-inside">
                <li>
                  <strong>Step 1:</strong>{" "}
                  <span className="text-success">Customer Upload</span> — Upload
                  &quot;Customer or sales Details.xlsx&quot; first (creates contract master data)
                </li>
                <li>
                  <strong>Step 2:</strong>{" "}
                  <span className="text-warning">Payment Upload</span> — Upload
                  &quot;Salary_Slip_Oct.xlsx&quot; (employee EMI payments)
                </li>
                <li>
                  <strong>Step 3:</strong>{" "}
                  <span className="text-warning">Payment Upload</span> — Upload
                  &quot;Payment.xlsx&quot; (external customer EMI payments)
                </li>
              </ol>
              <p className="text-xs text-text-secondary mt-2">
                <em>
                  Note: Payment uploads require contracts to exist from Step 1. Select
                  &quot;Customer Upload&quot; type for customer data, &quot;Payment
                  Upload&quot; for payment files.
                </em>
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="mb-4">
        <Label className="block mb-2">Upload Type</Label>
        <div className="grid grid-cols-3 gap-3">
          {(["full", "customer", "payment"] as UploadTypeKey[]).map((key) => {
            const type = UPLOAD_TYPES[key];
            return (
              <button
                key={key}
                type="button"
                onClick={() => setUploadType(key)}
                className={cn(
                  "relative p-4 rounded-lg border-2 transition-all text-left",
                  uploadType === key
                    ? "border-primary bg-primary/5 shadow-md shadow-primary/10"
                    : "border-border hover:border-primary/50 hover:bg-neutral-light/50"
                )}
              >
                <div className="flex items-center gap-3">
                  <span
                    className={cn(
                      "p-2 rounded-lg",
                      uploadType === key ? "bg-primary/10" : "bg-neutral-light/50"
                    )}
                  >
                    {type.icon}
                  </span>
                  <div>
                    <p className="font-medium text-text-primary">{type.label}</p>
                    <p className="text-sm text-text-secondary">{type.description}</p>
                  </div>
                </div>
                {uploadType === key && (
                  <div className="absolute top-2 right-2 w-5 h-5 rounded-full bg-primary flex items-center justify-center">
                    <Check className="h-3 w-3 text-white" />
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Label className="block mb-2">Drag & drop Excel file or click to browse</Label>
          <div
            {...getRootProps()}
            className={cn(
              "relative rounded-card border-2 border-dashed p-8 text-center transition-colors",
              isDragActive ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"
            )}
          >
            <input {...getInputProps()} />
            <Upload className="h-12 w-12 mx-auto text-text-secondary mb-4" />
            <p className="text-text-primary mb-1">{file ? file.name : "Drop .xlsx or .xls file here"}</p>
            <p className="text-sm text-text-secondary">Max size: 50MB</p>
            {file && (
              <div className="mt-4 flex items-center justify-center gap-2">
                <span className="text-sm text-text-secondary">{formatBytes(file.size)}</span>
                <Button variant="ghost" size="sm" onClick={() => setFile(null)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Upload Settings</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="as_of_date">As-of Date</Label>
                <Input
                  id="as_of_date"
                  type="date"
                  max={new Date().toISOString().slice(0, 10)}
                  value={asOfDate}
                  onChange={(e) => setAsOfDate(e.target.value)}
                />
                <p className="text-sm text-text-secondary mt-1">The date this data represents</p>
              </div>

              <div>
                <Label htmlFor="sheet_name">Sheet Name (optional)</Label>
                <Input id="sheet_name" placeholder="Leave blank for first sheet" />
              </div>

              <div>
                <Label htmlFor="header_row">Header Row (optional)</Label>
                <Input id="header_row" type="number" placeholder="Auto-detect" min="1" />
              </div>
            </CardContent>
          </Card>

          <Button onClick={onUpload} disabled={!file || isUploading} className="w-full" size="lg">
            {isUploading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Upload className="h-4 w-4 mr-2" />}
            {isUploading ? "Uploading..." : "Upload & Validate"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function ValidateStep({ preview, onNext, onBack }: any) {
  const report = preview?.validation_report;
  if (!report) return <div>Loading...</div>;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Validation Results</h2>
          <p className="text-text-secondary">Review issues before proceeding</p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant={report.has_errors ? "critical" : "success"}>
            {report.has_errors ? "Has Errors" : "All Clear"}
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card className="border-critical/50">
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-critical">{report.error_count}</p>
            <p className="text-sm text-text-secondary">Errors</p>
          </CardContent>
        </Card>
        <Card className="border-warning/50">
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-warning">{report.warning_count}</p>
            <p className="text-sm text-text-secondary">Warnings</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-text-primary">{preview.contracts_count}</p>
            <p className="text-sm text-text-secondary">Contracts</p>
          </CardContent>
        </Card>
      </div>

      {report.has_errors && (
        <Card className="border-critical/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-critical">
              <AlertCircle className="h-4 w-4" /> Errors (must fix before confirming)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ValidationIssuesList issues={report.issues.filter((i: ValidationIssue) => i.severity === "error")} />
          </CardContent>
        </Card>
      )}

      {report.has_warnings && (
        <Card className="border-warning/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-warning">
              <AlertCircle className="h-4 w-4" /> Warnings (review recommended)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ValidationIssuesList issues={report.issues.filter((i: ValidationIssue) => i.severity === "warning")} />
          </CardContent>
        </Card>
      )}

      <div className="flex justify-end gap-3">
        <Button variant="outline" onClick={onBack}>Back</Button>
        <Button onClick={onNext} disabled={report.has_errors}>
          Continue to Preview
        </Button>
      </div>
    </div>
  );
}

function ValidationIssuesList({ issues }: { issues: ValidationIssue[] }) {
  return (
    <div className="space-y-2 max-h-96 overflow-y-auto">
      {issues.slice(0, 20).map((issue, index) => (
        <div key={index} className="flex items-start gap-3 p-3 rounded-lg bg-neutral-light/50 border border-border">
          <Badge variant={issue.severity === "error" ? "critical" : "warning"} className="mt-0.5 flex-shrink-0">
            {issue.code}
          </Badge>
          <div className="flex-1 min-w-0">
            <p className="font-medium text-text-primary">{issue.message}</p>
            {issue.row && <p className="text-sm text-text-secondary">Row {issue.row}{issue.column ? `, Column: ${issue.column}` : ""}</p>}
            {issue.value && <p className="text-sm text-text-secondary font-mono">Value: {issue.value}</p>}
          </div>
        </div>
      ))}
      {issues.length > 20 && <p className="text-sm text-text-secondary text-center py-2">... and {issues.length - 20} more issues</p>}
    </div>
  );
}

function PreviewStep({ preview, onNext, onBack }: any) {
  if (!preview) return <div>Loading...</div>;

  const breakdown = (preview.monthly_breakdown || {}) as Record<string, { due?: number; received?: number }>;
  const months = Object.keys(breakdown);
  const totalDue = Object.values(breakdown).reduce((sum, item) => sum + (Number(item?.due) || 0), 0);
  const totalReceived = Object.values(breakdown).reduce((sum, item) => sum + (Number(item?.received) || 0), 0);

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Preview Summary</h2>
        <p className="text-text-secondary">Review the changes before confirming</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-text-primary">{preview.contracts_count}</p>
            <p className="text-sm text-text-secondary">Contracts</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-primary">{months.length}</p>
            <p className="text-sm text-text-secondary">Months</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-success">Nu. {formatNumber(totalDue)}</p>
            <p className="text-sm text-text-secondary">Total Due</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-warning">Nu. {formatNumber(totalReceived)}</p>
            <p className="text-sm text-text-secondary">Total Received</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Monthly Breakdown</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left p-3 font-medium text-text-secondary">Month</th>
                  <th className="text-right p-3 font-medium text-text-secondary tabular-nums">Due</th>
                  <th className="text-right p-3 font-medium text-text-secondary tabular-nums">Received</th>
                  <th className="text-right p-3 font-medium text-text-secondary tabular-nums">Outstanding</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(breakdown).map(([month, data]) => {
                  const due = Number(data?.due) || 0;
                  const received = Number(data?.received) || 0;
                  return (
                    <tr key={month} className="border-b border-border/50 hover:bg-neutral-light/50">
                      <td className="p-3 font-medium">{month}</td>
                      <td className="p-3 text-right tabular-nums">Nu. {formatNumber(due)}</td>
                      <td className="p-3 text-right tabular-nums">Nu. {formatNumber(received)}</td>
                      <td className="p-3 text-right tabular-nums text-critical">Nu. {formatNumber(due - received)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end gap-3">
        <Button variant="outline" onClick={onBack}>Back</Button>
        <Button onClick={onNext}>Continue to Confirm</Button>
      </div>
    </div>
  );
}

function ConfirmStep({ preview, totpCode, setTotpCode, onConfirm, isConfirming, onBack }: any) {
  return (
    <div className="p-6 space-y-6">
      <div className="border-l-4 border-critical bg-critical-light/50 p-4 rounded-r-card">
        <h2 className="font-semibold text-critical flex items-center gap-2">
          <AlertCircle className="h-5 w-5" /> Final Confirmation Required
        </h2>
        <p className="text-sm text-text-secondary mt-1">
          This action will update {preview.contracts_count} contracts in the database.
          Please enter your authenticator code to proceed.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Authenticator Code</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3 max-w-xs">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <input
                key={i}
                type="text"
                maxLength={1}
                value={totpCode[i - 1] || ""}
                onChange={(e) => {
                  const newCode = totpCode.split("");
                  newCode[i - 1] = e.target.value;
                  setTotpCode(newCode.join(""));
                  if (e.target.value && i < 6) {
                    (document.getElementById(`totp-${i + 1}`) as HTMLInputElement)?.focus();
                  }
                }}
                onKeyDown={(e) => {
                  if (e.key === "Backspace" && !totpCode[i - 1] && i > 1) {
                    (document.getElementById(`totp-${i - 1}`) as HTMLInputElement)?.focus();
                  }
                }}
                id={`totp-${i}`}
                className="w-10 h-10 text-center text-xl font-mono rounded-lg border border-input bg-background focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
                autoComplete="one-time-code"
              />
            ))}
          </div>
          <p className="text-sm text-text-secondary">Enter the 6-digit code from your authenticator app</p>
        </CardContent>
      </Card>

      <div className="flex justify-end gap-3">
        <Button variant="outline" onClick={onBack}>Back</Button>
        <Button onClick={onConfirm} disabled={totpCode.length !== 6 || isConfirming} className="bg-critical hover:bg-critical/90">
          {isConfirming ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <CheckCircle className="h-4 w-4 mr-2" />}
          {isConfirming ? "Confirming..." : "Confirm Upload"}
        </Button>
      </div>
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

function formatNumber(value: number): string {
  if (value === null || value === undefined || isNaN(Number(value))) return "0.00";
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value));
}