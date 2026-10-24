"use client";

import * as React from "react";
import { useDropzone } from "react-dropzone";
import { FileText, Upload, X, CheckCircle, AlertCircle, Loader2, ChevronRight, Eye, Settings } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Stepper, StepperStep } from "@/components/ui/stepper";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";

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

export function UploadPage() {
  const [currentStep, setCurrentStep] = React.useState(0);
  const [file, setFile] = React.useState<File | null>(null);
  const [preview, setPreview] = React.useState<UploadPreview | null>(null);
  const [isUploading, setIsUploading] = React.useState(false);
  const [isConfirming, setIsConfirming] = React.useState(false);
  const [totpCode, setTotpCode] = React.useState("");
  const [asOfDate, setAsOfDate] = React.useState(() => {
    const today = new Date();
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
  });

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

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, accept: { "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"], "application/vnd.ms-excel": [".xls"] } });

  const handleUpload = async () => {
    if (!file) return;
    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("as_of_date", asOfDate);

      const response = await fetch("/api/uploads", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();
      if (response.ok) {
        setPreview(data.preview);
        setCurrentStep(1); // Go to validate step
      } else {
        alert(data.detail || "Upload failed");
      }
    } catch (error) {
      alert("Upload failed: " + error);
    } finally {
      setIsUploading(false);
    }
  };

  const handleConfirm = async () => {
    if (!preview) return;
    setIsConfirming(true);
    try {
      const response = await fetch(`/api/uploads/${preview.id}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ totp_code: totpCode }),
      });

      const data = await response.json();
      if (response.ok) {
        alert("Upload confirmed successfully!");
        setCurrentStep(0);
        setFile(null);
        setPreview(null);
        setTotpCode("");
      } else {
        alert(data.detail || "Confirmation failed");
      }
    } catch (error) {
      alert("Confirmation failed: " + error);
    } finally {
      setIsConfirming(false);
    }
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 0:
        return <UploadStep onDrop={onDrop} getRootProps={getRootProps} getInputProps={getInputProps} isDragActive={isDragActive} file={file} asOfDate={asOfDate} setAsOfDate={setAsOfDate} onUpload={handleUpload} isUploading={isUploading} />;
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
  onDrop,
  getRootProps,
  getInputProps,
  isDragActive,
  file,
  asOfDate,
  setAsOfDate,
  onUpload,
  isUploading,
}: any) {
  return (
    <div className="p-6 space-y-6">
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
                <Input id="as_of_date" type="month" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} />
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
            <ValidationIssuesList issues={report.issues.filter((i) => i.severity === "error")} />
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
            <ValidationIssuesList issues={report.issues.filter((i) => i.severity === "warning")} />
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
            <p className="text-2xl font-bold text-primary">{Object.keys(preview.monthly_breakdown).length}</p>
            <p className="text-sm text-text-secondary">Months</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-success">₹{formatNumber(preview.monthly_breakdown)}</p>
            <p className="text-sm text-text-secondary">Total Due</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-warning">₹{formatNumber(preview.monthly_breakdown)}</p>
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
                {Object.entries(preview.monthly_breakdown).map(([month, data]) => (
                  <tr key={month} className="border-b border-border/50 hover:bg-neutral-light/50">
                    <td className="p-3 font-medium">{month}</td>
                    <td className="p-3 text-right tabular-nums">₹{formatNumber(data.due)}</td>
                    <td className="p-3 text-right tabular-nums">₹{formatNumber(data.received)}</td>
                    <td className="p-3 text-right tabular-nums text-critical">₹{formatNumber(data.due - data.received)}</td>
                  </tr>
                ))}
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
  return new Intl.NumberFormat("en-IN").format(value);
}