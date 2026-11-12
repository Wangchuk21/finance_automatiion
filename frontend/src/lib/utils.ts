import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number, currency = "Nu.", locale = "en-IN"): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: currency.replace(".", ""),
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function formatCurrencyCompact(amount: number, currency = "Nu."): string {
  if (amount >= 1e7) {
    return `${currency} ${(amount / 1e7).toFixed(2)} Cr`;
  }
  if (amount >= 1e5) {
    return `${currency} ${(amount / 1e5).toFixed(2)} L`;
  }
  if (amount >= 1e3) {
    return `${currency} ${(amount / 1e3).toFixed(1)} K`;
  }
  return `${currency} ${amount.toFixed(0)}`;
}

export function formatDate(date: string | Date, options?: Intl.DateTimeFormatOptions): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    ...options,
  });
}

export function formatMonthYear(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(value);
}

export function getStatusBadgeVariant(status: string): "success" | "warning" | "critical" | "neutral" | "primary" {
  const s = status.toLowerCase();
  if (["paid", "completed", "confirmed", "active"].includes(s)) return "success";
  if (["pending", "partial", "watch", "in_progress", "missing_review"].includes(s)) return "warning";
  if (["overdue", "error", "failed", "rejected", "critical"].includes(s)) return "critical";
  if (["closed", "cancelled", "rolled_back", "waived"].includes(s)) return "neutral";
  return "primary";
}

export function calculateChange(current: number, previous: number): { value: number; isPositive: boolean } {
  if (previous === 0) return { value: 0, isPositive: true };
  const change = ((current - previous) / Math.abs(previous)) * 100;
  return { value: Math.abs(change), isPositive: change >= 0 };
}

export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout> | null = null;
  return (...args: Parameters<T>) => {
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
}

export function generateId(): string {
  return Math.random().toString(36).substring(2, 15);
}